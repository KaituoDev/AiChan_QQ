import asyncio
import json
from collections import deque
from dataclasses import dataclass, asdict, field
from enum import Enum
from logging.handlers import SocketHandler
from typing import List, Union, Optional, Dict

import aiohttp
import botpy
from aiohttp import web
from botpy import Intents
from botpy import logger
from botpy.message import Message, GroupMessage, C2CMessage

import aichan_storage
import keyword_processor
from socket_packet import SocketPacket, PacketType
from utils import get_unix_timestamp_from_iso8601, get_unix_timestamp, \
    get_message_without_at, is_at_section, get_user_id_from_at_section, get_unix_timestamp_from_rfc3339, \
    get_formatted_time, remove_minecraft_color

# This interval is to prevent the bot from spamming messages too quickly.
MESSAGE_POLLING_INTERVAL = 0.5

# This http server is useful when an alternative account is available to send messages,
# so that the bot account can send messages as "reply" messages.
# Since QQ banned bots from sending active messages, this acts as a workaround.
# If there are regular messages to be sent, the server will return 200.
# Otherwise, the server will return 404.
HTTP_SERVER_PORT = 23000

# Set to store context message polling and deletion tasks
background_tasks = set()


class MessageType(Enum):
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"


@dataclass(frozen=True)
class MessageContext:
    """
    Represents the context of a message, including its type, unique identifiers, and relevant information.
    """
    message_type: MessageType
    message_id: str
    timestamp: int

    # Valid for group messages
    group_id: str = ""
    # Valid for channel messages
    guild_id: str = ""
    # Valid for channel messages
    channel_id: str = ""
    # Valid for private, group and channel messages
    user_id: str = ""


    def to_json(self):
        data = asdict(self)
        data["message_type"] = self.message_type.value
        return json.dumps(data)


    @classmethod
    def from_json(cls, json_str: str):
        data = json.loads(json_str)
        data["message_type"] = MessageType(data["message_type"])
        return cls(**data)


@dataclass
class ContextState:
    messages: List[str] = field(default_factory=list)
    sequence: int = 1


@dataclass
class ServerInfo:
    name: str
    trigger: str
    broadcast_trigger: str


def is_admin(context: MessageContext) -> bool:
    config = aichan_storage.bot_config

    if context.message_type == MessageType.PRIVATE:
        # Use 'or []' to prevent private_admins from being parsed as None when it's empty in YAML
        return context.user_id in (config.get("private_admins") or [])

    if context.message_type == MessageType.GROUP:
        group_admins = config.get("group_admins") or {}
        return context.user_id in group_admins.get(context.group_id, [])

    if context.message_type == MessageType.CHANNEL:
        guild_admins = config.get("guild_admins") or {}
        return context.user_id in guild_admins.get(context.guild_id, [])

    return False


def get_guild_username(context: MessageContext) -> Optional[str]:
    if context.message_type != MessageType.CHANNEL:
        raise ValueError("get_guild_usernames should only be called for channel messages.")
    data = aichan_storage.bot_data
    return data.get("guild_usernames", {}).get(context.guild_id, {}).get(context.user_id)


def update_guild_username(context: MessageContext, name: str, target_user_id: Optional[str] = None):
    if context.message_type != MessageType.CHANNEL:
        raise ValueError("update_guild_username should only be called for channel messages.")

    actual_target_user_id = target_user_id if target_user_id is not None else context.user_id
    data = aichan_storage.bot_data

    if "guild_usernames" not in data:
        data["guild_usernames"] = {}
    if context.guild_id not in data["guild_usernames"]:
        data["guild_usernames"][context.guild_id] = {}

    data["guild_usernames"][context.guild_id][actual_target_user_id] = name


class AiChanQQ(botpy.Client):

    def __init__(
            self,
            intents: Intents,
            timeout: int = 5,
            is_sandbox=False,
            log_config: Union[str, dict] = None,
            log_format: str = None,
            log_level: int = None,
            bot_log: Union[bool, None] = True,
            ext_handlers: Union[dict, List[dict], bool] = True,
    ):
        super().__init__(intents, timeout, is_sandbox, log_config, log_format, log_level, bot_log, ext_handlers)
        self.last_sent_channel_msg_timestamp: int = 0
        self.last_received_channel_msg_context: Optional[MessageContext] = None
        self.regular_messages : List[str] = []
        self.message_history = deque(maxlen=aichan_storage.bot_config["message_history_limit"])
        self.message_contexts : Dict[MessageContext, ContextState] = {}
        self.server = None
        self.online_servers : Dict[SocketHandler, ServerInfo] = {}


    async def add_context(self, context: MessageContext):
        """
        Add a command context to the bot, and start a background task to poll messages of the context and delete the context after a certain time.
        :param context: The context of the command, including source type, source ID, and message ID.
        """
        self.message_contexts[context] = ContextState()
        polling_and_deletion_task = asyncio.create_task(self.context_message_polling_and_deletion(context))
        # Add the task to the set of background tasks.
        # This is to prevent the task from midway being garbage collected and thus not being executed.
        background_tasks.add(polling_and_deletion_task)
        # When the task is done, remove it from the set of background tasks.
        polling_and_deletion_task.add_done_callback(background_tasks.discard)


    def try_add_context_message(self, context: MessageContext, msg: str):
        """
        Try to add a message to the context.
        If the context is not valid, the message will not be added and a warning will be logged.
        This function should be called for the following 2 scenarios:
        1. When a command feedback is sent from Minecraft Server to the bot.
        2. When a command feedback is generated by the bot itself (possibly due to permission reasons or command usage errors).
        :param context: The context of the command, including source type, source ID, and message ID.
        :param msg: The message to be added to the context.
        """
        if context not in self.message_contexts:
            logger.warning(f"Trying to add message {msg} to context {context}, but the context is not valid / already expired.")
            return
        self.message_contexts[context].messages.append(msg)


    async def try_send_context_messages(self, context: MessageContext):
        """
        Try to send messages of a context.
        If the context is not valid, the messages will not be sent and a warning will be logged.
        If the context is valid but there are no messages to be sent, nothing will be done.
        :param context: The context of the command.
        """
        if context not in self.message_contexts:
            logger.warning(f"Trying to send messages of context {context}, but the context is not valid / already expired.")
            return

        state = self.message_contexts[context]
        if len(state.messages) == 0:
            return

        combined_message = "\n".join(state.messages)
        state.messages.clear()

        if state.sequence >= 5:
            combined_message += "\n（若仍有后续消息，将被省略）"

        if context.message_type == MessageType.GROUP:
            try:
                await self.api.post_group_message(
                    group_openid=context.group_id,
                    msg_type=0,
                    msg_id=context.message_id,
                    # Group messages automatically add a "@user", so use a new line to avoid messing up the format.
                    content="\n" + combined_message,
                    msg_seq=state.sequence,
                )
                state.sequence += 1
            except Exception as e:
                logger.error(f"Failed to send group message: {e}")
            logger.info(f"Sent group message:\n{get_formatted_time()}[{context.group_id}] <-\n{combined_message}")
        elif context.message_type == MessageType.PRIVATE:
            try:
                await self.api.post_c2c_message(
                    openid=context.user_id,
                    msg_type=0,
                    msg_id=context.message_id,
                    content=combined_message,
                    # This parameter is int in Official document. WTF?
                    msg_seq=state.sequence,
                )
                state.sequence += 1
            except Exception as e:
                logger.error(f"Failed to send private message: {e}")
            logger.info(f"Sent private message:\n{get_formatted_time()}[{context.user_id}] <-\n{combined_message}")
        elif context.message_type == MessageType.CHANNEL:
            try:
                await self.api.post_message(
                    channel_id=context.channel_id,
                    msg_id=context.message_id,
                    content=combined_message,
                )
                state.sequence += 1
            except Exception as e:
                logger.error(f"Failed to send channel message: {e}")
            logger.info(f"Sent channel message:\n{get_formatted_time()}[{context.guild_id}][{context.channel_id}] <-\n{combined_message}")

    async def context_message_polling_and_deletion(self, context: MessageContext):
        """
        Polling for messages of a context and send them if needed, then delete the context after a certain time.
        The send action is done at the 0.25s, 0.5s, 1s, 2s, 4s, and deletion is done at the 8s.
        :param context: The context of the command.
        """
        await asyncio.sleep(0.25)
        await self.try_send_context_messages(context)
        await asyncio.sleep(0.25)
        await self.try_send_context_messages(context)
        await asyncio.sleep(0.5)
        await self.try_send_context_messages(context)
        await asyncio.sleep(1)
        await self.try_send_context_messages(context)
        await asyncio.sleep(2)
        await self.try_send_context_messages(context)
        await asyncio.sleep(4)
        del self.message_contexts[context]


    async def http_handle(self, request):
        if len(self.regular_messages) != 0:
            return web.Response(text="There are messages to be sent.", status=200)
        else:
            return web.Response(text="No messages are to be sent.", status=404)


    async def run_http_server(self):
        global HTTP_SERVER_PORT
        app = web.Application()
        app.router.add_get("/", self.http_handle)
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()

        site = aiohttp.web.TCPSite(runner, port=HTTP_SERVER_PORT)
        logger.info(f"Starting HTTP server on port {HTTP_SERVER_PORT}...")
        await site.start()

        while True:
            await asyncio.sleep(3600)  # Simulate long-running application


    async def regular_message_polling(self):
        global MESSAGE_POLLING_INTERVAL
        await asyncio.sleep(5)
        while True:
            await asyncio.sleep(MESSAGE_POLLING_INTERVAL)
            await self.try_send_regular_messages()


    # Send one message. No check will be done!
    async def send_regular_message(self, msg):
        target_channel_id = self.last_received_channel_msg_context.channel_id
        target_msg_id = self.last_received_channel_msg_context.message_id
        target_guild_id = self.last_received_channel_msg_context.guild_id
        try:
            await self.api.post_message(
                msg_id=target_msg_id,
                channel_id=target_channel_id,
                content=msg
            )
            self.last_sent_channel_msg_timestamp = get_unix_timestamp()
            logger.info(f"Sent channel message:\n{get_formatted_time()}[{target_guild_id}][{target_channel_id}] <-\n{msg}")

        except Exception as e:
            logger.error(f"Failed to send message: {e}")


    def get_regular_messages_with_limit(self, message_max_lines: int) -> str:
        combined_message = "\n".join(self.regular_messages[:message_max_lines])
        del self.regular_messages[:message_max_lines]
        return combined_message


    # Send all chat and information messages. No check will be done!
    async def send_regular_messages(self):
        config = aichan_storage.bot_config
        if len(self.regular_messages) != 0:
            combined_message = self.get_regular_messages_with_limit(config["message_max_lines"])
            await self.send_regular_message(combined_message)


    # Check for conditions and send messages if needed
    async def try_send_regular_messages(self):
        last_received_context = self.last_received_channel_msg_context
        last_sent_timestamp = self.last_sent_channel_msg_timestamp
        if last_received_context is None:
            return

        config = aichan_storage.bot_config
        now = get_unix_timestamp()

        if now - last_received_context.timestamp > config["message_threshold"]:
            return
        if now - last_sent_timestamp < config["message_interval"]:
            return
        await self.send_regular_messages()


    async def handle_command(self, cmd: str, context: MessageContext, title: str = "主人"):
        """
        Handle a command from a user.
        :param cmd: The command as a string.
        :param context: The context of the command.
        :param title: The title to address the user, default is "主人" (master).
        """
        sections = cmd.split()
        if len(sections) == 0:
            return

        config = aichan_storage.bot_config
        if sections[0] == "/say" or sections[0] == "s":
            # Sending messages to Minecraft servers is only allowed in guild channels.
            if context.message_type != MessageType.CHANNEL:
                return

            if len(sections) < 2:
                self.try_add_context_message(context, f"{title}，指令使用有误哦！请使用/say 内容")
                return

            new_guild_username = get_guild_username(context)
            if new_guild_username is None:
                self.try_add_context_message(context, f"{title}，你还没有绑定MC名字哦！")
                return

            msg = " ".join(sections[1:])
            prefix = config["channel_chat_prefix"]
            full_msg = f"{prefix} {new_guild_username}: {msg}"
            await self.server.broadcast_packet(
                SocketPacket(PacketType.BOT_CHAT_TO_SERVER,
        ["all", full_msg])
            )
            self.message_history.append(get_formatted_time("%H:%M") + remove_minecraft_color(full_msg))

        elif sections[0] == "/name" or sections[0] == "n":
            # Binding MC names is only allowed in guild channels.
            if context.message_type != MessageType.CHANNEL:
                return

            if len(sections) < 2:
                self.try_add_context_message(context, f"{title}，不能绑定空白名字哦！")
                return

            if is_at_section(sections[1]):
                if not is_admin(context):
                    self.try_add_context_message(context, f"{title}，你没有权限为别人绑定名字哦！")
                    return

                if len(sections) < 3:
                    self.try_add_context_message(context, f"{title}，不能为别人绑定空白名字哦！")
                    return

                new_guild_username = " ".join(sections[2:])
                target_user_id = get_user_id_from_at_section(sections[1])
                update_guild_username(context, new_guild_username, target_user_id)
                self.try_add_context_message(context, f"{title}，你已成功为用户{target_user_id}绑定MC名字 {new_guild_username} ！")
            else:
                old_guild_username = get_guild_username(context)
                # User can update name if they haven't bound a name before, or they are an admin.
                if (not is_admin(context)) and (old_guild_username is not None):
                    self.try_add_context_message(context, f"{title}，你已经绑定过了MC名字 {old_guild_username} ！请联系管理员修改！")
                    return

                new_guild_username = " ".join(sections[1:])
                update_guild_username(context, new_guild_username)
                self.try_add_context_message(context, f"{title}，你已成功绑定MC名字 {new_guild_username} ！")

        elif sections[0] == "/list" or sections[0] == "l":
            if len(sections) != 1:
                self.try_add_context_message(context, f"{title}，指令使用有误哦！请使用/list")
                return

            await self.server.broadcast_packet(SocketPacket(PacketType.BOT_LIST_REQUEST_TO_SERVER, [context.to_json()]))

        elif sections[0] == "/command" or sections[0] == "c":
            if not is_admin(context):
                self.try_add_context_message(context, f"{title}，你没有权限使用这个指令哦！")
                return

            if len(sections) < 3:
                self.try_add_context_message(context, f"{title}，指令使用有误哦！请使用/command 服务器代号 指令")
                return

            server_cmd = " ".join(sections[2:])
            await self.server.broadcast_packet(SocketPacket(
                PacketType.BOT_COMMAND_TO_SERVER,
                [context.to_json(), sections[1], server_cmd]
            ))

        elif sections[0] == "/ai" or sections[0] == "a":
            return

        elif sections[0] == "/remove" or sections[0] == "r":
            if not is_admin(context):
                self.try_add_context_message(context, f"{title}，你没有权限使用这个指令哦！")
                return

            if len(sections) != 2:
                self.try_add_context_message(context, f"{title}，指令使用有误哦！请使用/remove 关键词")
                return

            keyword = sections[1]
            keyword_processor.remove_keyword(keyword)
            self.try_add_context_message(context, f"{title}，关键词 {keyword} 已成功移除！")

        elif sections[0] == "/whitelist" or sections[0] == "w":
            if not is_admin(context):
                self.try_add_context_message(context, f"{title}，你没有权限使用这个指令哦！")
                return

            if len(sections) != 2:
                self.try_add_context_message(context, f"{title}，指令使用有误哦！请使用/whitelist ID")
                return

            mc_id = sections[1]
            server_cmd = "whitelist add " + mc_id
            await self.server.broadcast_packet(SocketPacket(
                PacketType.BOT_COMMAND_TO_SERVER,
                [context.to_json(), 'all', server_cmd]
            ))

        elif sections[0] == "/history" or sections[0] == "h":
            if len(sections) != 1:
                self.try_add_context_message(context, f"{title}，指令使用有误哦！请使用/history")
                return

            if len(self.message_history) == 0:
                self.try_add_context_message(context, f"{title}，当前没有历史消息哦！")
                return

            header = f"最近{len(self.message_history)}条消息如下："
            history_message = "\n".join(self.message_history)
            self.try_add_context_message(context, f"{header}\n{history_message}")

        elif sections[0] == "/ping" or sections[0] == "p":
            if len(sections) != 1:
                self.try_add_context_message(context, f"{title}，指令使用有误哦！请使用/ping")
                return

            if len(self.online_servers) == 0:
                self.try_add_context_message(context, f"{title}，当前没有在线服务器哦！")
                return

            header = f"当前有{len(self.online_servers)}个服务器在线："
            if is_admin(context):
                servers_message = "\n".join(
                    [f"{info.name}({info.trigger}/{info.broadcast_trigger})" for info in self.online_servers.values()]
                )
            else:
                servers_message = "，".join(
                    [f"{info.name}" for info in self.online_servers.values()]
                )

            self.try_add_context_message(context, f"{header}\n{servers_message}")


    # Listen to all guild messages
    async def on_message_create(self, message: Message):
        logger.info(f"Received channel message:\n{get_formatted_time()}[{message.guild_id}][{message.channel_id}][{message.author.id}] ->\n{message.content}")

        context = MessageContext(
            message_type=MessageType.CHANNEL,
            message_id=message.id,
            timestamp=get_unix_timestamp_from_iso8601(message.timestamp),
            guild_id=message.guild_id,
            channel_id=message.channel_id,
            user_id=message.author.id
        )
        if context not in self.message_contexts:
            await self.add_context(context)

        await self.handle_command(message.content, context, message.member.nick)

        self.last_received_channel_msg_context = context



    # Listen to guild messages that @ the bot
    async def on_at_message_create(self, message: Message):
        logger.info(f"Received channel message:\n{get_formatted_time()}[{message.guild_id}][{message.channel_id}][{message.author.id}] ->\n{message.content}")

        context = MessageContext(
            message_type=MessageType.CHANNEL,
            message_id=message.id,
            timestamp=get_unix_timestamp_from_iso8601(message.timestamp),
            guild_id=message.guild_id,
            channel_id=message.channel_id,
            user_id=message.author.id
        )
        if context not in self.message_contexts:
            await self.add_context(context)

        real_message = get_message_without_at(message.content)
        await self.handle_command(real_message, context, message.member.nick)

        self.last_received_channel_msg_context = context


    # Listen to group messages that @ the bot
    async def on_group_at_message_create(self, message: GroupMessage):
        logger.info(f"Received group message:\n{get_formatted_time()}[{message.group_openid}][{message.author.member_openid}] ->\n{message.content}")

        context = MessageContext(
            message_type=MessageType.GROUP,
            message_id=message.id,
            timestamp=get_unix_timestamp_from_rfc3339(message.timestamp),
            group_id=message.group_openid,
            user_id=message.author.member_openid
        )
        if context not in self.message_contexts:
            await self.add_context(context)

        await self.handle_command(message.content, context)


    # Listen to private messages
    async def on_c2c_message_create(self, message: C2CMessage):
        logger.info(f"Received private message:\n{get_formatted_time()}[{message.author.user_openid}] ->\n{message.content}")

        context = MessageContext(
            message_type=MessageType.PRIVATE,
            message_id=message.id,
            timestamp=get_unix_timestamp_from_rfc3339(message.timestamp),
            user_id=message.author.user_openid
        )
        if context not in self.message_contexts:
            await self.add_context(context)

        await self.handle_command(message.content, context)


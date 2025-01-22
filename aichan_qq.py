import asyncio

import aiohttp
from aiohttp import web
from botpy import logger
from datetime import datetime, timedelta
from typing import List, Union

import botpy
from botpy import Intents
from botpy.message import Message
from botpy.types.user import Member, User

import aichan_config
import keyword_processor
from socket_packet import SocketPacket, PacketType
from utils import get_unix_timestamp_from_iso8601, get_unix_timestamp, \
    get_message_without_at, is_at_section, get_user_id_from_at_section

MESSAGE_POLLING_INTERVAL = 0.5
HTTP_SERVER_PORT = 23000


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
        self.last_received_id: int = 0
        self.last_received_timestamp: int = 0
        self.last_send_timestamp: int = 0
        self.messages = []
        self.server = None

    async def http_handle(self, request):
        if len(self.messages) is not 0:
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

    async def message_polling(self):
        global MESSAGE_POLLING_INTERVAL
        await asyncio.sleep(5)
        while True:
            await asyncio.sleep(MESSAGE_POLLING_INTERVAL)
            await self.try_send_messages()

    async def hourly_push(self):
        config = aichan_config.bot_config
        push_hours = config["push_hours"]
        await asyncio.sleep(3600)
        while True:
            now = datetime.now()
            current_hour = now.hour

            if current_hour in push_hours:
                await self.send_messages(True)

            # Calculate the next run time
            next_run = now + timedelta(hours=1)
            next_run = next_run.replace(minute=0, second=0, microsecond=0)

            # Sleep until the next run
            sleep_time = (next_run - now).total_seconds()
            await asyncio.sleep(sleep_time)

    # Send one message. No check will be done!
    async def send_message(self, msg, active: bool = False):
        config = aichan_config.bot_config
        if active:
            try:
                await self.api.post_message(channel_id=str(config["channel_id"]), content=msg)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
        else:
            try:
                await self.api.post_message(msg_id=str(self.last_received_id), channel_id=str(config["channel_id"]),
                                            content=msg)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
        self.last_send_timestamp = get_unix_timestamp()
        logger.info(f"-> [{config['channel_id']}]\n{msg}")

    # Send all chat and information messages. No check will be done!
    async def send_messages(self, active: bool = False):
        config = aichan_config.bot_config
        if len(self.messages) != 0:
            new_message = self.get_messages_with_limit(config["message_max_lines"])
            await self.send_message(new_message, active)

    def get_messages_with_limit(self, message_max_lines: int) -> str:
        new_message = "\n".join(self.messages[:message_max_lines])
        del self.messages[:message_max_lines]
        return new_message

    # Check for conditions and send messages if needed
    async def try_send_messages(self):
        config = aichan_config.bot_config
        if get_unix_timestamp() - self.last_received_timestamp > config["message_threshold"]:
            return
        if get_unix_timestamp() - self.last_send_timestamp < config["message_interval"]:
            return
        await self.send_messages()

    async def handle_command(self, cmd: list, member: Member, user: User):
        config = aichan_config.bot_config
        always_reply: bool = bool(config["always_reply"])
        if cmd[0] == "/say" or cmd[0] == "s":
            if len(cmd) < 2:
                self.messages.append(f"{member.nick}，指令使用有误哦！请使用/say 内容")
                return
            if int(user.id) not in config["user_id"]:
                self.messages.append(f"{member.nick}，你还没有绑定MC名字哦！")
                return
            msg = " ".join(cmd[1:])
            prefix = config["channel_chat_prefix"]
            mc_id = config["user_id"][int(user.id)]
            await self.server.broadcast_packet(SocketPacket(PacketType.GROUP_CHAT_TO_SERVER,
                                                            ["all", f"{prefix} {mc_id}: {msg}"]))
            if always_reply:
                self.messages.append(f"{member.nick}，你的消息已发送！")
        elif cmd[0] == "/name" or cmd[0] == "n":
            if len(cmd) < 2:
                self.messages.append(f"{member.nick}，不能绑定空白名字哦！")
                return
            if is_at_section(cmd[1]):
                if int(user.id) not in config["admins"]:
                    self.messages.append(f"{member.nick}，你没有权限为别人绑定名字哦！")
                    return
                if len(cmd) < 3:
                    self.messages.append(f"{member.nick}，不能为别人绑定空白名字哦！")
                    return
                mc_id = " ".join(cmd[2:])
                target_user_id = get_user_id_from_at_section(cmd[1])
                config["user_id"][int(target_user_id)] = mc_id
                self.messages.append(f"{member.nick}，你已成功为用户{target_user_id}绑定MC名字 {mc_id} ！")
            else:
                if int(user.id) in config["user_id"]:
                    self.messages.append(f"{member.nick}，你已经绑定过了哦！请联系管理员修改！")
                    return
                mc_id = " ".join(cmd[1:])
                config["user_id"][int(user.id)] = mc_id
                self.messages.append(f"{member.nick}，你已成功绑定MC名字 {mc_id} ！")
        elif cmd[0] == "/list" or cmd[0] == "l":
            if len(cmd) != 1:
                self.messages.append(f"{member.nick}，指令使用有误哦！请使用/list")
                return
            await self.server.broadcast_packet(SocketPacket(PacketType.LIST_REQUEST_TO_SERVER, []))
            if always_reply:
                self.messages.append(f"{member.nick}，正在帮你查看服务器在线玩家！")
        elif cmd[0] == "/cmd" or cmd[0] == "c":
            if int(user.id) not in config["admins"]:
                self.messages.append(f"{member.nick}，你没有权限使用这个指令哦！")
                return
            if len(cmd) < 3:
                self.messages.append(f"{member.nick}，指令使用有误哦！请使用/cmd 服务器代号 指令")
                return
            server_cmd = " ".join(cmd[2:])
            await self.server.broadcast_packet(SocketPacket(PacketType.COMMAND_TO_SERVER,
                                                            [cmd[1], server_cmd]))
            if always_reply:
                self.messages.append(f"{member.nick}，你的指令已发送！")
        elif cmd[0] == "/ai":
            if always_reply:
                if len(self.messages) == 0:
                    await self.send_message(f"{member.nick}，最近没有消息哦！")
        elif cmd[0] == "/remove" or cmd[0] == "r":
            if int(user.id) not in config["admins"]:
                self.messages.append(f"{member.nick}，你没有权限使用这个指令哦！")
                return
            if len(cmd) != 2:
                self.messages.append(f"{member.nick}，指令使用有误哦！请使用/remove 关键词")
                return
            keyword_processor.remove_keyword(cmd[1])
            self.messages.append(f"{member.nick}，关键词 {cmd[1]} 已成功移除！")

    async def on_message_create(self, message: Message):
        logger.info(f"[{message.channel_id}] {message.author.id} -> \n{message.content}")
        config = aichan_config.bot_config
        self.last_received_id = message.id
        self.last_received_timestamp = get_unix_timestamp_from_iso8601(message.timestamp)
        config["guild_id"] = int(message.guild_id)
        config["channel_id"] = int(message.channel_id)

        sections = message.content.split()
        if len(sections) == 0:
            return

        await self.handle_command(sections, message.member, message.author)

    async def on_at_message_create(self, message: Message):
        config = aichan_config.bot_config
        self.last_received_id = message.id
        self.last_received_timestamp = get_unix_timestamp_from_iso8601(message.timestamp)
        config["guild_id"] = int(message.guild_id)
        config["channel_id"] = int(message.channel_id)

        sections = get_message_without_at(message.content).split()
        if len(sections) == 0:
            return

        await self.handle_command(sections, message.member, message.author)

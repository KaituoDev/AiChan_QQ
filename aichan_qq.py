import asyncio
from datetime import datetime, timedelta
from typing import List, Union

import botpy
from botpy import Intents
from botpy.message import Message
from botpy.types.user import Member, User

import aichan_config
from socket_packet import SocketPacket, PacketType
from utils import get_unix_timestamp_from_iso8601, get_unix_timestamp, concat_strings_with_limit, get_message_without_at

MESSAGE_POLLING_INTERVAL = 0.5

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
        self.last_received_id = 0
        self.last_received_timestamp = 0
        self.last_send_timestamp = 0
        self.server_chat = []
        self.server_information = []
        self.server = None


    async def message_polling(self):
        global MESSAGE_POLLING_INTERVAL
        await asyncio.sleep(5)
        while True:
            await asyncio.sleep(MESSAGE_POLLING_INTERVAL)
            await self.try_send_messages()

    async def hourly_push(self):
        config = aichan_config.bot_config
        push_hours = config["push_hours"]
        while True:
            now = datetime.now()
            current_hour = now.hour

            if current_hour in push_hours:
                await self.send_messages()

            # Calculate the next run time
            next_run = now + timedelta(hours=1)
            next_run = next_run.replace(minute=0, second=0, microsecond=0)

            # Sleep until the next run
            sleep_time = (next_run - now).total_seconds()
            await asyncio.sleep(sleep_time)

    # Send one message. No check will be done!
    async def send_message(self, msg):
        config = aichan_config.bot_config
        await self.api.post_message(msg_id=str(self.last_received_id), channel_id=str(config["channel_id"]), content=msg)
        self.last_send_timestamp = get_unix_timestamp()

    # Send all chat and information messages. No check will be done!
    async def send_messages(self):
        config = aichan_config.bot_config
        if len(self.server_chat) != 0:
            await self.send_message(concat_strings_with_limit(self.server_chat, config["message_max_lines"]))
            self.server_chat.clear()

        if len(self.server_information) != 0:
            await self.send_message(concat_strings_with_limit(self.server_information, config["message_max_lines"]))
            self.server_information.clear()

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
        if cmd[0] == "/say":
            if len(cmd) < 2:
                self.server_information.append(f"{member.nick}，指令使用有误哦！请使用/say 内容")
                return
            if int(user.id) not in config["user_id"]:
                self.server_information.append(f"{member.nick}，你还没有绑定MC名字哦！")
                return
            msg = " ".join(cmd[1:])
            prefix = config["channel_chat_prefix"]
            mc_id = config["user_id"][int(user.id)]
            await self.server.broadcast_packet(SocketPacket(PacketType.GROUP_CHAT_TO_SERVER,
                                                            ["all", f"{prefix} {mc_id}: {msg}"]))
        elif cmd[0] == "/name":
            if len(cmd) < 2:
                self.server_information.append(f"{member.nick}，不能绑定空白名字哦！")
                return
            mc_id = " ".join(cmd[1:])
            config["user_id"][int(user.id)] = mc_id
            self.server_information.append(f"{member.nick}，你已成功绑定MC名字 {mc_id} ！")
        elif cmd[0] == "/list":
            if len(cmd) != 1:
                self.server_information.append(f"{member.nick}，指令使用有误哦！请使用/list")
                return
            await self.server.broadcast_packet(SocketPacket(PacketType.LIST_REQUEST_TO_SERVER,[]))
        elif cmd[0] == "/cmd":
            if int(user.id) not in config["admins"]:
                self.server_information.append(f"{member.nick}，你没有权限使用这个指令哦！")
                return
            if len(cmd) < 3:
                self.server_information.append(f"{member.nick}，指令使用有误哦！请使用/cmd 服务器代号 指令")
                return
            server_cmd = " ".join(cmd[2:])
            await self.server.broadcast_packet(SocketPacket(PacketType.COMMAND_TO_SERVER,
                                                            [cmd[1], server_cmd]))
    async def on_at_message_create(self, message: Message):
        config = aichan_config.bot_config

        if int(message.guild_id) != config["guild_id"]:
            return
        if int(message.channel_id) != config["channel_id"]:
            return
        self.last_received_id = message.id
        self.last_received_timestamp = get_unix_timestamp_from_iso8601(message.timestamp)

        sections = get_message_without_at(message.content).split()
        if len(sections) == 0:
            return

        if not sections[0].startswith("/"):
            return

        await self.handle_command(sections, message.member, message.author)

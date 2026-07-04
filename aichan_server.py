import json
from word_filter_api import filter_text

from botpy import logger
from cryptography.fernet import Fernet
from websockets import ConnectionClosedError
from websockets.asyncio.server import serve

import aichan_storage
from aichan_qq import MessageContext, ServerInfo
from socket_packet import SocketPacket, PacketType
from utils import get_formatted_time, remove_minecraft_color, remove_url

UNPROCESSED_MESSAGE_PLACEHOLDER = "[消息过滤失败，请联系管理员！]"

class AiChanServer:
    from aichan_qq import AiChanQQ
    def __init__(self, bot: AiChanQQ, host: str, port: int, fernet: Fernet):
        self.connections = set()
        self.bot = bot
        self.host = host
        self.port = port
        self.server = None
        self.fernet = fernet
        bot.server = self

    async def broadcast_message(self, message):
        for websocket in self.connections:
            await websocket.send(message)

    async def start(self):
        logger.info("Trying to start server on " + str(self.host) + ":" + str(self.port) + "...")
        async with serve(self.handler, self.host, self.port) as server:
            self.server = server
            await server.serve_forever()

    async def handler(self, websocket):
        logger.info("A client just connected.")
        self.connections.add(websocket)
        try:
            async for message in websocket:
                decrypted_content = self.fernet.decrypt(message.encode("utf-8")).decode("utf-8")
                packet = SocketPacket.from_dict(json.loads(decrypted_content))

                if packet.packet_type == PacketType.SERVER_CHAT_TO_BOT:
                    trigger = packet.content[0]
                    message_content = packet.content[1]
                    packet_to_server = SocketPacket(PacketType.BOT_CHAT_TO_SERVER, [trigger, message_content])
                    await self.broadcast_packet(packet_to_server)
                    processed_message = remove_url(remove_minecraft_color(packet.content[1]))
                    filtered_message = await filter_text(processed_message)
                    if filtered_message is None:
                        filtered_message = UNPROCESSED_MESSAGE_PLACEHOLDER
                        logger.warning("Failed to filter message: " + processed_message)
                    if filtered_message != processed_message:
                        logger.warning("Message was filtered. Original: " + processed_message + " Filtered: " + filtered_message)
                    self.bot.regular_messages.append(get_formatted_time("%H:%M") + filtered_message)
                    self.bot.message_history.append(get_formatted_time("%H:%M") + filtered_message)

                elif packet.packet_type == PacketType.SERVER_INFORMATION_TO_BOT:
                    processed_message = remove_url(remove_minecraft_color(packet.content[0]))
                    filtered_message = await filter_text(processed_message)
                    if filtered_message is None:
                        filtered_message = UNPROCESSED_MESSAGE_PLACEHOLDER
                        logger.warning("Failed to filter message: " + processed_message)
                    if filtered_message != processed_message:
                        logger.warning("Message was filtered. Original: " + processed_message + " Filtered: " + filtered_message)
                    self.bot.regular_messages.append(get_formatted_time("%H:%M") + filtered_message)
                    self.bot.message_history.append(get_formatted_time("%H:%M") + filtered_message)

                elif packet.packet_type == PacketType.SERVER_COMMAND_FEEDBACK_TO_BOT:
                    context = MessageContext.from_json(packet.content[0])
                    feedback = remove_url(remove_minecraft_color(packet.content[1]))
                    filtered_feedback = await filter_text(feedback)
                    if filtered_feedback is None:
                        filtered_feedback = UNPROCESSED_MESSAGE_PLACEHOLDER
                        logger.warning("Failed to filter command feedback: " + feedback)
                    if filtered_feedback != feedback:
                        logger.warning("Command feedback was filtered. Original: " + feedback + " Filtered: " + filtered_feedback)
                    self.bot.try_add_context_message(context, filtered_feedback)

                elif packet.packet_type == PacketType.SERVER_HELLO_TO_BOT:
                    server_name = packet.content[0]
                    server_trigger = packet.content[1]
                    server_broadcast_trigger = packet.content[2]
                    self.bot.online_servers[websocket] = ServerInfo(
                        server_name, server_trigger, server_broadcast_trigger
                    )

                elif packet.packet_type == PacketType.SERVER_PLAYER_LOOKUP_REQUEST_TO_BOT:
                    mc_id = packet.content[0].lower()
                    session_id = packet.content[1]
                    data = aichan_storage.bot_data
                    banlist = data.get("manual_banlist", [])
                    whitelist = data.get("manual_whitelist", [])

                    if mc_id in banlist:
                        is_authorized, is_banned = False, True
                    elif mc_id in whitelist:
                        is_authorized, is_banned = True, False
                    else:
                        found = any(
                            username == mc_id
                            for username in data.get("usernames", {}).values()
                        )
                        is_authorized, is_banned = found, False

                    response = SocketPacket(PacketType.BOT_PLAYER_LOOKUP_RESULT_TO_SERVER,
                                           [mc_id, session_id, str(is_authorized).lower(), str(is_banned).lower()])
                    await self.broadcast_packet(response)

        except ConnectionClosedError:
            logger.warning("A client just disconnected.")
        except Exception as e:
            logger.warning("An exception was raised. A client just disconnected.")
            logger.warning(e)
        finally:
            self.bot.online_servers.pop(websocket, None)
            self.connections.discard(websocket)

    async def broadcast_packet(self, packet: SocketPacket):
        raw_content = json.dumps(packet.to_dict())
        encrypted_content = self.fernet.encrypt(raw_content.encode("utf-8")).decode("utf-8")
        await self.broadcast_message(encrypted_content)
import json
import logging

from botpy import logger
from cryptography.fernet import Fernet
from websockets import ConnectionClosedError
from websockets.asyncio.server import serve
from keyword_processor import filter_text
from socket_packet import SocketPacket, PacketType
from utils import get_formatted_time, remove_minecraft_color, remove_url


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
                    packet_to_server = SocketPacket(PacketType.GROUP_CHAT_TO_SERVER, [trigger, message_content])
                    await self.broadcast_packet(packet_to_server)
                    final_message = filter_text(remove_url(remove_minecraft_color(packet.content[1])))
                    self.bot.messages.append(get_formatted_time() + final_message)
                elif packet.packet_type == PacketType.SERVER_INFORMATION_TO_BOT:
                    final_message = filter_text(remove_url(remove_minecraft_color(packet.content[0])))
                    self.bot.messages.append(get_formatted_time() + final_message)

        except ConnectionClosedError:
            logger.warning("A client just disconnected.")
        except Exception as e:
            logger.warning("An exception was raised. A client just disconnected.")
            logger.warning(e)
        finally:
            self.connections.remove(websocket)

    async def broadcast_packet(self, packet: SocketPacket):
        raw_content = json.dumps(packet.to_dict())
        encrypted_content = self.fernet.encrypt(raw_content.encode("utf-8")).decode("utf-8")
        await self.broadcast_message(encrypted_content)

import asyncio
import json

from cryptography.fernet import Fernet
from websockets import ConnectionClosedError
from websockets.asyncio.server import serve
import logging

from socket_packet import SocketPacket, PacketType
from utils import get_formatted_time, remove_minecraft_color

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
        logging.warning("Trying to start server on " + str(self.host) + ":" + str(self.port) + "...")
        async with serve(self.handler, self.host, self.port) as server:
            self.server = server
            await server.serve_forever()
        logging.warning("Server stopped...")

    async def handler(self, websocket):
        logging.warning("A client just connected.")
        self.connections.add(websocket)
        try:
            async for message in websocket:
                decrypted_content = self.fernet.decrypt(message.encode("utf-8")).decode("utf-8")
                print(decrypted_content)
                packet = SocketPacket.from_dict(json.loads(decrypted_content))
                if packet.packet_type == PacketType.SERVER_CHAT_TO_BOT:
                    print(1)
                    trigger = packet.content[0]
                    message_content = packet.content[1]
                    packet_to_server = SocketPacket(PacketType.GROUP_CHAT_TO_SERVER, [trigger, message_content])
                    await self.broadcast_packet(packet_to_server)

                    self.bot.server_chat.append(get_formatted_time() + remove_minecraft_color(packet.content[1]))
                elif packet.packet_type == PacketType.SERVER_INFORMATION_TO_BOT:
                    print(2)
                    self.bot.server_information.append(get_formatted_time() + remove_minecraft_color(packet.content[0]))

        except ConnectionClosedError:
            logging.warning("A client just disconnected.")
        except Exception as e:
            logging.warning("An exception was raised. A client just disconnected.")
            logging.warning(e)
        finally:
            self.connections.remove(websocket)

    async def broadcast_packet(self, packet: SocketPacket):
        raw_content = json.dumps(packet.to_dict())
        encrypted_content = self.fernet.encrypt(raw_content.encode("utf-8")).decode("utf-8")
        await self.broadcast_message(encrypted_content)
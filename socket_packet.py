from enum import Enum


class PacketType(Enum):
    SERVER_HELLO_TO_BOT = 0
    SERVER_HEARTBEAT_TO_BOT = 1
    SERVER_CHAT_TO_BOT = 2
    SERVER_COMMAND_FEEDBACK_TO_BOT = 3
    SERVER_INFORMATION_TO_BOT = 4
    BOT_LIST_REQUEST_TO_SERVER = 5
    BOT_COMMAND_TO_SERVER = 6
    BOT_CHAT_TO_SERVER = 7


class SocketPacket:

    def __init__(self, packet_type, content: list):
        self.packet_type = packet_type
        self.content = content

    @classmethod
    def from_dict(cls, d: dict):
        return cls(PacketType[d["packetType"]], d["content"])

    def to_dict(self):
        result = {"packetType": self.packet_type.name, "content": self.content}
        return result

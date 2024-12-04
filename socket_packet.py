import json
from enum import Enum

class PacketType(Enum):
    HEARTBEAT_TO_BOT = 0
    SERVER_CHAT_TO_BOT = 1
    GROUP_CHAT_TO_SERVER = 2
    PLAYER_LOOKUP_REQUEST_TO_BOT = 3
    PLAYER_LOOKUP_RESULT_TO_SERVER = 4
    PLAYER_NOT_FOUND_TO_SERVER = 5
    LIST_REQUEST_TO_SERVER = 6
    COMMAND_TO_SERVER = 7
    SERVER_INFORMATION_TO_BOT = 8

class SocketPacket:

    def __init__(self, packet_type, content: list):
        self.packet_type = packet_type
        self.content = content

    @classmethod
    def from_dict(cls, d: dict):
        return cls(PacketType[d["packetType"]],  d["content"])

    def to_dict(self):
        result = {"packetType": self.packet_type.name, "content": self.content}
        return result
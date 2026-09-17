"""Compatibility helpers for QQ BotPy features not yet exposed by the SDK."""

from botpy.connection import ConnectionState
from botpy.message import GroupMessage


def enable_group_message_create() -> bool:
    """Add GROUP_MESSAGE_CREATE parsing when the installed SDK lacks it.

    qq_botpy 1.2.1 already exposes the GROUP_AND_C2C_EVENT intent, but its
    gateway parser only handles GROUP_AT_MESSAGE_CREATE. The new full group
    message event has the same basic payload shape and can reuse GroupMessage.

    Returns True when the compatibility parser is installed. If a future SDK
    provides native support, this function leaves it untouched and returns
    False.
    """
    if hasattr(ConnectionState, "parse_group_message_create"):
        return False

    def parse_group_message_create(self, payload):
        message = GroupMessage(self.api, payload.get("id"), payload.get("d", {}))
        self._dispatch("group_message_create", message)

    ConnectionState.parse_group_message_create = parse_group_message_create
    return True

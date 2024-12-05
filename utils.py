import re
from datetime import datetime


def remove_minecraft_color(message: str) -> str:
    return re.sub(r'[&§][0-9a-fk-or]', '', message)


def get_formatted_time() -> str:
    current_time = datetime.now().strftime("%H:%M")
    return f"[{current_time}]"


def get_unix_timestamp_from_iso8601(iso8601: str) -> int:
    return int(datetime.fromisoformat(iso8601).timestamp())


def get_unix_timestamp() -> int:
    return int(datetime.now().timestamp())


def get_message_without_at(msg: str) -> str:
    pattern = r"<@!\d+>"
    return re.sub(pattern, "", msg)


def concat_strings_with_limit(strings: list, max_lines: int) -> str:
    if len(strings) <= max_lines:
        return '\n'.join(strings)
    prefix = f"已隐藏更早的{len(strings) - max_lines}条消息"
    sublist = strings[(len(strings) - max_lines):len(strings)]
    return prefix + '\n' + '\n'.join(sublist)

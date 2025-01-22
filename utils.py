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


def remove_url(msg: str) -> str:
    pattern = r"[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
    return re.sub(pattern, "[链接已屏蔽]", msg)


# Return true if given section is @user
def is_at_section(section: str) -> bool:
    pattern = r"<@!\d+>"
    return bool(re.fullmatch(pattern, section))


def get_user_id_from_at_section(section: str) -> str | None:
    pattern = r"<@!(\d+)>"
    match = re.search(pattern, section)
    return match.group(1) if match else None
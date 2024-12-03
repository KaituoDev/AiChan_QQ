import re
from datetime import datetime


def remove_minecraft_color(message: str) -> str:
    return re.sub(r'[&§][0-9a-fk-or]', '', message)

def get_formatted_time() -> str:
    current_time = datetime.now().strftime("%H:%M")
    return f"[{current_time}]"
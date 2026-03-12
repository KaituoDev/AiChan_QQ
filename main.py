import asyncio
import os
import warnings

import botpy
from botpy.logging import DEFAULT_FILE_HANDLER, DEFAULT_FILE_FORMAT
from cryptography.fernet import Fernet

import aichan_storage

from aichan_qq import AiChanQQ
from aichan_server import AiChanServer

LOGS_DIR_PATH = os.path.join(os.getcwd(), "logs")

os.makedirs(LOGS_DIR_PATH, exist_ok=True)

# Change log file path
DEFAULT_FILE_HANDLER["filename"] = os.path.join(LOGS_DIR_PATH, "%(name)s.log")
# Use default log format
DEFAULT_FILE_HANDLER["format"] = DEFAULT_FILE_FORMAT

# Ignore warnings due to force stop
warnings.filterwarnings(
    "ignore",
    message="coroutine '.*' was never awaited",
    category=RuntimeWarning
)

warnings.filterwarnings(
    "ignore",
    message="Enable tracemalloc to get the object allocation traceback",
    category=RuntimeWarning
)


async def auto_save_data():
    config = aichan_storage.bot_config
    while True:
        await asyncio.sleep(config["data_auto_save_interval"])
        aichan_storage.save_data()


async def handle_user_input():
    while True:
        user_input = await asyncio.to_thread(input)
        if user_input.strip().lower() == "stop":
            print("Stopping...")
            os._exit(0)
        else:
            print("Unknown command. Use 'stop' to stop the bot.")


async def main():
    aichan_storage.load_config()
    aichan_storage.load_data()

    config = aichan_storage.bot_config
    app_id = config["app_id"]
    secret = config["secret"]

    fernet = Fernet(config["fernet_key"].encode("utf-8"))

    intents = botpy.Intents(
        public_guild_messages=True,
        guild_messages=True,
        direct_message=True,
        public_messages=True,
    )
    bot = AiChanQQ(intents=intents, ext_handlers=DEFAULT_FILE_HANDLER)

    server = AiChanServer(bot, config["server_address"], config["port"], fernet)

    tasks = [
        bot.start(appid=app_id, secret=secret),
        bot.regular_message_polling(),
        server.start(),
        auto_save_data(),
        handle_user_input(),
        bot.run_http_server()
    ]
    try:
        await asyncio.gather(*tasks)
    except SystemExit:
        pass


if __name__ == "__main__":
    asyncio.run(main())

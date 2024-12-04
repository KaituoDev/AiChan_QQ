import asyncio

import botpy
from cryptography.fernet import Fernet

import aichan_config
from aichan_qq import AiChanQQ
from aichan_server import AiChanServer

CONFIG_FILE_PATH = "config.yml"

async def auto_save_config():
    global CONFIG_FILE_PATH
    config = aichan_config.bot_config
    while True:
        await asyncio.sleep(config["config_auto_save_interval"])
        aichan_config.save_config(CONFIG_FILE_PATH)

async def main():
    global CONFIG_FILE_PATH
    aichan_config.load_config(CONFIG_FILE_PATH)

    config = aichan_config.bot_config
    app_id = str(config["app_id"])
    secret = config["secret"]

    fernet = Fernet(config["fernet_key"].encode("utf-8"))

    intents = botpy.Intents(public_guild_messages=True)
    bot = AiChanQQ(intents=intents)

    server = AiChanServer(bot, config["server_address"], config["port"], fernet)
    #await asyncio.gather(server.start())
    await asyncio.gather(bot.start(appid=app_id, secret=secret), bot.message_polling(), server.start(), auto_save_config())

if __name__ == "__main__":
    asyncio.run(main())
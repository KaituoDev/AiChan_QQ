import botpy
import yaml
import config

from aichan_qq import AiChanQQ

if __name__ == "__main__":
    config.load_config("config.yml")
    app_id = config.bot_config["app_id"]
    secret = config.bot_config["secret"]

    intents = botpy.Intents(public_guild_messages=True)
    client = AiChanQQ(intents=intents)
    client.run(appid=app_id, secret=secret)
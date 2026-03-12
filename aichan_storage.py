import yaml

CONFIG_FILE_PATH = "config.yml"
DATA_FILE_PATH = "data.yml"

bot_config = {}
bot_data = {}



def load_config():
    global bot_config
    with open(CONFIG_FILE_PATH, 'r', encoding="utf-8") as f:
        bot_config = yaml.safe_load(f)


def load_data():
    global bot_data
    with open(DATA_FILE_PATH, 'r', encoding="utf-8") as f:
        bot_data = yaml.safe_load(f)


def save_data():
    global bot_data
    with open(DATA_FILE_PATH, 'w', encoding="utf-8") as f:
        yaml.dump(bot_data, f, allow_unicode=True, default_flow_style=False)

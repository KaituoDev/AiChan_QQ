import yaml

bot_config = {}

def load_config(file_path):
    global bot_config
    with open(file_path, 'r', encoding="utf-8") as f:
        bot_config = yaml.safe_load(f)

def save_config(file_path):
    global bot_config
    with open(file_path, 'w', encoding="utf-8") as f:
        yaml.dump(bot_config, f, allow_unicode=True, default_flow_style=False)
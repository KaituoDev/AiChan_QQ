import yaml

bot_config = []

def load_config(file_path):
    global bot_config
    with open(file_path, 'r') as f:
        bot_config = yaml.safe_load(f)
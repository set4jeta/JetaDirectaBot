# tracking/soloq/channel_config.py
import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "notify_config.json")

def load_channel_ids() -> dict[int, int]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        return {int(k): v for k, v in data.items()}

def save_channel_id(guild_id: int, channel_id: int):
    data = load_channel_ids()
    data[guild_id] = channel_id
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
        




def remove_channel_id(guild_id: int):
    """
    Elimina el canal de notificación asociado a un servidor.
    """
    if not os.path.exists(CONFIG_PATH):
        return False

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    str_guild_id = str(guild_id)
    if str_guild_id in data:
        del data[str_guild_id]
        with open(CONFIG_PATH, "w", encoding="utf-8") as f2:
            json.dump(data, f2, ensure_ascii=False, indent=2)
        return True
    return False
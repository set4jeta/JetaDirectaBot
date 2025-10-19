# tracking/soloq/notifier.py
import json
import os
import time
import nextcord

ANNOUNCED_GAMES_PATH = os.path.join(os.path.dirname(__file__), "announced_games.json")
EXPIRATION = 2 * 3600  # 2 horas

def load_announced_games():
    if os.path.exists(ANNOUNCED_GAMES_PATH):
        with open(ANNOUNCED_GAMES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_announced_games(data: dict):
    with open(ANNOUNCED_GAMES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def already_announced(announced_map: dict, game_id: int, channel_id: int) -> bool:
    chan_map = announced_map.get(str(channel_id), {})
    return str(game_id) in chan_map

def mark_announced(announced_map: dict, game_id: int, channel_id: int):
    chan_map = announced_map.setdefault(str(channel_id), {})
    chan_map[str(game_id)] = int(time.time())

def clean_old_announcements(announced_map: dict):
    now = int(time.time())
    for chan_id in list(announced_map):
        chan_map = announced_map[chan_id]
        announced_map[chan_id] = {
            gid: ts for gid, ts in chan_map.items() if now - ts < EXPIRATION
        }

async def notify_channel(channel, embed, bat_path=None, files=None):
    try:
        to_send = []

        if files:
            # Esto evita el problema de archivos cerrados
            for f in files:
                to_send.append(nextcord.File(f.fp.name, filename=f.filename))

        if bat_path:
            to_send.append(nextcord.File(bat_path, filename="spectate_lol.bat"))

        await channel.send(
            content="⬇️ **Archivo para espectar la partida:**" if bat_path else None,
            embed=embed,
            files=to_send if to_send else None
        )
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo enviar mensaje: {e}")
        return False


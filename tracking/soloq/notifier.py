# tracking/soloq/notifier.py
"""Registro de qué partidas ya se anunciaron, por canal.

Nota sobre `notify_channel`
---------------------------
Aquí había una función `notify_channel(channel, embed, bat_path, files)` que no
la llamaba **nadie** (comprobado con una búsqueda en todo el proyecto). El envío
real lo hace `active_game_checker._notificar_a_canales`, y tiene que hacerlo él
porque necesita dos cosas que esta función no podía saber: el embed correcto
según el idioma de cada servidor y reabrir los adjuntos entre canal y canal
(nextcord cierra el descriptor tras cada envío).

Se ha quitado en vez de traducirla: era la única cadena en español que quedaba
en este módulo y mantener una copia muerta de la lógica de envío es justo la
forma en la que dos caminos acaban divergiendo.
"""

import json
import os
import time

from utils.logger import get_logger

log = get_logger("tracking.soloq.notifier")

ANNOUNCED_GAMES_PATH = os.path.join(os.path.dirname(__file__), "announced_games.json")
EXPIRATION = 2 * 3600  # 2 horas

def load_announced_games():
    """Mapa `{canal: {id_partida: hora}}`, o `{}` si el fichero no sirve.

    Tolera fichero corrupto o de 0 bytes a propósito. Esto se leía con
    `json.load` a pelo y la llamada está en `ActiveGameTracker.__init__`, así
    que un JSON ilegible **no daba un aviso perdido: tiraba el arranque del
    tracker entero**. Pasó de verdad el 03-09-2026: el disco se quedó sin
    espacio, `save_announced_games` truncó el fichero a 0 bytes y el siguiente
    arranque habría muerto con `JSONDecodeError`.

    Perder este fichero no cuesta nada —caduca a las 2 h por diseño— así que
    empezar de cero es siempre preferible a no arrancar. Como mucho se repite
    un aviso ya enviado.
    """
    if not os.path.exists(ANNOUNCED_GAMES_PATH):
        return {}
    try:
        with open(ANNOUNCED_GAMES_PATH, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(
            "%s ilegible (%s); se empieza con el registro vacío. "
            "Como mucho se repetirá algún aviso de la última hora.",
            ANNOUNCED_GAMES_PATH, exc,
        )
        return {}
    return datos if isinstance(datos, dict) else {}

def save_announced_games(data: dict):
    """Vuelca el registro de forma atómica.

    Se escribe en `.tmp` y se hace `os.replace` por el mismo motivo que en
    `utils/safe_json.py`: abrir el destino en modo `"w"` lo trunca *antes* de
    saber si el volcado va a caber. Con el disco lleno eso deja el fichero en 0
    bytes y se pierde el registro bueno. Además el bot recibe SIGTERM de Render
    en cada despliegue, y ese es el otro momento en el que un volcado se corta
    a medias.
    """
    tmp = ANNOUNCED_GAMES_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ANNOUNCED_GAMES_PATH)
    except OSError as exc:
        log.error(
            "No se pudo guardar %s: %s. Se conserva el fichero anterior.",
            ANNOUNCED_GAMES_PATH, exc,
        )
        try:
            os.remove(tmp)
        except OSError:
            pass

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

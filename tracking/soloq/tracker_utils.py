"""Filtros para decidir qué partidas son notificables.

Con la key antigua el cuello de botella era no gastar peticiones; con la nueva
el problema contrario es no inundar el canal con partidas irrelevantes. Este
filtro es lo que evita que el bot avise de partidas normales, ARAM o modos de
rotación.
"""

from __future__ import annotations

import os

from utils.logger import get_logger

log = get_logger("tracking.tracker_utils")

# Colas que se consideran relevantes para seguir a jugadores de SoloQ:
#   400 = Normal (Draft), 420 = SoloQ, 430 = Normal (Blind), 440 = Flex
DEFAULT_VALID_QUEUES = {400, 420, 430, 440}

# Se puede ampliar sin tocar el código, p. ej.:
#   TRACKER_QUEUES=400,420,430,440,1750   (1750 = Arena, verificado con la sonda)
#   TRACKER_MODES=CLASSIC,CHERRY
def _env_set(name: str, default: set[int] | set[str]):
    raw = os.getenv(name)
    if not raw:
        return default
    values = {v.strip() for v in raw.split(",") if v.strip()}
    return {int(v) if v.lstrip("-").isdigit() else v for v in values}


VALID_QUEUES = _env_set("TRACKER_QUEUES", DEFAULT_VALID_QUEUES)
VALID_MODES = _env_set("TRACKER_MODES", {"CLASSIC"})


def is_valid_game(game: dict, player_name: str = "", puuid: str = "") -> bool:
    """True si la partida cumple los filtros configurados.

    Antes esto imprimía una línea por cada partida descartada; con decenas de
    jugadores eso saturaba la consola. Ahora va a nivel debug.
    """
    game_type = game.get("gameType")
    game_mode = game.get("gameMode")
    queue_id = game.get("gameQueueConfigId")

    valid = (
        game_type == "MATCHED"
        and game_mode in VALID_MODES
        and queue_id in VALID_QUEUES
    )

    if not valid:
        log.debug(
            "Descartada %s (%s): gameType=%s gameMode=%s queueId=%s",
            player_name or "?", (puuid or "")[:12], game_type, game_mode, queue_id,
        )

    return valid

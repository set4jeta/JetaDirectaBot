"""Caché en memoria de las partidas en curso detectadas por el tracker.

Guarda la respuesta completa de `spectator-v5` junto con el instante en que se
recibió, para que `!live` y `!match` puedan responder sin volver a preguntar a
Riot. `utils.game_clock.desde_cache` es quien interpreta los tiempos.

Nota sobre `game_length`: es el reloj del **servidor de espectadores**, no el de
la partida. Va unos 3 minutos por detrás y arranca en negativo. Se guarda tal
cual viene y no se normaliza aquí, porque quien lo necesita ya sabe qué es.
"""

from __future__ import annotations

import time

from utils.logger import get_logger

log = get_logger("tracking.active_game_cache")

# Estructura:
#   {puuid: {"active_game": dict, "timestamp": float,
#            "game_length": int | None, "ranked_data_map": dict (opcional)}}
ACTIVE_GAME_CACHE: dict[str, dict] = {}
ACTIVE_GAME_CACHE_BY_NAME: dict[str, dict] = {}


def _entrada(active_game: dict, ranked_data_map: dict | None = None) -> dict:
    game_length = active_game.get("gameLength")
    entrada = {
        "active_game": active_game,
        "timestamp": time.time(),
        "game_length": game_length if isinstance(game_length, int) else None,
    }
    if ranked_data_map is not None:
        entrada["ranked_data_map"] = ranked_data_map
    return entrada


def set_active_game(puuid: str, active_game: dict, player_name: str | None = None) -> None:
    # Esto era un `print()`: con 80 cuentas revisadas cada 30 s ensuciaba la
    # consola y en Render se iba entero al log de stdout.
    log.debug("Caché de partida actualizada para %s...", (puuid or "")[:12])
    entrada = _entrada(active_game)
    ACTIVE_GAME_CACHE[puuid] = entrada
    if player_name:
        ACTIVE_GAME_CACHE_BY_NAME[player_name.lower()] = entrada


def set_active_game_with_ranked(
    puuid: str, active_game: dict, ranked_data_map: dict, player_name: str
) -> None:
    log.debug("Caché de partida (con rangos) actualizada para %s...", (puuid or "")[:12])
    entrada = _entrada(active_game, ranked_data_map)
    ACTIVE_GAME_CACHE[puuid] = entrada
    if player_name:
        ACTIVE_GAME_CACHE_BY_NAME[player_name.lower()] = entrada


def get_active_game_cache(puuid: str) -> dict | None:
    return ACTIVE_GAME_CACHE.get(puuid)


def get_active_game_cache_by_name(player_name: str) -> dict | None:
    return ACTIVE_GAME_CACHE_BY_NAME.get((player_name or "").lower())


def olvidar(puuid: str, player_name: str | None = None) -> None:
    """Quita una cuenta de la caché (ya no está en partida).

    También limpia el índice por nombre: antes solo se borraba de
    `ACTIVE_GAME_CACHE` (con `pop` desde el tracker), así que la entrada por
    nombre sobrevivía y `!match` podía servir una partida terminada al caer al
    respaldo por nombre.
    """
    entrada = ACTIVE_GAME_CACHE.pop(puuid, None)
    if player_name:
        ACTIVE_GAME_CACHE_BY_NAME.pop(player_name.lower(), None)
        return
    if entrada is None:
        return
    for nombre, valor in list(ACTIVE_GAME_CACHE_BY_NAME.items()):
        if valor is entrada:
            ACTIVE_GAME_CACHE_BY_NAME.pop(nombre, None)

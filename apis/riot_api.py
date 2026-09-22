"""Capa de compatibilidad sobre `apis.riot_client`.

Este módulo existía antes con sus propios headers, su propia sesión de aiohttp
y sin rate limiting. Lo mantengo porque hay varios módulos que lo importan
(`live_command`, `retry_handler`, `register_player_commands`, `update_puuids`...),
pero ahora **todo se delega al cliente central**, así que esos módulos pasan a
tener rate limiting, reintentos y el User-Agent correcto sin cambiar una línea.

El parámetro `session` se sigue aceptando por compatibilidad, pero se ignora:
la sesión vive en el cliente.

Sobre `platform`
----------------

Las tres funciones que consultan un servidor concreto (`get_active_game`,
`get_ranked_data`, `get_soloq_rank`) aceptan ahora `platform`. Antes no, así que
el cliente caía a `DEFAULT_PLATFORM` (euw1) y las cuentas de KR, NA1 o BR1
—48 de las 172 seguidas— contestaban 404: `!match` decía "no está en partida"
aunque el jugador estuviera jugando. Es opcional para no romper a los llamadores
antiguos, pero quien conozca la cuenta debe pasarla.

Esta capa es provisional. En fases posteriores conviene migrar los llamadores a
`apis.riot_client` directamente y borrar este archivo.
"""

from __future__ import annotations

from typing import Any

from apis.riot_client import RiotApiError, get_riot_client, normalizar_plataforma
from utils.logger import get_logger

log = get_logger("apis.riot_api")

__all__ = [
    "get_puuid_from_riot_id",
    "get_active_game",
    "get_ranked_data",
    "get_soloq_rank",
    "RIOT_BASE_URL",
    "EU_BASE_URL",
]

# Conservadas por si algún módulo las importa.
RIOT_BASE_URL = "https://europe.api.riotgames.com"
EU_BASE_URL = "https://euw1.api.riotgames.com"


async def get_puuid_from_riot_id(
    game_name: str, tag_line: str, session: Any = None
) -> tuple[str | None, int]:
    """Devuelve (puuid, status). `session` se ignora, se acepta por compatibilidad."""
    client = await get_riot_client()
    try:
        puuid = await client.get_puuid(game_name, tag_line)
    except RiotApiError as exc:
        log.debug("by-riot-id %s#%s -> %s", game_name, tag_line, exc.status)
        return None, exc.status
    return (puuid, 200) if puuid else (None, 404)


async def get_active_game(
    puuid: str, session: Any = None, platform: str | None = None
) -> tuple[dict | None, int]:
    """Devuelve (datos_partida, status). 404 significa que no está en partida."""
    client = await get_riot_client()
    plataforma = normalizar_plataforma(platform)
    try:
        game = await client.get_active_game(puuid, platform=plataforma)
    except RiotApiError as exc:
        # 400 = PUUID corrupto. Se propaga el código para que el llamador pueda
        # marcar la cuenta como stale en lugar de reintentar sin fin.
        log.debug("spectator-v5 para %s... (%s) -> %s", puuid[:12], plataforma, exc.status)
        return None, exc.status
    return (game, 200) if game else (None, 404)


async def get_ranked_data(
    puuid: str, session: Any = None, platform: str | None = None
) -> list | None:
    """Entradas de liga de la cuenta, o None si no hay datos."""
    client = await get_riot_client()
    try:
        return await client.get_league_entries(puuid, normalizar_plataforma(platform))
    except RiotApiError as exc:
        log.debug("league-v4 para %s... -> %s", puuid[:12], exc.status)
        return None


async def get_soloq_rank(
    puuid: str, session: Any = None, platform: str | None = None
) -> dict | None:
    """Entrada de RANKED_SOLO_5x5 de la cuenta, o None."""
    client = await get_riot_client()
    try:
        return await client.get_soloq_rank(puuid, normalizar_plataforma(platform))
    except RiotApiError as exc:
        log.debug("league-v4 (soloq) para %s... -> %s", puuid[:12], exc.status)
        return None

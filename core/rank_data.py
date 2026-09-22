"""Utilidades de rangos y construcción del ranking.

El almacén persistente vive en `core/rank_store.py`. Aquí solo quedan los
envoltorios que usa el resto del bot (`get_cached_rank`, `save_rank_data`,
`get_rank_from_ranked_data`) y la construcción del ranking.

Cambio importante de comportamiento
-----------------------------------

`get_cached_rank` ya **no** devuelve cualquier entrada del histórico: solo la
devuelve si es reciente (`RANK_CACHE_MAX_AGE`). Antes daba por bueno un rango
guardado hacía un año, así que los embeds podían enseñar el Elo que un jugador
tenía en julio de 2025 como si fuera el de hoy. Si está caducado se devuelve
`None` y el llamador lo pide a la API, que es lo que ya hacía cuando no había
nada cacheado.
"""

import json
import os
import time
import asyncio

import aiohttp

import config
from core import health as salud
from core import rank_store
from tracking.soloq.accounts_io import load_tracked_accounts
from utils.cache_utils import save_ranking_cache, load_puuid_cache
from utils.logger import get_logger
from apis.dpm_api import (
    LIGAS,
    fetch_champion_stats,
    fetch_league_leaderboard,
    fetch_lec_leaderboard,
    fetch_pro_leaderboard,
    get_rank_from_dpmlol,
)

log = get_logger("core.rank_data")

RANKED_DATA_FILE = rank_store.RANKED_DATA_FILE


def get_cached_rank(account, max_edad: int | None = None):
    """Rango cacheado de una cuenta, solo si sigue siendo válido."""
    puuid = getattr(account, "puuid", None)
    if not puuid:
        return None
    return rank_store.obtener_fresco(puuid, max_edad)


def save_rank_data(account) -> bool:
    """Anota el rango de una cuenta en el histórico.

    La escritura es diferida: se acumula y se vuelca cada
    `RANK_FLUSH_INTERVAL` segundos. Antes cada llamada reescribía los 316 KB
    del fichero completo, así que un `!team` de 25 cuentas escribía casi 8 MB.
    """
    puuid = getattr(account, "puuid", None)
    rank = getattr(account, "rank", None)
    if not puuid or not isinstance(rank, dict):
        return False
    return rank_store.guardar(puuid, rank)


def get_rank_from_ranked_data(puuid):
    """Último rango conocido, aunque sea antiguo.

    Lo usa el ranking, que prefiere un dato viejo a una casilla vacía.
    """
    return rank_store.obtener_crudo(puuid)


def flush_rank_data(forzar: bool = True) -> bool:
    """Vuelca a disco lo que quede pendiente. Se llama al cerrar el bot."""
    return rank_store.volcar(forzar=forzar)


# Abreviaciones de campeones
CHAMPION_ABBR = {
    "Twisted Fate": "Twisted F",
    "Miss Fortune": "Miss F",
    "Ezreal": "Ez",
    "Katarina": "Kata",
    "Nautilus": "Nauty",
    "Dr. Mundo": "Dr.Mundo",
    "Tristana": "Trist",
    # Añade más aquí si quieres
}

def abbreviate_champion_name(champ_name):
    return CHAMPION_ABBR.get(champ_name, champ_name)





CACHE_TTL = 1800  # 30 minutos
RANKING_CACHE_FILE = "ranking_cache.json"



def build_lec_index(lec_data):
    # Indexa por (gameName.lower(), tagLine.lower())
    index = {}
    for p in lec_data:
        game = p.get("gameName", "")
        tag = p.get("tagLine", "")
        if game and tag:
            index[(game.lower(), tag.lower())] = p
    return index

def build_pro_index(pro_data):
    # Indexa por (gameName.lower(), tagLine.lower())
    index = {}
    for p in pro_data:
        game = p.get("gameName", "")
        tag = p.get("tagLine", "")
        if game and tag:
            index[(game.lower(), tag.lower())] = p
    return index









async def build_and_cache_ranking(liga: str = "lec"):
    """Construye el ranking de una liga y lo deja en caché.

    Reescrito. La versión anterior exigía, para **cada** jugador, tener a la vez
    un PUUID de dpm.lol en `puuid_cache.json` y un PUUID de Riot en la cuenta,
    y hacía `break` en la primera coincidencia en vez de en la mejor. De los 46
    jugadores seguidos solo 33 cumplían las dos condiciones, así que el ranking
    salía incompleto incluso cuando la red funcionaba. Además cruzaba tres
    fuentes (`lec_leaderboard`, `pro_leaderboard` y `champion_stats` por jugador)
    para reconstruir datos que el leaderboard de liga ya trae juntos.

    Ahora se pide una sola cosa: `/v1/esport/soloq/leagues/<liga>/leaderboard`,
    que devuelve por jugador displayName, team, lane, tier, rank, leaguePoints,
    wins, losses, kda y mostChamps. Una petición, cero dependencia de los dos
    espacios de PUUID, y sirve igual para LEC que para LCK o LPL.
    """
    from cache.champion_cache import CHAMPION_ID_TO_NAME

    liga = (liga or "lec").lower().strip()
    entradas = await fetch_league_leaderboard(liga)
    if not entradas:
        log.warning("El leaderboard de %s vino vacío; no se cachea nada.", liga.upper())
        # Vacío sin excepción es el fallo silencioso típico de dpm.lol: si no se
        # apunta, `/ranking` responde con la caché vieja y nadie se enteraría.
        salud.registrar("leaderboard", False, f"{liga.upper()} vino vacío")
        return []

    ranking = []
    for e in entradas:
        wins = e.get("wins") or 0
        losses = e.get("losses") or 0
        partidas = wins + losses

        champs = [
            abbreviate_champion_name(CHAMPION_ID_TO_NAME.get(str(cid), str(cid)))
            for cid in (e.get("mostChamps") or [])[:3]
        ]

        ranking.append({
            "player": e.get("displayName") or e.get("gameName") or "?",
            "team": (e.get("team") or "").upper(),
            "riot_id": {
                "game_name": e.get("gameName", ""),
                "tag_line": e.get("tagLine", ""),
            },
            "role": e.get("lane") or "",
            "tier": e.get("tier") or "Unranked",
            "division": e.get("rank") or "",
            "lp": e.get("leaguePoints") or 0,
            "winrate": (wins / partidas * 100) if partidas else 0,
            "kda": round(e.get("kda") or 0, 2),
            "best_champions": champs,
            "profile_icon": e.get("profileIcon"),
            "wins": wins,
            "losses": losses,
            "total_games": partidas,
            "puuid": e.get("puuid"),
        })

    # Orden por Elo real: el tier manda sobre los LP, porque 90 LP en Diamante no
    # están por encima de 10 LP en Challenger. Antes se ordenaba solo por `lp`.
    ranking.sort(key=lambda x: (_peso_tier(x["tier"]), x["lp"]), reverse=True)

    save_ranking_cache(ranking, liga)
    log.info("Ranking de %s: %d jugadores.", liga.upper(), len(ranking))
    salud.registrar("leaderboard", True, f"{liga.upper()}: {len(ranking)} jugadores")
    return ranking


#: Orden de los tiers de LoL, de menor a mayor. Un tier desconocido va al final.
_ORDEN_TIERS = [
    "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD",
    "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER",
]


def _peso_tier(tier: str | None) -> int:
    if not tier:
        return -1
    try:
        return _ORDEN_TIERS.index(tier.strip().upper())
    except ValueError:
        return -1

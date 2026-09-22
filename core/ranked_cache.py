"""Caché en memoria de rangos, en primer nivel delante de la API.

Durante una misma pasada del tracker se consulta el rango de los 10
participantes de cada partida. Sin caché, la misma cuenta se pediría varias
veces en pocos segundos.

Qué se arregló
--------------

* **Crecía sin límite.** Se guardaba una entrada por cada participante de cada
  partida detectada (incluidos rivales aleatorios) y `clear_expired()` no lo
  llamaba nadie. En un proceso largo en Render eso son miles de entradas que
  nunca se liberan.
* **Guardaba la respuesta cruda de Riot**, que es la lista completa de colas
  (soloq, flex, TFT...) con ~20 campos cada una. El bot solo usa tier,
  división y LP: ahora se guarda ya reducido, y se parsea una vez en vez de en
  cada acierto de caché.
* **Los reintentos ya no viven aquí**: los hace el cliente de Riot
  (`apis/riot_client.py`), que lee el `Retry-After` y aplica backoff. Mantener
  aquí un bucle duplicaba la lógica y añadía esperas a ciegas.
* **Preguntaba siempre a `euw1`.** `get_league_entries` se llamaba sin
  `platform`, así que cogía `DEFAULT_PLATFORM`. Con la LEC no se notaba, pero de
  las 172 cuentas seguidas hoy 48 están en KR, NA1 o BR1: Riot contestaba 404 y
  esas cuentas salían sin Elo en `/team`, `/ranking` y los embeds de aviso.
  Ahora la plataforma se pasa desde quien conoce la cuenta.

Sobre la clave del caché
------------------------

Sigue siendo solo el PUUID, **no** `(puuid, platform)`. Un PUUID pertenece a una
única región: la plataforma no identifica la entrada, solo enruta la petición.
Meterla en la clave duplicaría entradas de la misma cuenta si dos llamadores
pasaran plataformas distintas para el mismo jugador.
"""

from __future__ import annotations

import time
from typing import Any

import config
from apis.riot_client import RiotApiError, get_riot_client, normalizar_plataforma
from utils.helpers import parse_ranked_data
from utils.logger import get_logger

log = get_logger("core.ranked_cache")

# {puuid: (timestamp, rango_ya_parseado)}
RANKED_CACHE: dict[str, tuple[float, dict]] = {}

# Cuánto aguanta un rango en memoria. Riot no actualiza el rango
# instantáneamente al terminar la partida, así que un TTL corto evita datos
# obsoletos sin multiplicar las peticiones.
CACHE_TTL = config.RANKED_CACHE_TTL

# Tope de entradas. Al pasarse se limpia lo caducado y, si aún sobra, se tiran
# las más antiguas. Sin esto la caché crecía indefinidamente.
CACHE_MAX = 2000

UNKNOWN = {"tier": "Desconocido", "division": "", "lp": 0}


def _guardar(puuid: str, rango: dict) -> None:
    RANKED_CACHE[puuid] = (time.time(), rango)
    if len(RANKED_CACHE) > CACHE_MAX:
        clear_expired()
        if len(RANKED_CACHE) > CACHE_MAX:
            # Se eliminan las más viejas hasta volver al tope.
            sobran = len(RANKED_CACHE) - CACHE_MAX
            viejas = sorted(RANKED_CACHE, key=lambda p: RANKED_CACHE[p][0])[:sobran]
            for p in viejas:
                RANKED_CACHE.pop(p, None)


async def get_rank_data_or_cache(
    puuid: str,
    session: Any = None,
    platform: str | None = None,
    **_ignored,
) -> dict:
    """Devuelve el rango formateado de una cuenta, usando caché si está fresca.

    `platform` es el servidor de la cuenta (`"kr"`, `"na1"`...). Si no se pasa,
    el cliente cae a `DEFAULT_PLATFORM` (euw1) y una cuenta coreana devuelve 404:
    hay que pasarla siempre que se conozca. `normalizar_plataforma` acepta las
    formas que llegan de dpm.lol (`"KR"`, `"NA"`) y de `platformId` de Riot.

    `session` se acepta solo por compatibilidad con llamadores antiguos; la
    petición real la hace el cliente central.
    """
    if not puuid:
        return dict(UNKNOWN)

    cached = RANKED_CACHE.get(puuid)
    if cached and (time.time() - cached[0]) < CACHE_TTL:
        return dict(cached[1])

    client = await get_riot_client()
    try:
        ranked_data = await client.get_league_entries(
            puuid, normalizar_plataforma(platform)
        )
    except RiotApiError as exc:
        log.debug("No se pudo obtener rango de %s...: %s", puuid[:12], exc.status)
        return dict(UNKNOWN)

    if ranked_data is None:
        return dict(UNKNOWN)

    # Se parsea una vez y se guarda ya reducido: la respuesta cruda son varios
    # KB por cuenta y el bot solo usa tres campos.
    rango = parse_ranked_data(ranked_data)
    _guardar(puuid, rango)
    return dict(rango)


def clear_expired() -> int:
    """Elimina entradas caducadas. Devuelve cuántas se liberaron."""
    now = time.time()
    expired = [puuid for puuid, (ts, _) in RANKED_CACHE.items() if now - ts >= CACHE_TTL]
    for puuid in expired:
        del RANKED_CACHE[puuid]
    return len(expired)


def cache_size() -> int:
    return len(RANKED_CACHE)

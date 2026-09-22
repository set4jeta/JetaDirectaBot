#apis/dpm_api.py
"""Cliente para la API de dpm.lol.

Esta API **no es la de Riot**: no comparte rate limit con la key de Riot, así
que se gestiona aparte.

Qué se arregló aquí (era la causa principal de que el bot se quedara sin
memoria en Render y se reiniciara):

1. Cada llamada creaba un `cloudscraper.create_scraper()` nuevo. Eso construye
   una sesión TLS completa con su adaptador, su pool de conexiones y su
   fingerprint. `!historial` hace cientos de llamadas, así que se creaban
   cientos de sesiones que nadie cerraba.
   → Ahora hay un scraper por hilo, creado una vez y reutilizado.

2. Cada función `aiohttp` abría su propio `ClientSession`. Sin pool compartido
   los sockets se quedaban esperando a que el recolector los limpiara.
   → Ahora hay una sola sesión con el conector limitado.

3. `!historial` llamaba a `asyncio.gather` sobre todos los jugadores y todas
   sus cuentas sin límite, y cada tarea ocupaba un hilo del executor.
   → Ahora hay un semáforo que acota la concurrencia.

4. `print()` en cada vuelta, con respuestas JSON enteras volcadas al log.
   → Ahora hay logging con niveles y un caché que evita repetir llamadas.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp
import cloudscraper

from apis import transporte_dpm

import config
from utils.logger import get_logger

log = get_logger("apis.dpm")

_BASE = "https://dpm.lol/v1"
_TIMEOUT = config.DPM_TIMEOUT


# ---------------------------------------------------------------------- #
# Sesiones reutilizadas
# ---------------------------------------------------------------------- #

# cloudscraper no es thread-safe, y lo ejecutamos en hilos del executor.
# Con thread-local cada hilo tiene el suyo y lo reutiliza entre llamadas.
_local = threading.local()


def _get_scraper():
    """Devuelve el scraper del hilo actual, creándolo solo la primera vez."""
    scraper = getattr(_local, "scraper", None)
    if scraper is None:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        _local.scraper = scraper
    return scraper


# Una sola sesión aiohttp para todo el proceso, con el conector limitado para
# que un pico de peticiones no abra cientos de sockets.
_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is not None and not _session.closed:
        return _session
    async with _session_lock:
        if _session is None or _session.closed:
            timeout = aiohttp.ClientTimeout(total=_TIMEOUT)
            connector = aiohttp.TCPConnector(
                limit=config.DPM_CONCURRENCY * 2,
                limit_per_host=config.DPM_CONCURRENCY,
                ttl_dns_cache=300,
            )
            _session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={"User-Agent": "JetaDirectaBot/2.0 (+https://github.com/)", },
            )
    return _session


async def close_session() -> None:
    """Cierra la sesión compartida. Llamar al apagar el bot."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


# ---------------------------------------------------------------------- #
# Concurrencia acotada
# ---------------------------------------------------------------------- #

_sem: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Semáforo global. Se crea dentro del loop en marcha."""
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(config.DPM_CONCURRENCY)
    return _sem


# ---------------------------------------------------------------------- #
# Cachés con TTL y tamaño máximo
# ---------------------------------------------------------------------- #

_history_cache: dict[str, tuple[float, Any]] = {}
_puuid_cache: dict[str, tuple[float, str | None]] = {}
_cache_lock = threading.Lock()


def _cache_get(store: dict, key: str, ttl: float) -> tuple[bool, Any]:
    with _cache_lock:
        hit = store.get(key)
        if hit is None:
            return False, None
        ts, value = hit
        if time.monotonic() - ts > ttl:
            del store[key]
            return False, None
        return True, value


def _cache_put(store: dict, key: str, value: Any) -> None:
    """Guarda y, si la caché se pasa de tamaño, suelta las entradas más viejas."""
    with _cache_lock:
        store[key] = (time.monotonic(), value)
        if len(store) > config.DPM_CACHE_MAX:
            for k, _ in sorted(store.items(), key=lambda kv: kv[1][0]):
                del store[k]
                if len(store) <= config.DPM_CACHE_MAX:
                    break


def clear_caches() -> None:
    """Vacía las cachés en memoria (útil para pruebas y para liberar RAM)."""
    with _cache_lock:
        _history_cache.clear()
        _puuid_cache.clear()


def cache_stats() -> dict[str, int]:
    with _cache_lock:
        return {"historial": len(_history_cache), "puuid": len(_puuid_cache)}


# ---------------------------------------------------------------------- #
# Helpers de red
# ---------------------------------------------------------------------- #

async def _get_json(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET JSON contra dpm.lol. Devuelve `None` si no hay datos.

    Por qué NO usa aiohttp
    ----------------------
    Esta función usaba `aiohttp` y **devolvía HTTP 403 en todas las llamadas**,
    lo que dejaba muertos `!ranking`, los pickrates semanales,
    `get_puuid_from_dpmlol` y `fetch_champion_stats`. Cloudflare no bloquea por
    cabeceras ni por IP: bloquea por **huella TLS del cliente**. Comprobado
    falsificando seis hipótesis, todas con 403:

    * user-agent de navegador,
    * el juego de cabeceras exacto de `requests` replicado byte a byte
      (`CIMultiDict` + `skip_auto_headers` para conservar el orden),
    * el contexto TLS de urllib3 vía `create_urllib3_context()`,
    * ALPN forzado a `http/1.1`,
    * `HttpVersion10`,
    * transplante de cookies de clearance (`cloudscraper` no deja ninguna: pasa
      por huella, no por cookie).

    Y se descartó rate-limit por IP: cinco rondas alternando en el mismo proceso
    dieron 403 a aiohttp cinco veces y 200 a requests cinco veces, misma IP y
    mismo segundo.

    Así que se enruta por `cloudscraper`, que es síncrono, dentro de
    `asyncio.to_thread` para no bloquear el event loop. La firma sigue siendo
    `async`, así que ningún llamador cambia.
    """
    url = f"{_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    async with _get_semaphore():
        for intento in range(1, config.RIOT_MAX_RETRIES + 1):
            estado, data = await asyncio.to_thread(_scraper_get, url)

            if estado == 200:
                return data
            if estado == 404:
                return None
            if estado in (429, 503):
                espera = min(2 ** intento, 30)
                log.debug("dpm.lol %s -> %s, reintento en %ss", path, estado, espera)
                await asyncio.sleep(espera)
                continue
            if estado == 0:
                # Fallo de red o de resolución del challenge: merece reintento.
                espera = min(2 ** intento, 15)
                log.debug("dpm.lol %s: fallo de transporte, reintento en %ss", path, espera)
                await asyncio.sleep(espera)
                continue

            log.warning("dpm.lol %s -> HTTP %s", path, estado)
            return None

    log.warning("dpm.lol %s agotó los %d intentos.", path, config.RIOT_MAX_RETRIES)
    return None


def _scraper_get(url: str) -> tuple[int, Any]:
    """GET a dpm.lol. Devuelve `(estado, json)`; estado 0 = no hubo respuesta.

    Va por `transporte_dpm.pedir`, que intenta cloudscraper y **reintenta con
    curl_cffi** cuando la respuesta no sirve. Hace falta desde que se comprobó que
    desde una IP de datacenter (Render) Cloudflare no deja pasar con cloudscraper:
    los logs estaban llenos de "El leaderboard devolvió 0 cuentas".

    Se separa de `_scraper_get_json` porque `_get_json` necesita distinguir "404,
    no existe" de "no pude ni conectar", para decidir si reintenta.
    """
    resp = transporte_dpm.pedir(url, timeout=_TIMEOUT)
    if resp is None:
        return 0, None
    if resp.status != 200:
        return resp.status, None
    try:
        return 200, resp.json()
    except ValueError as exc:
        log.debug("dpm.lol respuesta no-JSON en %s: %s", url, exc)
        return 0, None


def _scraper_get_json(url: str) -> Any:
    """GET JSON a dpm.lol, ejecutado en hilo. Con respaldo de transporte."""
    resp = transporte_dpm.pedir(url, timeout=_TIMEOUT)
    if resp is None:
        return None
    if resp.status == 404:
        return None
    if resp.status != 200:
        log.debug("dpm.lol %s -> HTTP %s", url, resp.status)
        return None
    try:
        return resp.json()
    except ValueError:
        return None


# ---------------------------------------------------------------------- #
# Endpoints públicos (se mantienen las firmas originales)
# ---------------------------------------------------------------------- #

# endpoint para solicitar lista de players MSI
async def fetch_leaderboard_players():
    data = await _get_json("/leaderboards/custom/f1a01cf4-0352-4dac-9c6d-e8e1e44db67a")
    return (data or {}).get("players", []) if isinstance(data, dict) else []


# Api para solicitar lista de puuids desde DPM lol
async def get_puuid_from_dpmlol(game_name, tag_line):
    data = await _get_json(
        "/players/search", {"gameName": game_name, "tagLine": tag_line}
    )
    return data.get("puuid") if isinstance(data, dict) else None


async def get_match_history_from_dpmlol(puuid):
    """Historial de un PUUID, con caché de TTL corto.

    Antes cada llamada creaba un scraper nuevo; ahora el scraper es por hilo
    y el resultado se recuerda `DPM_HISTORY_TTL` segundos.
    """
    if not puuid:
        return None

    hit, value = _cache_get(_history_cache, puuid, config.DPM_HISTORY_TTL)
    if hit:
        log.debug("Historial de %s servido desde caché", puuid[:8])
        return value

    async with _get_semaphore():
        data = await asyncio.to_thread(
            _scraper_get_json, f"{_BASE}/players/{puuid}/match-history"
        )

    # No se cachea un fallo: si dpm.lol falló, la próxima vez se reintenta.
    if not data:
        return None

    # Se devuelve siempre la misma forma (recortada) para que el resultado no
    # cambie según haya sido acierto o fallo de caché.
    data = _trim_history(data)
    _cache_put(_history_cache, puuid, data)
    return data


# Campos que el bot usa de verdad. Cada participante trae unos 90; aquí solo
# los que consume `!historial` (y los razonables para futuras vistas).
_SLIM_PARTICIPANT = (
    "puuid", "gameName", "tagLine", "displayName", "championName", "champLevel",
    "kills", "deaths", "assists", "win", "teamPosition", "position", "role",
    "teamId", "team", "timePlayed", "totalMinionsKilled", "goldEarned",
    "damagePerMinute", "dpmScore", "killParticipation", "tier", "rank",
    "leaguePoints", "lp", "opponentChampionName",
)

_SLIM_MATCH = ("gameCreation", "gameDuration", "gameId", "platformId", "queueId")


def _trim_history(data: Any) -> Any:
    """Deja el historial en la forma que el bot necesita y la recorta.

    Tres recortes, todos ellos sin efecto en lo que ve el usuario:

    1. Solo las últimas `DPM_HISTORY_MATCHES` partidas, ordenadas por fecha
       (`!historial` vuelve a ordenar, así que conservar las recientes basta).
    2. Solo los campos de `_SLIM_PARTICIPANT` y `_SLIM_MATCH`. Un historial
       completo son ~59 KB de JSON que se convierten en ~205 KB de objetos
       Python; así se queda en ~20 KB.
    3. Se conservan el resto de claves que pueda traer la respuesta raíz.
    """
    if not isinstance(data, dict):
        return data

    matches = data.get("matches")
    if not isinstance(matches, list):
        return data

    ordenadas = sorted(
        (m for m in matches if isinstance(m, dict)),
        key=lambda m: m.get("gameCreation", 0),
        reverse=True,
    )[: config.DPM_HISTORY_MATCHES]

    if not config.DPM_SLIM_HISTORY:
        return {**data, "matches": ordenadas}

    slim_matches = []
    for m in ordenadas:
        participantes = [
            {k: p[k] for k in _SLIM_PARTICIPANT if k in p}
            for p in (m.get("participants") or [])
            if isinstance(p, dict)
        ]
        slim_matches.append({
            **{k: m[k] for k in _SLIM_MATCH if k in m},
            "participants": participantes,
        })

    return {**data, "matches": slim_matches}


async def get_dpmlol_puuid(game_name, tag_line):
    """PUUID en dpm.lol para gameName#tagLine, con caché de un día."""
    if not game_name or not tag_line:
        return None

    key = f"{game_name}#{tag_line}".lower()
    hit, value = _cache_get(_puuid_cache, key, config.DPM_PUUID_TTL)
    if hit:
        return value

    url = (
        f"{_BASE}/players/search"
        f"?gameName={game_name.replace(' ', '+')}&tagLine={tag_line}"
    )
    async with _get_semaphore():
        data = await asyncio.to_thread(_scraper_get_json, url)

    puuid = None
    if isinstance(data, dict):
        puuid = data.get("puuid")
    elif isinstance(data, list) and data:
        for player in data:
            if (
                str(player.get("gameName", "")).lower() == game_name.lower()
                and str(player.get("tagLine", "")).lower() == tag_line.lower()
            ):
                puuid = player.get("puuid")
                break
        if puuid is None:
            puuid = data[0].get("puuid")

    # Los negativos también se recuerdan para no insistir con cuentas
    # inexistentes, pero con un TTL más corto.
    if puuid:
        _cache_put(_puuid_cache, key, puuid)
    else:
        with _cache_lock:
            _puuid_cache[key] = (time.monotonic() - config.DPM_PUUID_TTL + 3600, None)
    return puuid


async def get_is_live_and_updated_from_dpmlol(game_name, tag_line):
    """Devuelve (is_live, updated_at) de una cuenta."""
    game_name_enc = game_name.replace(" ", "+")
    url = f"{_BASE}/players/search?gameName={game_name_enc}&tagLine={tag_line}"

    async with _get_semaphore():
        data = await asyncio.to_thread(_scraper_get_json, url)

    if data is None:
        return False, None

    player = None
    if isinstance(data, list):
        for candidate in data:
            if (
                str(candidate.get("gameName", "")).lower() == game_name.lower()
                and str(candidate.get("tagLine", "")).lower() == tag_line.lower()
            ):
                player = candidate
                break
    elif isinstance(data, dict):
        player = data

    if not player:
        return False, None
    return bool(player.get("isLive", False)), player.get("updatedAt")


def get_rank_from_dpmlol(game_name: str, tag_line: str) -> dict:
    """Rango de SoloQ de una cuenta. Se mantiene sincrónica: se llama desde
    código que no es asíncrono."""
    import urllib.parse

    game_name_enc = urllib.parse.quote_plus(game_name)
    tag_line_enc = urllib.parse.quote_plus(tag_line)
    url = f"{_BASE}/players/search?gameName={game_name_enc}&tagLine={tag_line_enc}"

    data = _scraper_get_json(url)
    if not data:
        return {}

    player = None
    if isinstance(data, list) and data:
        for p in data:
            if (
                str(p.get("gameName", "")).lower() == game_name.lower()
                and str(p.get("tagLine", "")).lower() == tag_line.lower()
            ):
                player = p
                break
        if player is None:
            player = data[0]
    elif isinstance(data, dict):
        player = data

    if not player:
        return {}

    # Busca el rank de SoloQ
    for rank_info in player.get("ranks", []) or []:
        if rank_info.get("queue") == "RANKED_SOLO_5x5":
            return rank_info

    # Si no hay ranks, busca el campo "rank"
    rank = player.get("rank")
    if isinstance(rank, dict) and rank.get("tier"):
        return rank

    return {}


# ---------------------------------------------------------------------- #
# Parche actual
# ---------------------------------------------------------------------- #

_DDRAGON_VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json"
_patch_cache: tuple[float, str] | None = None
_PATCH_TTL = 6 * 3600


async def obtener_parche_actual() -> str:
    """Parche vigente en formato `16.17`, derivado de ddragon.

    `config.DPM_PATCH` era un valor fijo. Cuando Riot saca un parche nuevo, el
    `timeframe` deja de coincidir y `/tierlist` devuelve **0 campeones**, así que
    los pickrates se congelaban en silencio y los roles se inferían con datos
    viejos. Medido: `16.17` -> 173 campeones, `15.14` -> 171, `99.99` -> 0,
    basura -> HTTP 422.

    ddragon sí responde por aiohttp (no está detrás de Cloudflare), así que aquí
    no hace falta el scraper. Si falla, se cae a `config.DPM_PATCH`.
    """
    global _patch_cache

    if _patch_cache and time.time() - _patch_cache[0] < _PATCH_TTL:
        return _patch_cache[1]

    try:
        session = await _get_session()
        async with session.get(_DDRAGON_VERSIONS) as resp:
            if resp.status == 200:
                versiones = await resp.json(content_type=None)
                if isinstance(versiones, list) and versiones:
                    # "16.17.1" -> "16.17": dpm.lol usa mayor.menor.
                    partes = str(versiones[0]).split(".")
                    if len(partes) >= 2:
                        parche = f"{partes[0]}.{partes[1]}"
                        _patch_cache = (time.time(), parche)
                        log.debug("Parche actual según ddragon: %s", parche)
                        return parche
            log.warning("ddragon versions -> HTTP %s", resp.status)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        log.warning("No se pudo leer el parche de ddragon (%s).", exc)

    log.info("Usando el parche de config: %s", config.DPM_PATCH)
    return config.DPM_PATCH


# ---------------------------------------------------------------------- #
# Tierlist y estadísticas
# ---------------------------------------------------------------------- #

async def fetch_champion_lane_pickrates(timeframe=None, game_mode="ranked"):
    """Pickrate por línea para cada campeón: {championName: {lane: pickrate}}."""
    if timeframe is None:
        timeframe = await obtener_parche_actual()

    data = await _get_json(
        "/tierlist",
        {"tier": "emerald_plus", "timeframe": timeframe, "gameMode": game_mode},
    )
    if not isinstance(data, dict):
        return None

    pickrate_by_champ = {}
    for champ in data.get("champions", []) or []:
        name = champ.get("championName")
        if name:
            pickrate_by_champ[name] = champ.get("lanesPickrate", {})

    if not pickrate_by_champ:
        log.error(
            "/tierlist respondió pero sin campeones para timeframe=%s. "
            "Probablemente el parche ya no es válido.",
            timeframe,
        )
        return None

    log.debug("Pickrates: %d campeones (timeframe %s).", len(pickrate_by_champ), timeframe)
    return pickrate_by_champ


async def save_pickrate_json(filepath="champion_lane_pickrates.json",
                             timeframe=None, game_mode="ranked"):
    """Descarga los pickrates y los guarda en disco indexados por ID de campeón."""
    data = await fetch_champion_lane_pickrates(timeframe, game_mode)
    if not data:
        log.error("No se pudo obtener datos de pickrates para guardar.")
        return False

    from utils.champion_names import a_id

    data_by_id = {}
    sin_id = 0
    for champ_name, pickrates in data.items():
        champ_id = a_id(champ_name)
        if champ_id:
            data_by_id[champ_id] = pickrates
        else:
            sin_id += 1

    # Antes se invertía el diccionario a mano y se perdían 24 campeones: dpm.lol
    # devuelve "MonkeyKing" y el caché solo conoce el nombre de display
    # "Wukong". `a_id` entiende las dos formas.
    if sin_id:
        log.warning(
            "%d campeones sin id conocido (recientes o renombrados): se omiten.",
            sin_id,
        )

    # Escritura atómica: si el proceso muere a medias no se corrompe el JSON.
    tmp = f"{filepath}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data_by_id, f, ensure_ascii=False, indent=4)
    os.replace(tmp, filepath)

    log.info("Guardado JSON de pickrates en %s (%d campeones)", filepath, len(data_by_id))
    return True


async def fetch_champion_stats(puuid):
    data = await _get_json(f"/players/{puuid}/champions", {"queue": "solo", "currentSplit": "true"})
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------- #
# Rankings
# ---------------------------------------------------------------------- #

#: Ligas confirmadas vivas en `/v1/esport/soloq/leagues/<liga>/leaderboard`.
#: Comprobado midiendo: un código inexistente **no da 404**, devuelve un
#: leaderboard genérico. Por eso hay lista blanca: sin ella,
#: `!ranking lolquesea` mostraría datos que no son de ninguna liga.
#:
#: Medido el 2026-09-01 (jugadores · equipos):
#:   lec 82·10   lck 81·10   lpl 81·12   lcs 61·8    lcp 57·8
#:   lfl 95·10   nlc 103·15  tcl 61·8    hll 64·8    prm 107·10
#:   msi 121·11  cblol 62·8
#:
#: Ampliado el 2026-09-02 con ocho ligas más. El código de dpm **no coincide**
#: con el slug oficial de lolesports, que es por lo que antes se dieron por
#: inexistentes: `cd` (no `circuito`), `al` (no `arabian`), `hm` (no `hitpoint`),
#: `les` (no `superliga`). Medido igual (jugadores · equipos):
#:   cd 68·10    al 62·8     lit 53·8    les 64·8
#:   ebl 37·6    rl 59·7     rol 61·8    hm 57·8
#:
#: Y estos siguen devolviendo el comodín, probados con todas las variantes
#: razonables de su nombre: lla, nacl, lta/lta_n/lta_s, lrn, lrs, ljl, lco,
#: pcs, vcs, ldl, worlds, lckc/lck_challengers, emea_masters, first_stand,
#: liga_portuguesa, cacg, fls, wsci, ewc.
LIGAS = {
    "lec": "LEC · Europa",
    "lfl": "LFL · Francia",
    "nlc": "NLC · Norte de Europa",
    "lck": "LCK · Corea",
    "lpl": "LPL · China",
    "lcp": "LCP · Asia-Pacífico",
    "lcs": "LCS · Norteamérica",
    "cblol": "CBLOL · Brasil",
    "tcl": "TCL · Turquía",
    "hll": "HLL · Grecia",
    "prm": "Prime League · Alemania",
    "msi": "MSI · Internacional",
    "les": "LES · España",
    "lit": "LIT · Italia",
    "rl": "Rift Legends · Polonia",
    "rol": "Road of Legends · Benelux",
    "hm": "Hitpoint Masters · Chequia y Eslovaquia",
    "ebl": "EBL · Balcanes",
    "al": "Arabian League · Oriente Medio",
    "cd": "Circuito Desafiante · Brasil",
}

#: Tamaño mínimo a partir del cual un leaderboard se considera el comodín.
#:
#: Antes esto era una igualdad contra un número fijo (`1683`). Dejó de servir
#: en cuanto el comodín pasó a 1684 jugadores, y con ello volvió el bug que
#: pretendía evitar: `/ranking lla` devolvía datos sin que fueran de ninguna
#: liga. Como ninguna liga real llega a 122 jugadores (la más grande es MSI con
#: 121) y el comodín ronda los 1700, un umbral holgado aguanta que dpm.lol
#: siga creciendo sin que haya que volver a tocar el número.
_UMBRAL_COMODIN = 200


def fetch_league_leaderboard_sync(liga: str = "lec") -> list[dict[str, Any]]:
    """Igual que `fetch_league_leaderboard` pero sin event loop.

    Por qué existe la versión síncrona
    ---------------------------------
    `accounts_from_teams.main()` es síncrona y se llama con
    `asyncio.to_thread(...)` desde `core/background_tasks.py` y directamente
    desde `main.py` al sembrar cuentas. Si desde ahí se llamara a la versión
    `async` con `asyncio.run()`, se crearía un loop nuevo **dentro de cada
    hilo** y el semáforo global de dpm (`_sem`) quedaría atado al primer loop
    que lo usara: en la segunda llamada, `RuntimeError: ... is bound to a
    different event loop`.

    `_scraper_get_json` es síncrona y no toca el loop, así que no hay problema.
    """
    codigo = (liga or "lec").lower().strip()
    if codigo not in LIGAS:
        log.warning("Liga desconocida: %s. Disponibles: %s", codigo, ", ".join(LIGAS))
        return []

    url = f"{_BASE}/esport/soloq/leagues/{codigo}/leaderboard"
    data = None
    for intento in range(1, config.RIOT_MAX_RETRIES + 1):
        data = _scraper_get_json(url)
        if data is not None:
            break
        if intento < config.RIOT_MAX_RETRIES:
            time.sleep(min(2 ** intento, 15))

    if not isinstance(data, list):
        log.warning("dpm.lol no devolvió una lista para la liga '%s'.", codigo)
        return []

    if len(data) >= _UMBRAL_COMODIN:
        log.error(
            "La liga '%s' devolvió el leaderboard genérico (%d jugadores, "
            "ninguna liga real pasa de 121): dpm.lol ya no la reconoce. "
            "Se descarta para no mostrar datos que no son de esta liga.",
            codigo,
            len(data),
        )
        return []

    return data


async def fetch_league_leaderboard(liga: str = "lec") -> list[dict[str, Any]]:
    """Leaderboard de SoloQ de una liga.

    Una sola petición trae, por jugador: puuid, displayName, team, lane, tier,
    rank, leaguePoints, wins, losses, kda y mostChamps. Eso es todo lo que
    `!ranking` necesitaba armar antes con tres fuentes distintas.
    """
    codigo = (liga or "lec").lower().strip()
    if codigo not in LIGAS:
        log.warning("Liga desconocida: %s. Disponibles: %s", codigo, ", ".join(LIGAS))
        return []

    # Se reutiliza la versión síncrona para que las dos rutas no puedan
    # divergir: una sola implementación del filtro del comodín.
    async with _get_semaphore():
        return await asyncio.to_thread(fetch_league_leaderboard_sync, codigo)


async def fetch_lec_leaderboard():
    """Se mantiene por compatibilidad: es `fetch_league_leaderboard("lec")`."""
    return await fetch_league_leaderboard("lec")


async def fetch_pro_leaderboard():
    data = await _get_json(
        "/leaderboards/soloq", {"page": 1, "platform": "euw1", "isPro": "true"}
    )
    return (data or {}).get("players", []) if isinstance(data, dict) else []


# ---------------------------------------------------------------------- #
# trackingthepros
# ---------------------------------------------------------------------- #

INFO_PLAYERS_PATH = os.path.join(
    os.path.dirname(__file__), "../tracking/soloq/infoplayers_eu.json"
)

_TRACKING_THE_PROS_URL = (
    "https://www.trackingthepros.com/d/list_players"
    "?filter_region=EU&&draw=1&columns%5B0%5D%5Bdata%5D=player_name"
)


async def fetch_infoplayers_eu():
    """Descarga el listado de pros de EU y lo guarda en disco."""
    session = await _get_session()
    try:
        async with _get_semaphore():
            async with session.get(_TRACKING_THE_PROS_URL) as resp:
                if resp.status != 200:
                    log.error("trackingthepros HTTP %s", resp.status)
                    return False
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.error("trackingthepros falló: %s", exc)
        return False

    players = data.get("data", []) if isinstance(data, dict) else []
    if not players:
        log.warning("trackingthepros devolvió 0 jugadores, no se sobrescribe el JSON.")
        return False

    tmp = f"{INFO_PLAYERS_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INFO_PLAYERS_PATH)

    log.info("Actualizados %d jugadores en %s", len(players), INFO_PLAYERS_PATH)
    return True

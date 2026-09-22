"""Cliente único y centralizado para la API de Riot Games.

Por qué existe este módulo
--------------------------
El proyecto original hacía peticiones a Riot desde dos sitios distintos
(`apis/riot_api.py` y el validador de cuentas del torneo, ya retirado), cada uno
con su propia key, sus propios headers y su propia sesión de aiohttp, y ninguno
con rate limiting real.
Como la key antigua era muy limitada (20 req/s, 100 req/2min), el código estaba
sembrado de `sleep(8)` y reintentos a ciegas para sobrevivir.

Con la key nueva (500 req/10s y 30000 req/10min) ese mecanismo ya no hace falta,
pero sí hace falta lo contrario: un limitador que aproveche el cupo sin pasarse,
porque Riot bloquea la key si te excedes de forma sostenida.

Qué hace este cliente
---------------------
1. **Rate limiting de ventana deslizante** con dos ventanas simultáneas
   (10 s y 600 s), igual que las que Riot aplica.
2. **Se autoajusta** leyendo los headers `X-App-Rate-Limit` que devuelve Riot,
   así que si Riot cambia los límites, el cliente se entera solo.
3. **Respeta `Retry-After`** en los 429 y aplica backoff exponencial en 5xx.
4. **User-Agent de navegador**: Cloudflare bloquea el UA por defecto de Python
   con un `403 error code: 1010`. Verificado en vivo.
5. **Una sola sesión** reutilizada (connection pooling), en lugar de abrir una
   sesión nueva por cada petición como hacía el código antiguo.

Uso típico::

    from apis.riot_client import get_riot_client

    client = get_riot_client()
    game = await client.get_active_game(puuid)      # None si no está en partida
    entries = await client.get_league_entries(puuid)
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

import aiohttp

from utils.logger import get_logger

log = get_logger("apis.riot_client")

# Cloudflare bloquea el User-Agent por defecto de aiohttp/urllib con un
# "403 error code: 1010". Hay que presentarse como navegador.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Límites por defecto de la key de producción: 500 req/10s y 30000 req/10min.
# Se sobreescriben automáticamente con lo que Riot reporte en sus headers.
DEFAULT_APP_LIMITS: tuple[tuple[int, float], ...] = ((500, 10.0), (30000, 600.0))

# Límites POR MÉTODO, medidos en vivo contra esta key (no son suposiciones:
# salen de `X-Method-Rate-Limit` de una respuesta real de cada endpoint).
#
# Por qué hay que tenerlos escritos aquí
# --------------------------------------
# `_method_limiters` se creaba al leer la PRIMERA respuesta de cada método. Es
# decir: la primera ráfaga de cada endpoint salía **sin límite de método**,
# porque el limitador todavía no existía. En el arranque real eso significaba
# ~1245 peticiones a `account-v1.by-riot-id` de golpe contra un límite de
# 1000:60 — un 429 garantizado que además arrastraba al resto de tareas.
#
# Sembrarlos evita ese agujero desde la primera petición. Si Riot cambia algún
# límite, `update_limits()` lo sobreescribe con la cabecera real en la siguiente
# respuesta, así que esto no puede quedarse obsoleto en silencio.
KNOWN_METHOD_LIMITS: dict[str, tuple[tuple[int, float], ...]] = {
    "account-v1.by-riot-id": ((1000, 60.0),),
    "account-v1.region": ((20000, 10.0), (1200000, 600.0)),
    "summoner-v4.by-puuid": ((2000, 60.0),),
    "league-v4.entries": ((20000, 10.0), (1200000, 600.0)),
    "spectator-v5.active-games": ((3000, 10.0), (180000, 600.0)),
    "match-v5.ids": ((2000, 10.0),),
}

# Regiones que usa el bot. Los endpoints de cuenta viven en el clúster europeo.
REGION_ACCOUNT = "europe"
REGION_MATCH = "europe"
DEFAULT_PLATFORM = os.getenv("RIOT_DEFAULT_PLATFORM", "euw1")

#: Servidores de LoL a los que se puede preguntar por `spectator-v5`.
#:
#: Esto importa porque el bot ya no sigue solo la LEC: medido en `/v1/pros`,
#: las cuentas de los pros están repartidas entre servidores (la LCK tiene
#: cuentas en KR, NA1 y EUW1; la LCS en NA1, KR, EUW1 y BR1). Antes todas se
#: consultaban contra `DEFAULT_PLATFORM` (euw1) y Riot contestaba 404, así que
#: un jugador en partida en su servidor contaba como "no jugando".
PLATAFORMAS: frozenset[str] = frozenset({
    "br1", "eun1", "euw1", "jp1", "kr", "la1", "la2", "na1",
    "oc1", "ph2", "ru", "sg2", "th2", "tr1", "tw2", "vn2",
})


def normalizar_plataforma(platform: str | None) -> str:
    """Deja una plataforma en la forma que espera la API de Riot.

    dpm.lol las da en mayúsculas (`"EUW1"`) y a veces con otros nombres
    (`"NA"`); la URL de Riot las quiere en minúsculas (`"euw1"`). Si no se
    reconoce, se cae a `DEFAULT_PLATFORM` y se registra en el log: consultar
    contra un servidor inventado gasta una petición para siempre dar 404.
    """
    from utils.logger import get_logger

    limpia = (platform or "").strip().lower()
    if not limpia:
        return DEFAULT_PLATFORM
    if limpia in PLATAFORMAS:
        return limpia

    # "na" -> "na1", "euw" -> "euw1", "kr" ya está.
    con_uno = f"{limpia}1"
    if con_uno in PLATAFORMAS:
        return con_uno

    get_logger("apis.riot_client").debug(
        "Plataforma desconocida %r, se usa %s.", platform, DEFAULT_PLATFORM
    )
    return DEFAULT_PLATFORM

MAX_RETRIES = int(os.getenv("RIOT_MAX_RETRIES", "4"))
REQUEST_TIMEOUT = float(os.getenv("RIOT_REQUEST_TIMEOUT", "15"))


class RiotApiError(Exception):
    """Error no recuperable de la API de Riot."""

    def __init__(self, status: int, message: str, url: str = ""):
        super().__init__(f"Riot API {status}: {message}")
        self.status = status
        self.message = message
        self.url = url


class RiotRateLimitExceeded(RiotApiError):
    """Se agotaron los reintentos por rate limit."""


@dataclass
class _Window:
    """Ventana deslizante de peticiones: como máximo `limit` en `seconds`."""

    limit: int
    seconds: float
    hits: deque[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.hits is None:
            self.hits = deque()

    def prune(self, now: float) -> None:
        while self.hits and (now - self.hits[0]) >= self.seconds:
            self.hits.popleft()

    def wait_time(self, now: float) -> float:
        """Segundos que hay que esperar para poder hacer otra petición."""
        self.prune(now)
        if len(self.hits) < self.limit:
            return 0.0
        return max(0.0, self.seconds - (now - self.hits[0]))

    def record(self, now: float) -> None:
        self.hits.append(now)

    def sync_count(self, count: int, now: float) -> None:
        """Sube la ventana al consumo que Riot dice que llevamos. **Nunca baja.**

        Nuestro contador local empieza en cero, pero la key puede estar
        compartida con otros procesos (otro bot, un script, el historial del
        propio proceso antes de reiniciar). Riot reporta lo que llevamos gastado
        en `X-App-Rate-Limit-Count`; si no lo tenemos en cuenta, el limitador
        cree que tiene todo el cupo libre y provoca 429 que podríamos evitar.

        Por qué solo se sube
        --------------------
        La versión anterior también **restaba**: si Riot reportaba menos de lo
        que teníamos apuntado, hacía `popleft()` de nuestras propias marcas.
        Eso está mal y era grave.

        `X-App-Rate-Limit-Count` es una foto del instante en que Riot procesó
        *esa* petición, y las respuestas llegan desordenadas: con 12 corrutinas
        en vuelo es normal recibir una respuesta que salió cuando el contador
        iba por 20 justo después de otra que iba por 480. Restar significa
        borrar marcas de peticiones que sí hicimos.

        Medido con `scripts/test_rate_limiter.py`: con 500 peticiones en vuelo,
        una sola respuesta tardía con `Count: 20:10` dejaba la ventana en 20 y
        regalaba **480 peticiones de cupo que no existen**. Justo el camino a un
        429 y, sostenido, a que Riot bloquee la key.

        Subir sí es correcto y además es demostrable: dentro de una misma
        ventana el contador de Riot solo crece, así que cualquier foto —incluso
        vieja— es una **cota inferior** del consumo real. Quedarnos con el
        máximo visto no puede sobreestimar por culpa del desorden. Y las marcas
        caducan solas en `prune()`, así que el ajuste no se queda pegado.

        Rellenamos con marcas de tiempo actuales: es conservador (libera el
        cupo un poco más tarde de lo estrictamente necesario), que es justo lo
        que queremos para no ganarnos un 429.
        """
        if count <= 0:
            return
        self.prune(now)
        missing = count - len(self.hits)
        if missing > 0:
            self.hits.extend([now] * missing)


class _RateLimiter:
    """Aplica varias ventanas a la vez y elige la más restrictiva.

    Riot devuelve límites con formato `"500:10,30000:600"` en
    `X-App-Rate-Limit`. Es decir, varias ventanas simultáneas: hay que cumplir
    **todas** a la vez, así que el tiempo de espera es el máximo de todas ellas.
    """

    def __init__(self, limits: Iterable[tuple[int, float]] = DEFAULT_APP_LIMITS):
        self.windows = [_Window(limit, seconds) for limit, seconds in limits]
        self._lock = asyncio.Lock()
        self.total_waits = 0
        self.total_wait_seconds = 0.0

    def update_limits(self, limits: Iterable[tuple[int, float]]) -> None:
        """Sustituye las ventanas conservando el histórico del mismo tamaño."""
        new = [_Window(limit, seconds) for limit, seconds in limits]
        for old, fresh in zip(self.windows, new):
            if old.seconds == fresh.seconds:
                fresh.hits = old.hits
        self.windows = new

    def sync_counts(self, counts: Iterable[tuple[int, float]]) -> None:
        """Sincroniza el consumo reportado por Riot con nuestro conteo local."""
        now = time.monotonic()
        for (count, seconds) in counts:
            for window in self.windows:
                if window.seconds == seconds:
                    window.sync_count(count, now)
                    break

    async def acquire(self) -> None:
        """Reserva un hueco. Duerme fuera del lock para no serializar corrutinas.

        Dormir con el lock puesto sería un error grave: con cientos de
        corrutinas esperando, todas se bloquearían detrás de la que duerme y el
        bot pasaría a ser secuencial. Aquí solo la comprobación y la reserva
        son atómicas; la espera se hace con el lock liberado.
        """
        while True:
            async with self._lock:
                now = time.monotonic()
                wait = max((w.wait_time(now) for w in self.windows), default=0.0)
                if wait <= 0:
                    stamp = time.monotonic()
                    for w in self.windows:
                        w.record(stamp)
                    return
                self.total_waits += 1
                self.total_wait_seconds += wait

            log.debug("Rate limit local alcanzado, esperando %.2fs", wait)
            await asyncio.sleep(wait)


def _parse_rate_limit_header(value: str | None) -> tuple[tuple[int, float], ...]:
    """`"500:10,30000:600"` -> `((500, 10.0), (30000, 600.0))`."""
    if not value:
        return ()
    parsed: list[tuple[int, float]] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        try:
            count, seconds = chunk.split(":", 1)
            parsed.append((int(count), float(seconds)))
        except ValueError:
            continue
    return tuple(parsed)


class RiotClient:
    """Cliente async de la API de Riot con rate limiting y reintentos."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("RIOT_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "RIOT_API_KEY no está definida. Cárgala en el .env antes de usar el cliente."
            )

        self._session: aiohttp.ClientSession | None = None
        self._app_limiter = _RateLimiter(DEFAULT_APP_LIMITS)
        # Sembrados con los límites medidos: si se esperara a la primera
        # respuesta, la primera ráfaga de cada endpoint saldría sin limitar.
        self._method_limiters: dict[str, _RateLimiter] = {
            clave: _RateLimiter(limites)
            for clave, limites in KNOWN_METHOD_LIMITS.items()
        }
        self.stats = {"requests": 0, "retries": 0, "errors": 0, "rate_limited": 0}
        # Desglose de los 429 por `X-Rate-Limit-Type`: application / method /
        # service. Sin esto, `/health` solo puede decir "hubo 429" y no si el
        # problema es nuestro cupo o un límite interno de Riot.
        self.rate_limit_types: dict[str, int] = {}

    # ------------------------------------------------------------------ #
    # Ciclo de vida de la sesión
    # ------------------------------------------------------------------ #

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "X-Riot-Token": self.api_key,
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    # ------------------------------------------------------------------ #
    # Núcleo HTTP
    # ------------------------------------------------------------------ #

    def _sync_limits_from_response(self, headers, method_key: str) -> None:
        """Ajusta los limitadores con lo que Riot reporta en sus headers.

        Riot manda `X-App-Rate-Limit` (los límites) y `X-App-Rate-Limit-Count`
        (lo que llevas gastado). Si alguna vez cambian los límites de la key,
        el cliente se adapta solo en la siguiente respuesta.
        """
        app_limits = _parse_rate_limit_header(headers.get("X-App-Rate-Limit"))
        if app_limits:
            self._app_limiter.update_limits(app_limits)

        # Alineamos nuestro conteo con el de Riot: la key puede estar consumida
        # por otro proceso o por una ejecución anterior.
        app_counts = _parse_rate_limit_header(headers.get("X-App-Rate-Limit-Count"))
        if app_counts:
            self._app_limiter.sync_counts(app_counts)

        method_limits = _parse_rate_limit_header(headers.get("X-Method-Rate-Limit"))
        if method_limits:
            limiter = self._method_limiters.get(method_key)
            if limiter is None:
                limiter = _RateLimiter(method_limits)
                self._method_limiters[method_key] = limiter
            else:
                limiter.update_limits(method_limits)

            method_counts = _parse_rate_limit_header(headers.get("X-Method-Rate-Limit-Count"))
            if method_counts:
                limiter.sync_counts(method_counts)

    async def _request(self, url: str, method_key: str) -> tuple[int, Any]:
        last_status = 0
        last_body: Any = None

        for attempt in range(MAX_RETRIES + 1):
            # Esperar el turno en la ventana de app y en la del método.
            await self._app_limiter.acquire()
            method_limiter = self._method_limiters.get(method_key)
            if method_limiter:
                await method_limiter.acquire()

            self.stats["requests"] += 1
            try:
                async with self.session.get(url) as resp:
                    self._sync_limits_from_response(resp.headers, method_key)
                    last_status = resp.status

                    if resp.status == 200:
                        return 200, await resp.json(content_type=None)

                    body: Any = None
                    try:
                        body = await resp.json(content_type=None)
                    except Exception:
                        body = await resp.text()

                    # 204 No Content: sin datos, pero petición válida.
                    if resp.status == 204:
                        return 204, None

                    # 404 aquí significa "no encontrado" (p. ej. no está en
                    # partida). Es un resultado legítimo, no un error.
                    if resp.status == 404:
                        return 404, None

                    if resp.status == 429:
                        self.stats["rate_limited"] += 1
                        self.stats["retries"] += 1
                        retry_after = resp.headers.get("Retry-After")
                        # `X-Rate-Limit-Type` dice QUÉ límite se pasó:
                        # `application` (500:10 / 30000:600), `method` (el del
                        # endpoint) o `service` (un límite interno de Riot que no
                        # viene en ninguna cabecera de cupo). Sin este dato, un
                        # 429 es indistinguible de otro y no se puede arreglar
                        # nada: el log solo decía "Retry-After=23" y hubo que
                        # gastar cuatro sondas para no averiguarlo.
                        limit_type = resp.headers.get("X-Rate-Limit-Type", "?")
                        wait = float(retry_after) if retry_after else min(2 ** attempt, 30)
                        if attempt == MAX_RETRIES:
                            raise RiotRateLimitExceeded(
                                429, f"rate limit persistente tras {MAX_RETRIES} reintentos", url
                            )
                        self.rate_limit_types[limit_type] = (
                            self.rate_limit_types.get(limit_type, 0) + 1
                        )
                        log.warning(
                            "429 en %s (tipo=%s). Retry-After=%s. Esperando %.1fs · app=%s método=%s",
                            method_key, limit_type, retry_after, wait,
                            resp.headers.get("X-App-Rate-Limit-Count", "?"),
                            resp.headers.get("X-Method-Rate-Limit-Count", "?"),
                        )
                        await asyncio.sleep(wait)
                        continue

                    if 500 <= resp.status < 600:
                        self.stats["retries"] += 1
                        if attempt == MAX_RETRIES:
                            break
                        wait = min(2 ** attempt, 30)
                        log.warning("%s en %s (intento %s). Reintentando en %.1fs", resp.status, method_key, attempt + 1, wait)
                        await asyncio.sleep(wait)
                        continue

                    # 4xx no recuperable: no tiene sentido reintentar.
                    self.stats["errors"] += 1
                    message = body.get("status", {}).get("message") if isinstance(body, dict) else str(body)
                    raise RiotApiError(resp.status, str(message)[:200], url)

            except asyncio.TimeoutError:
                self.stats["retries"] += 1
                if attempt == MAX_RETRIES:
                    self.stats["errors"] += 1
                    raise RiotApiError(408, f"timeout tras {REQUEST_TIMEOUT}s", url)
                log.warning("Timeout en %s (intento %s)", method_key, attempt + 1)
                await asyncio.sleep(min(2 ** attempt, 30))
            except aiohttp.ClientError as exc:
                self.stats["retries"] += 1
                if attempt == MAX_RETRIES:
                    self.stats["errors"] += 1
                    raise RiotApiError(0, f"error de red: {exc}", url)
                await asyncio.sleep(min(2 ** attempt, 30))

        self.stats["errors"] += 1
        raise RiotApiError(last_status, f"fallo tras {MAX_RETRIES} reintentos", url)

    def _url(self, host: str, path: str) -> str:
        return f"https://{host}.api.riotgames.com{path}"

    # ------------------------------------------------------------------ #
    # Endpoints
    # ------------------------------------------------------------------ #

    async def get_account_by_riot_id(
        self, game_name: str, tag_line: str, region: str = REGION_ACCOUNT
    ) -> dict | None:
        """Resuelve gameName#tagLine a PUUID. None si la cuenta no existe.

        Este es el endpoint que repara los PUUIDs corruptos del proyecto: los
        que se guardaron desde dpm.lol no los puede descifrar Riot.
        """
        from urllib.parse import quote

        path = (
            f"/riot/account/v1/accounts/by-riot-id/"
            f"{quote(str(game_name), safe='')}/{quote(str(tag_line), safe='')}"
        )
        status, data = await self._request(self._url(region, path), "account-v1.by-riot-id")
        return data if status == 200 else None

    async def get_puuid(self, game_name: str, tag_line: str, region: str = REGION_ACCOUNT) -> str | None:
        account = await self.get_account_by_riot_id(game_name, tag_line, region)
        return account.get("puuid") if account else None

    async def get_active_game(self, puuid: str, platform: str = DEFAULT_PLATFORM) -> dict | None:
        """Partida en curso. None si no está en partida (404)."""
        path = f"/lol/spectator/v5/active-games/by-summoner/{puuid}"
        status, data = await self._request(self._url(platform, path), "spectator-v5.active-games")
        return data if status == 200 else None

    async def get_league_entries(self, puuid: str, platform: str = DEFAULT_PLATFORM) -> list | None:
        """Entradas de liga (soloq, flex, etc.) de una cuenta."""
        path = f"/lol/league/v4/entries/by-puuid/{puuid}"
        status, data = await self._request(self._url(platform, path), "league-v4.entries")
        return data if status == 200 else None

    async def get_soloq_rank(self, puuid: str, platform: str = DEFAULT_PLATFORM) -> dict | None:
        """Devuelve solo la entrada de RANKED_SOLO_5x5, que es lo que usa el bot."""
        entries = await self.get_league_entries(puuid, platform)
        if not entries:
            return None
        for entry in entries:
            if entry.get("queueType") == "RANKED_SOLO_5x5":
                return entry
        return None

    async def get_region_by_puuid(self, puuid: str, region: str = REGION_ACCOUNT) -> str | None:
        """Región/plataforma real de la cuenta, por PUUID."""
        path = f"/riot/account/v1/region/by-game/lol/by-puuid/{puuid}"
        status, data = await self._request(self._url(region, path), "account-v1.region")
        return data.get("region") if status == 200 and data else None

    async def get_summoner(self, puuid: str, platform: str = DEFAULT_PLATFORM) -> dict | None:
        """Perfil de invocador: nivel, icono, fecha de revisión."""
        path = f"/lol/summoner/v4/summoners/by-puuid/{puuid}"
        status, data = await self._request(self._url(platform, path), "summoner-v4.by-puuid")
        return data if status == 200 else None

    async def get_match_ids(
        self,
        puuid: str,
        start: int = 0,
        count: int = 20,
        region: str = REGION_MATCH,
    ) -> list[str]:
        """IDs de partidas recientes. Permite reconstruir historial sin dpm.lol."""
        path = f"/lol/match/v5/matches/by-puuid/{puuid}/ids?start={start}&count={count}"
        status, data = await self._request(self._url(region, path), "match-v5.ids")
        return data if status == 200 else []

    async def get_match(self, match_id: str, region: str = REGION_MATCH) -> dict | None:
        path = f"/lol/match/v5/matches/{match_id}"
        status, data = await self._request(self._url(region, path), "match-v5.match")
        return data if status == 200 else None

    # ------------------------------------------------------------------ #
    # Utilidades
    # ------------------------------------------------------------------ #

    async def verify_key(self) -> bool:
        """Comprueba que la key sirve gastando una sola petición."""
        try:
            await self.get_account_by_riot_id("Caps", "G2W")
            return True
        except RiotApiError as exc:
            log.error("La key de Riot no es válida: %s", exc)
            return False

    def rate_limit_report(self) -> str:
        counts = self.stats
        detalle = ""
        if self.rate_limit_types:
            tipos = " ".join(f"{k}={v}" for k, v in sorted(self.rate_limit_types.items()))
            detalle = f" tipos_429[{tipos}]"
        return (
            f"peticiones={counts['requests']} reintentos={counts['retries']} "
            f"429s={counts['rate_limited']} errores={counts['errors']} "
            f"esperas_locales={self._app_limiter.total_waits}{detalle}"
        )


# ---------------------------------------------------------------------- #
# Singleton
# ---------------------------------------------------------------------- #

_client: RiotClient | None = None
_client_lock = asyncio.Lock()


async def get_riot_client() -> RiotClient:
    """Devuelve el cliente compartido, creándolo la primera vez."""
    global _client
    async with _client_lock:
        if _client is None:
            _client = RiotClient()
    return _client


async def close_riot_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None

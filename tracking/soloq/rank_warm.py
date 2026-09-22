"""Mantiene frescos los rangos de las cuentas seguidas.

Por qué hace falta
------------------

`!team` tiene que comparar el Elo de todas las cuentas de un jugador para
enseñar la mejor. Si el rango no está cacheado, lo pide a Riot en el momento:
un equipo de 5 jugadores con 2-3 cuentas cada uno son 10-15 peticiones antes de
poder contestar, y el usuario espera.

Y al revisar el histórico solo **56 de las 635 cuentas conocidas** tenían un
rango guardado: el resto de las 1885 entradas eran rivales aleatorios de
partidas antiguas. Es decir, en la práctica `!team` pedía casi todo a la API.

Cómo funciona
-------------

Igual que el precalentado del historial: cada vuelta refresca una fracción de
las cuentas rotando el punto de inicio, así que en

    RANK_CACHE_MAX_AGE / RANK_WARM_INTERVAL

vueltas se ha pasado por todas y ninguna llega a caducar. Con los valores por
defecto (6 h de validez, vuelta cada 5 min) son 72 vueltas: unas 9 cuentas por
vuelta de las 635, es decir 9 peticiones cada 5 minutos.

Sobre el límite de la key
-------------------------

Aunque se refrescaran las 635 de golpe seguiría siendo trivial para la key de
producción (500 req/10 s): son 2 ventanas. Se hace por lotes de todas formas
porque el cupo lo comparten el tracker de partidas, `!live` y `!historial`, y
no tiene sentido gastarlo en ráfagas cuando el dato no caduca en horas.

Cada cuenta en SU servidor
--------------------------

`cuentas_seguidas()` devolvía una `list[str]` de PUUIDs, tirando
`account.platform`. Sin la plataforma, `get_soloq_rank` caía a `DEFAULT_PLATFORM`
(euw1) y las cuentas de KR/NA1/BR1 —48 de las 172 seguidas hoy— contestaban 404:
el refresco las contaba como "sin clasificar" y su Elo nunca se cacheaba, así que
`!team` acababa enseñando la cuenta europea secundaria en vez de la principal.
Ahora se acarrean pares `(puuid, plataforma)` de punta a punta.
"""

from __future__ import annotations

import asyncio
import time

import config
from apis.riot_client import RiotApiError, get_riot_client, normalizar_plataforma
from core import rank_store
from utils.logger import get_logger

log = get_logger("tracking.rank_warm")

_offset = 0
_estado: dict[str, object] = {}

#: Una cuenta a refrescar: su PUUID y el servidor donde vive.
Cuenta = tuple[str, str]


def cuentas_seguidas() -> list[Cuenta]:
    """Cuentas seguidas como `(puuid, plataforma)`, sin repetir ni inválidas.

    Se omiten las marcadas `stale`: son PUUIDs que Riot rechaza con un 400 y
    gastar una petición en ellas es tirar cupo.

    La plataforma se normaliza aquí y no en cada petición: viene de dpm.lol en
    mayúsculas (`"EUW1"`, `"KR"`) y la URL de Riot la quiere en minúsculas.
    """
    from tracking.soloq.accounts_io import load_tracked_accounts

    cuentas: list[Cuenta] = []
    vistos: set[str] = set()
    for jugador in load_tracked_accounts():
        for account in jugador.accounts:
            puuid = getattr(account, "puuid", None)
            if not puuid or puuid in vistos or getattr(account, "stale", False):
                continue
            vistos.add(puuid)
            cuentas.append((puuid, normalizar_plataforma(getattr(account, "platform", None))))
    return cuentas


def _fraccion_por_vuelta() -> int:
    """En cuántas vueltas se recorre la lista entera."""
    intervalo = max(1, config.RANK_WARM_INTERVAL)
    # Margen del 20 %: mejor pasar por todas antes de que caduquen.
    ventana = max(intervalo, int(config.RANK_CACHE_MAX_AGE * 0.8))
    return max(1, ventana // intervalo)


async def refrescar(cuentas: list[Cuenta], concurrencia: int | None = None) -> dict:
    """Pide el rango de cada cuenta en su servidor y lo anota en el histórico.

    Acepta también una lista de PUUIDs sueltos por comodidad de los scripts de
    mantenimiento; en ese caso se usa el servidor por defecto.
    """
    if not cuentas:
        return {"total": 0, "ok": 0, "sin_rango": 0, "errores": 0, "segundos": 0.0}

    # Los scripts antiguos pasan `list[str]`. Se normaliza aquí para no tener
    # que tocarlos y para que un str suelto no se desmonte en `(p, u, u, i, d)`.
    pares: list[Cuenta] = [
        (c, normalizar_plataforma(None)) if isinstance(c, str) else c for c in cuentas
    ]

    client = await get_riot_client()
    sem = asyncio.Semaphore(concurrencia or config.TRACKER_CONCURRENCY)
    t0 = time.perf_counter()

    async def uno(puuid: str, plataforma: str) -> str:
        async with sem:
            try:
                entrada = await client.get_soloq_rank(puuid, plataforma)
            except RiotApiError as exc:
                log.debug("Rango de %s... (%s): %s", puuid[:12], plataforma, exc.status)
                return "error"

        if not entrada:
            # No es un fallo: la cuenta existe pero no tiene SoloQ clasificada.
            return "sin_rango"

        rank = {
            "tier": str(entrada.get("tier", "")).capitalize(),
            "division": entrada.get("rank", ""),
            "lp": entrada.get("leaguePoints", 0),
        }
        # flush=False: se vuelca una sola vez al final del lote, no 600 veces.
        return "ok" if rank_store.guardar(puuid, rank, flush=False) else "sin_rango"

    resultados = await asyncio.gather(
        *[uno(p, plat) for p, plat in pares], return_exceptions=True
    )
    rank_store.volcar(forzar=True)

    conteo = {"ok": 0, "sin_rango": 0, "error": 0}
    for r in resultados:
        if isinstance(r, Exception):
            conteo["error"] += 1
        else:
            conteo[r] = conteo.get(r, 0) + 1

    return {
        "total": len(pares),
        "ok": conteo["ok"],
        "sin_rango": conteo["sin_rango"],
        "errores": conteo["error"],
        "segundos": round(time.perf_counter() - t0, 1),
    }


async def siguiente_lote() -> dict:
    """Refresca la siguiente fracción de cuentas. Una unidad de trabajo."""
    global _offset, _estado

    cuentas = cuentas_seguidas()
    if not cuentas:
        log.debug("Rangos: no hay cuentas que refrescar.")
        return {"total": 0, "ok": 0, "sin_rango": 0, "errores": 0, "segundos": 0.0}

    partes = _fraccion_por_vuelta()
    tamano = max(1, -(-len(cuentas) // partes))  # techo de la división

    inicio = _offset % len(cuentas)
    lote = (cuentas[inicio:] + cuentas[:inicio])[:tamano]
    _offset = (inicio + len(lote)) % len(cuentas)

    resumen = await refrescar(lote)
    resumen["de"] = len(cuentas)
    resumen["partes"] = partes
    _estado = resumen

    log.info(
        "Rangos refrescados: %d/%d (%d sin clasificar, %d errores) en %.1fs · %d de %d cuentas",
        resumen["ok"], resumen["total"], resumen["sin_rango"], resumen["errores"],
        resumen["segundos"], len(lote), len(cuentas),
    )
    return resumen


async def refrescar_todo(concurrencia: int | None = None) -> dict:
    """Refresca todas las cuentas seguidas de una pasada.

    Se usa al arrancar (una vez) y desde los scripts de mantenimiento. Con la
    key de producción son unos pocos segundos.
    """
    cuentas = cuentas_seguidas()
    resumen = await refrescar(cuentas, concurrencia)
    # Se registran los servidores implicados: si aparece un único servidor
    # cuando debería haber varios, la plataforma se ha perdido por el camino.
    servidores = sorted({plat for _, plat in cuentas})
    log.info(
        "Rangos: pasada completa %d/%d cuentas con rango en %.1fs "
        "(%d sin clasificar, %d errores) · servidores: %s",
        resumen["ok"], resumen["total"], resumen["segundos"],
        resumen["sin_rango"], resumen["errores"], ", ".join(servidores) or "-",
    )
    return resumen


def estado() -> dict[str, object]:
    return dict(_estado)

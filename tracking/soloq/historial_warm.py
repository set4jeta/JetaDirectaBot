"""Mantiene caliente la caché del historial.

`!historial` tarda unos 20 s en frío: tiene que descargar las partidas de las
130 cuentas registradas antes de poder contestar. Ese cálculo se puede hacer
antes de que nadie lo pida.

Cómo funciona
-------------

No se refrescan las 130 cuentas de golpe cada poco: serían 260 peticiones
seguidas a dpm.lol. En vez de eso cada vuelta refresca una **fracción** de las
cuentas, rotando el punto de inicio. En

    DPM_HISTORY_TTL / HISTORIAL_WARM_INTERVAL

vueltas se ha pasado por todas, así que ninguna entrada llega a caducar y el
comando siempre encuentra los datos ya descargados.

Con los valores por defecto (TTL 300 s, intervalo 60 s) hay 5 vueltas: se
refresca una quinta parte de las cuentas por minuto y todas están al día.
"""

from __future__ import annotations

import asyncio
import time

import config
from apis.dpm_api import get_dpmlol_puuid, get_match_history_from_dpmlol
from utils.logger import get_logger

log = get_logger("tracking.historial_warm")

# Rotación entre vueltas para no empezar siempre por las mismas cuentas.
_offset = 0

# Resultado de la última pasada completa, para poder informar del estado.
_estado: dict[str, object] = {}


def _fraccion_por_vuelta() -> int:
    """Cuántas vueltas caben en el TTL, con margen."""
    vueltas = max(1, config.DPM_HISTORY_TTL // max(1, config.HISTORIAL_WARM_INTERVAL))
    return max(1, vueltas)


def estado() -> dict[str, object]:
    """Último estado conocido: cuentas refrescadas, fallos y duración."""
    return dict(_estado)


async def refrescar_lote(cuentas: list[tuple[str, str]], concurrencia: int | None = None) -> dict:
    """Descarga el historial de una lista de (gameName, tagLine).

    Devuelve un resumen con cuántas se han refrescado y cuántas han fallado.
    """
    if not cuentas:
        return {"total": 0, "ok": 0, "fallos": 0, "segundos": 0.0}

    sem = asyncio.Semaphore(concurrencia or config.DPM_CONCURRENCY)
    t0 = time.perf_counter()

    async def uno(game_name: str, tag_line: str) -> bool:
        async with sem:
            puuid = await get_dpmlol_puuid(game_name, tag_line)
            if not puuid:
                return False
            await get_match_history_from_dpmlol(puuid)
            return True

    resultados = await asyncio.gather(
        *[uno(gn, tl) for gn, tl in cuentas], return_exceptions=True
    )

    ok = sum(1 for r in resultados if r is True)
    fallos = len(cuentas) - ok
    segundos = time.perf_counter() - t0
    return {"total": len(cuentas), "ok": ok, "fallos": fallos, "segundos": round(segundos, 1)}


async def siguiente_lote() -> dict:
    """Refresca la siguiente fracción de cuentas y rota el offset.

    Pensado para llamarse desde un `tasks.loop`: hace una unidad de trabajo y
    devuelve, sin dormir dentro.
    """
    global _offset, _estado

    from tracking.soloq.accounts_io import load_tracked_accounts

    jugadores = load_tracked_accounts()
    cuentas: list[tuple[str, str]] = []
    vistas: set[str] = set()
    for jugador in jugadores:
        for account in jugador.accounts:
            gn = account.riot_id.get("game_name", "")
            tl = account.riot_id.get("tag_line", "")
            clave = f"{gn}#{tl}".lower()
            if gn and tl and clave not in vistas:
                vistas.add(clave)
                cuentas.append((gn, tl))

    if not cuentas:
        log.debug("Historial: no hay cuentas que precalentar.")
        return {"total": 0, "ok": 0, "fallos": 0, "segundos": 0.0}

    partes = _fraccion_por_vuelta()
    tamano = max(1, -(-len(cuentas) // partes))  # techo de la división

    inicio = _offset % len(cuentas)
    lote = (cuentas[inicio:] + cuentas[:inicio])[:tamano]
    _offset = (inicio + len(lote)) % len(cuentas)

    resumen = await refrescar_lote(lote)
    resumen["de"] = len(cuentas)
    resumen["partes"] = partes
    _estado = resumen

    log.info(
        "Historial precalentado: %d/%d cuentas en %.1fs (%d fallos) · vuelta %d/%d",
        resumen["ok"], resumen["total"], resumen["segundos"], resumen["fallos"],
        (inicio // tamano) + 1, partes,
    )
    return resumen

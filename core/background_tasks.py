"""Tareas periódicas del bot.

Regla de oro de `nextcord.ext.tasks`
------------------------------------
Un `@tasks.loop(...)` programa la siguiente vuelta **cuando el cuerpo termina**.
Si el cuerpo contiene un `while True` o un `sleep` que dura lo mismo que el
intervalo, el loop deja de comportarse como esperas: o no vuelve a dispararse
nunca, o lo hace con el doble de retraso.

Aquí había cuatro tareas con ese problema:

* `check_games_loop` llamaba a `ActiveGameTracker.run()`, que era `while True`.
* `actualizar_puuids_poco_a_poco` avanzaba una cuenta por minuto sin terminar
  nunca (tardaría más de 11 horas en pasar por las ~690 cuentas).
* `actualizar_accounts_diario` era `@tasks.loop(hours=24)` **y además** hacía
  `await asyncio.sleep(24 * 60 * 60)` dentro: 48 h hasta la primera ejecución.
* `actualizar_infoplayers_poco_a_poco` era `@tasks.loop(hours=1)` y su cuerpo
  dormía en trozos hasta completar esa misma hora.

Ahora cada tarea hace una unidad de trabajo y devuelve. Además, los scrapers
síncronos (`cloudscraper`) se ejecutan en un hilo aparte: llamarlos directamente
desde una corrutina bloquea el event loop y congela el bot entero.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from nextcord.ext import tasks

import config
from core import health as salud
from tracking.soloq import puuid_repair
from tracking.soloq.accounts_io import load_accounts
from tracking.soloq.active_game_checker import ActiveGameTracker
from utils.logger import get_logger

log = get_logger("core.background_tasks")

_bot_instance = None
_tracker_instance = None
_players = load_accounts()

# Cadencia de la pasada de partidas. Antes el intervalo real lo imponía un
# `sleep(0.5)` por jugador (>30 s con 55 jugadores). Ahora una pasada dura
# menos de 2 s, así que podemos permitirnos sondear más a menudo: una partida
# se detecta mucho antes sin acercarnos al límite de la API.
CHECK_INTERVAL = int(os.getenv("CHECK_GAMES_INTERVAL", "30"))

# Cuántas cuentas se reparan por hora en la tarea de mantenimiento.
ACCOUNTS_PER_HOUR = int(os.getenv("PUUID_REPAIR_BATCH", "200"))

# Cuántos jugadores se refrescan por hora en Infoplayers.
INFOPLAYERS_PER_HOUR = int(os.getenv("INFOPLAYERS_PER_HOUR", "60"))

# Índice circular para las tareas que trabajan por lotes.
_infoplayers_offset = 0


def start_background_tasks(bot):
    """Arranca todas las tareas periódicas. Idempotente."""
    global _bot_instance, _tracker_instance
    _bot_instance = bot
    _tracker_instance = ActiveGameTracker(bot)

    for loop in (
        check_games_loop,
        actualizar_puuids_periodico,
        actualizar_accounts_diario,
        actualizar_pickrates_semanal,
        actualizar_infoplayers_por_lotes,
    ):
        if not loop.is_running():
            loop.start()

    if config.HISTORIAL_WARM and not precalentar_historial.is_running():
        precalentar_historial.start()

    if config.RANK_WARM and not refrescar_rangos.is_running():
        refrescar_rangos.start()

    log.info(
        "Tareas iniciadas | partidas cada %ss | reparación %s cuentas/h | "
        "infoplayers %s jugadores/h | historial %s | rangos %s",
        CHECK_INTERVAL, ACCOUNTS_PER_HOUR, INFOPLAYERS_PER_HOUR,
        "precalentado" if config.HISTORIAL_WARM else "en frío",
        f"cada {config.RANK_WARM_INTERVAL}s" if config.RANK_WARM else "solo a demanda",
    )


# ---------------------------------------------------------------------- #
# 1 · Partidas en curso
# ---------------------------------------------------------------------- #

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_games_loop():
    """Una pasada del tracker. `run()` devuelve, así que el loop se repite."""
    from core.ranked_cache import clear_expired
    from utils.cache_utils import limpiar_cache_partidas_viejas

    try:
        limpiar_cache_partidas_viejas()
        # La caché de rangos en memoria tenía un `clear_expired()` que nadie
        # llamaba: crecía con cada participante de cada partida detectada.
        clear_expired()
    except Exception as exc:
        log.debug("Error limpiando cachés: %s", exc)

    if _tracker_instance is None:
        return

    try:
        await _tracker_instance.run()
    except Exception:
        # Una excepción aquí MATARÍA la tarea para siempre si no se captura.
        log.exception("Fallo en la pasada de partidas; se reintentará en la próxima vuelta.")
        salud.registrar("riot", False, "fallo en la pasada de partidas")
    else:
        salud.registrar("riot", True)


@check_games_loop.before_loop
async def before_check_games():
    from apis.riot_client import get_riot_client

    # Calentamos el cliente para que la primera pasada no pague la conexión.
    await get_riot_client()


# ---------------------------------------------------------------------- #
# 2 · Reparación de PUUIDs
# ---------------------------------------------------------------------- #

@tasks.loop(hours=6)
async def actualizar_puuids_periodico():
    """Re-resuelve los PUUIDs contra Riot.

    Sustituye a `actualizar_puuids_poco_a_poco`, que avanzaba una cuenta por
    minuto. Con la key nueva (500 req/10s) las ~690 cuentas se resuelven en
    pocos segundos, así que se hace todo de una vez y sin estado intermedio.

    Solo repara cuentas que siguen vivas: las marcadas como `stale` se
    reintentan también, porque una cuenta puede volver a existir si el jugador
    recupera el nombre.
    """
    try:
        summary = await puuid_repair.repair_all(dry_run=False, make_backup=False)
    except Exception:
        log.exception("Fallo reparando PUUIDs; se reintentará en la próxima vuelta.")
        return

    reparadas = sum(s.get("reparadas", 0) for s in summary.values())
    perdidas = sum(s.get("no_encontradas", 0) for s in summary.values())
    log.info("Reparación de PUUIDs: %d corregidas, %d no halladas en Riot", reparadas, perdidas)


# ---------------------------------------------------------------------- #
# 3 · Descarga de cuentas desde dpm.lol
# ---------------------------------------------------------------------- #

@tasks.loop(hours=24)
async def actualizar_accounts_diario():
    """Refresca accounts.json y accounts_from_teams.json.

    Antes tenía un `sleep(24h)` dentro del propio cuerpo de un loop de 24 h,
    así que la primera ejecución llegaba a las 48 h. El descanso inicial, si se
    quiere, se configura con `.before_loop`, no durmiendo dentro.
    """
    from tracking.soloq.accounts_from_leaderboard import main as update_leaderboard
    from tracking.soloq.accounts_from_teams import main as update_teams

    log.info("Actualizando cuentas desde dpm.lol...")

    # cloudscraper es síncrono y bloqueante: sin esto, el bot se congela
    # durante toda la descarga. asyncio.to_thread lo saca del event loop.
    try:
        await asyncio.to_thread(update_leaderboard)
        await asyncio.to_thread(update_teams)
    except Exception:
        log.exception("Fallo descargando cuentas desde dpm.lol.")
        salud.registrar("cuentas", False, "dpm.lol no respondió")
        return

    global _players
    anterior = len(_players)
    _players = load_accounts()
    log.info("Cuentas actualizadas (%d jugadores en memoria).", len(_players))

    # Una caída de dpm.lol puede devolver una lista vacía sin lanzar nada: el
    # fichero se sobreescribe con [] y el bot deja de seguir a nadie en
    # silencio. Si pasa, se marca como avería aunque la descarga "funcionara".
    if not _players:
        log.error(
            "La descarga dejó 0 jugadores (antes había %d). dpm.lol ha devuelto "
            "algo vacío o con otro formato.",
            anterior,
        )
        salud.registrar("cuentas", False, "0 jugadores tras la descarga")
    else:
        salud.registrar("cuentas", True, f"{len(_players)} jugadores")

    # Aprovechamos para dejar los PUUIDs consistentes con los nombres nuevos.
    try:
        await puuid_repair.repair_all(dry_run=False, make_backup=False)
    except Exception:
        log.exception("Fallo reparando PUUIDs tras la descarga de cuentas.")


# ---------------------------------------------------------------------- #
# 4 · Pickrates de campeones
# ---------------------------------------------------------------------- #

@tasks.loop(hours=168)  # 1 semana
async def actualizar_pickrates_semanal():
    """Refresca champion_lane_pickrates.json, que se usa para inferir roles.

    `save_pickrate_json` **devuelve False** cuando dpm.lol no da datos, no lanza.
    Antes eso se ignoraba y el log decía "Pickrates de campeones actualizados"
    igualmente: una semana entera creyendo que estaba al día cuando no se había
    escrito nada. Es exactamente el tipo de fallo silencioso que hace que el bot
    parezca funcionar y dé datos viejos.
    """
    from apis.dpm_api import save_pickrate_json

    try:
        ok = await save_pickrate_json()
    except Exception:
        log.exception("Fallo actualizando pickrates; se mantiene el fichero anterior.")
        salud.registrar("pickrates", False, "excepción al descargar")
        return

    if ok:
        log.info("Pickrates de campeones actualizados.")
        salud.registrar("pickrates", True)
    else:
        log.warning(
            "dpm.lol no devolvió pickrates: se sigue usando el fichero anterior "
            "(los roles inferidos pueden ser de un parche viejo)."
        )
        salud.registrar("pickrates", False, "dpm.lol no devolvió datos")


# ---------------------------------------------------------------------- #
# 5 · Infoplayers
# ---------------------------------------------------------------------- #

@tasks.loop(hours=1)
async def actualizar_infoplayers_por_lotes():
    """Refresca Infoplayers/ por lotes, en vez de dormir una hora seguida.

    La versión anterior recorría todos los jugadores con sleeps calculados para
    ocupar la hora entera. El problema: si el bot se reiniciaba a mitad, el
    progreso se perdía; y durante esa hora el event loop estaba ocupado
    gestionando el bucle. Aquí cada vuelta procesa un lote acotado y devuelve.
    """
    global _infoplayers_offset

    from tracking.soloq.infoplayers_eu_dpm import guardar_datos_jugador_en_json
    from utils.load_accounts import load_all_accounts

    cuentas = load_all_accounts()
    nombres = sorted({acc["name"] for acc in cuentas if acc.get("name")})

    if not nombres:
        log.debug("Infoplayers: no hay jugadores que actualizar.")
        return

    # Rotamos el punto de inicio para que con el tiempo todos se actualicen,
    # aunque el lote sea más pequeño que el total.
    inicio = _infoplayers_offset % len(nombres)
    lote = (nombres[inicio:] + nombres[:inicio])[:INFOPLAYERS_PER_HOUR]
    _infoplayers_offset = (inicio + len(lote)) % len(nombres)

    log.info("Infoplayers: actualizando %d de %d jugadores.", len(lote), len(nombres))

    scraper = None
    try:
        import cloudscraper

        scraper = await asyncio.to_thread(cloudscraper.create_scraper)
    except Exception:
        log.exception("No se pudo crear el scraper de Infoplayers.")
        return

    ok = 0
    for nombre in lote:
        try:
            # Bloqueante: va a un hilo para no congelar el bot.
            await asyncio.to_thread(guardar_datos_jugador_en_json, nombre, scraper)
            ok += 1
        except Exception:
            log.debug("No se pudo actualizar Infoplayers de %s", nombre)

    log.info("Infoplayers: %d/%d actualizados correctamente.", ok, len(lote))

    # Que falle alguno es normal (jugadores sin página en dpm.lol). Que fallen
    # todos significa que la fuente está caída o ha cambiado.
    if lote and ok == 0:
        salud.registrar("historial", False, "0 de %d jugadores actualizados" % len(lote))
    else:
        salud.registrar("historial", True, f"{ok}/{len(lote)}")


# ---------------------------------------------------------------------- #
# 6 · Precalentamiento del historial
# ---------------------------------------------------------------------- #

@tasks.loop(seconds=config.HISTORIAL_WARM_INTERVAL)
async def precalentar_historial():
    """Mantiene la caché del historial al día para que `!historial` responda ya.

    Cada vuelta refresca una fracción de las cuentas rotando el inicio, de modo
    que todas se refrescan dentro del TTL sin lanzar cientos de peticiones de
    golpe. Ver `tracking/soloq/historial_warm.py`.
    """
    from tracking.soloq.historial_warm import siguiente_lote

    try:
        await siguiente_lote()
    except Exception:
        log.exception("Fallo precalentando el historial; se reintentará en la próxima vuelta.")


# ---------------------------------------------------------------------- #
# 7 · Rangos de las cuentas seguidas
# ---------------------------------------------------------------------- #

@tasks.loop(seconds=config.RANK_WARM_INTERVAL)
async def refrescar_rangos():
    """Mantiene el Elo de las cuentas seguidas al día.

    `!team` tiene que comparar el Elo de todas las cuentas de cada jugador para
    enseñar la mejor. Sin esto lo pedía a la API en el momento (10-15
    peticiones antes de contestar), porque el histórico solo tenía rango para
    56 de las 635 cuentas conocidas.
    """
    from tracking.soloq.rank_warm import siguiente_lote

    try:
        await siguiente_lote()
    except Exception:
        log.exception("Fallo refrescando rangos; se reintentará en la próxima vuelta.")


@refrescar_rangos.before_loop
async def before_refrescar_rangos():
    """Primera pasada completa, para no arrancar con el histórico vacío."""
    from tracking.soloq.rank_warm import refrescar_todo

    try:
        await refrescar_todo()
    except Exception:
        log.exception("Fallo en la primera pasada de rangos; seguirá por lotes.")


# ---------------------------------------------------------------------- #
# Cierre ordenado
# ---------------------------------------------------------------------- #

async def stop_background_tasks():
    """Para las tareas y cierra los clientes HTTP."""
    for loop in (
        check_games_loop,
        actualizar_puuids_periodico,
        actualizar_accounts_diario,
        actualizar_pickrates_semanal,
        actualizar_infoplayers_por_lotes,
        precalentar_historial,
        refrescar_rangos,
    ):
        if loop.is_running():
            loop.cancel()

    from apis.dpm_api import close_session
    from apis.riot_client import close_riot_client
    from core.rank_data import flush_rank_data

    # Los rangos se escriben en diferido: si el proceso se va sin volcar, se
    # perdería lo que se haya recogido desde el último flush.
    try:
        flush_rank_data(forzar=True)
    except Exception:
        log.debug("No se pudo volcar el histórico de rangos al cerrar.")

    await close_riot_client()
    try:
        await close_session()
    except Exception:
        log.debug("La sesión de dpm.lol ya estaba cerrada.")
    log.info("Tareas detenidas y clientes HTTP cerrados.")

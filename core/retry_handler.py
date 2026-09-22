"""Cola de reintentos para cuentas cuya partida no se pudo confirmar.

Se usa desde `!match` / `/match`: si Riot limita la petición, se contesta con la
última partida en caché y se apunta la cuenta aquí para que un trabajador de
fondo vuelva a intentarlo y deje la caché fresca para la siguiente consulta.

Qué estaba roto
---------------

1. **Bucle infinito.** El `RETRY_PUUIDS.pop(0)` estaba fuera del `while
   RETRY_PUUIDS`, así que la cola nunca se vaciaba: el trabajador repetía la
   misma cuenta para siempre. Cada vuelta era una petición a `spectator-v5`, o
   sea una tarea que se queda golpeando la API mientras el proceso viva. Con la
   key de producción eso es cupo tirado y, en Render, memoria que no baja.

2. **Sin plataforma.** `get_active_game(puuid)` iba contra euw1. Para una cuenta
   de KR el reintento devolvía 404 eternamente: nunca podía tener éxito.

3. **`aiohttp.ClientSession` inútil.** Se abría una sesión y se pasaba a
   `get_active_game`, que la ignora desde que las peticiones las hace el cliente
   central. Era un pool de conexiones abierto para nada.

4. **La bandera se ponía tarde.** `RETRY_WORKER_RUNNING` se marcaba *dentro* de
   la corrutina, así que dos llamadas seguidas a `add_to_retry_queue` creaban dos
   trabajadores antes de que ninguno arrancara. Ahora se marca al crear la tarea.

Los reintentos por 429 (con `Retry-After` y backoff) los hace ya
`apis/riot_client.py`. Que un 429 llegue hasta aquí significa que el cliente
agotó sus intentos, así que aquí solo se reintenta un número acotado de veces y
espaciado; no tiene sentido insistir en caliente.
"""

from __future__ import annotations

import asyncio

from apis.riot_api import get_active_game
from tracking.soloq.active_game_cache import olvidar, set_active_game
from utils.logger import get_logger

log = get_logger("core.retry_handler")

#: Cuentas pendientes: `(puuid, plataforma_o_None)`.
RETRY_PUUIDS: list[tuple[str, str | None]] = []
RETRY_WORKER_RUNNING = False

#: Tope de intentos por cuenta antes de rendirse.
MAX_INTENTOS = 3
#: Espera entre intentos. El limitador del cliente ya espació los suyos.
ESPERA = 5.0
#: Tope de la cola. `!match` la alimenta una vez por invocación; si crece más
#: que esto es que algo va mal y no conviene acumular trabajo sin fin.
MAX_COLA = 200


def add_to_retry_queue(puuid: str, platform: str | None = None) -> None:
    """Apunta una cuenta para reintentar la consulta de partida activa."""
    global RETRY_WORKER_RUNNING

    if not puuid:
        return
    if any(p == puuid for p, _ in RETRY_PUUIDS):
        return
    if len(RETRY_PUUIDS) >= MAX_COLA:
        log.warning("Cola de reintentos llena (%d), se descarta %s...", MAX_COLA, puuid[:12])
        return

    RETRY_PUUIDS.append((puuid, platform))

    if not RETRY_WORKER_RUNNING:
        # Se marca aquí, no dentro de la corrutina: si se espera a que la tarea
        # arranque, dos llamadas seguidas crean dos trabajadores.
        RETRY_WORKER_RUNNING = True
        asyncio.create_task(retry_worker())


async def _reintentar(puuid: str, platform: str | None) -> None:
    """Hasta `MAX_INTENTOS` consultas espaciadas para una cuenta."""
    for intento in range(1, MAX_INTENTOS + 1):
        try:
            active_game, status = await get_active_game(puuid, platform=platform)
        except Exception as exc:
            log.debug("Reintento de %s... falló: %s", puuid[:12], exc)
            return

        if status == 200 and active_game:
            set_active_game(puuid, active_game)
            log.debug("Reintento de %s... resuelto en el intento %d.", puuid[:12], intento)
            return
        if status == 404:
            # Confirmado: no está en partida. Se limpia la entrada obsoleta.
            olvidar(puuid)
            return
        if status != 429:
            # Cualquier otro error no se arregla esperando.
            log.debug("Reintento de %s... abandonado (status %s).", puuid[:12], status)
            return

        if intento < MAX_INTENTOS:
            await asyncio.sleep(ESPERA)

    log.debug("Reintento de %s... agotado tras %d intentos.", puuid[:12], MAX_INTENTOS)


async def retry_worker() -> None:
    """Vacía la cola. Sale cuando no queda nada, no antes ni después."""
    global RETRY_WORKER_RUNNING

    try:
        while RETRY_PUUIDS:
            puuid, platform = RETRY_PUUIDS.pop(0)
            await _reintentar(puuid, platform)
    except asyncio.CancelledError:
        # Apagado del bot: se deja la cola como está, no es estado que persista.
        raise
    except Exception:
        log.exception("El trabajador de reintentos murió con la cola a medias.")
    finally:
        RETRY_WORKER_RUNNING = False

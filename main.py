# main.py
"""Punto de entrada del bot.

Qué hacía antes y por qué se ha cambiado
----------------------------------------
1. **Lanzaba el bot como proceso hijo** (`subprocess.run(["python", "-m",
   "core.bot_launcher"])`). Eso tenía tres problemas:

   * Las señales van al **padre**. Render manda SIGTERM al proceso principal, el
     hijo no se enteraba, y el cierre ordenado de `core.bot_launcher` (volcar los
     rangos pendientes, cerrar las sesiones HTTP) no se ejecutaba nunca.
   * Dos intérpretes de Python a la vez en un plan de 512 MB, con el padre
     manteniendo en memoria las cuentas ya cargadas sin usarlas para nada.
   * `"python"` a pelo depende del PATH; si el entorno solo tiene `python3` el
     arranque fallaba con `FileNotFoundError` después de haber hecho todo el
     trabajo de descarga.

2. **Descargaba el leaderboard y los equipos de dpm.lol antes de conectar.** Son
   dos scrapes con `cloudscraper` que tardan minutos; el bot no aparecía en
   Discord hasta que acababan. Y es trabajo **duplicado**: la tarea
   `actualizar_accounts_diario` de `core/background_tasks.py` hace exactamente lo
   mismo, en un hilo aparte, y su primera vuelta salta al arrancar.

3. **Resolvía los PUUIDs con el camino viejo** (`update_puuids_in_accounts`), que
   abre su propia `aiohttp.ClientSession`, reintenta con `sleep(8)` y no pasa por
   el limitador de la key nueva. `puuid_repair.repair_all()` hace lo mismo con el
   cliente compartido y las ~690 cuentas salen en segundos.

Ahora esto solo comprueba la configuración, abre el puerto de salud y arranca el
bot **en este mismo proceso**. El refresco de datos lo llevan las tareas de
fondo, salvo el caso en el que de verdad hace falta hacerlo antes: que no haya
ficheros de cuentas todavía (primer despliegue).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import config
from keep_alive import keep_alive
from utils.logger import get_logger

log = get_logger("main")

BASE_DIR = Path(__file__).resolve().parent
ACCOUNTS = BASE_DIR / "tracking" / "soloq" / "accounts.json"
ACCOUNTS_TEAMS = BASE_DIR / "tracking" / "soloq" / "accounts_from_teams.json"

# Fuerza el refresco síncrono al arrancar (comportamiento antiguo). Solo útil
# para depurar los scrapers: en producción retrasa la conexión a Discord.
STARTUP_REFRESH = os.getenv("STARTUP_REFRESH", "0") == "1"


def _vacio(path: Path) -> bool:
    """True si el fichero no existe, está vacío o no es una lista con datos."""
    if not path.exists() or path.stat().st_size == 0:
        return True
    try:
        with path.open(encoding="utf-8") as f:
            return not json.load(f)
    except (json.JSONDecodeError, OSError):
        # Un JSON roto es peor que uno ausente: mejor volver a bajarlo.
        log.warning("%s no se puede leer; se tratará como vacío.", path.name)
        return True


def _sembrar_cuentas() -> None:
    """Descarga las cuentas de forma síncrona. Solo en el primer arranque."""
    from tracking.soloq.accounts_from_leaderboard import main as update_leaderboard
    from tracking.soloq.accounts_from_teams import main as update_teams

    log.info("No hay ficheros de cuentas: descargando por primera vez...")
    for nombre, fn in (("leaderboard", update_leaderboard), ("equipos", update_teams)):
        try:
            fn()
            log.info("Cuentas de %s descargadas.", nombre)
        except Exception:
            # Sin cuentas el bot arranca igual: el tracker no encontrará a nadie
            # y la tarea diaria volverá a intentarlo.
            log.exception("Fallo descargando las cuentas de %s.", nombre)


async def _reparar_puuids() -> None:
    """Resuelve los PUUIDs con el cliente compartido y su limitador."""
    from apis.riot_client import close_riot_client
    from tracking.soloq import puuid_repair

    try:
        resumen = await puuid_repair.repair_all(dry_run=False, make_backup=False)
    except Exception:
        log.exception("Fallo reparando PUUIDs; el bot arranca con lo que haya.")
        return
    finally:
        # Este cliente pertenece a un event loop que se cierra al salir de
        # `asyncio.run`; si se dejara vivo, el bot lo heredaría atado a un loop
        # muerto y toda petición fallaría con "Event loop is closed".
        await close_riot_client()

    reparadas = sum(s.get("reparadas", 0) for s in resumen.values())
    log.info("PUUIDs verificados (%d corregidos).", reparadas)


def main() -> int:
    falta = config.missing_required()
    if falta:
        log.error("Faltan variables obligatorias en .env: %s", ", ".join(falta))
        return 1

    log.info("Configuración:\n%s", config.resumen())

    primera_vez = _vacio(ACCOUNTS) and _vacio(ACCOUNTS_TEAMS)
    if primera_vez or STARTUP_REFRESH:
        _sembrar_cuentas()
        asyncio.run(_reparar_puuids())
    else:
        # La tarea `actualizar_accounts_diario` refresca esto en su primera
        # vuelta, y `actualizar_puuids_periodico` repara los PUUIDs cada 6 h.
        log.info("Cuentas presentes; el refresco lo hacen las tareas de fondo.")

    # Puerto de salud para los PaaS que esperan uno abierto (hilo demonio).
    keep_alive()

    # Los módulos de scraping se importan **aquí**, en el arranque, y no en el
    # comando que los usa. Pesa (cloudscraper, bs4 y curl_cffi) y `/track <liga>`
    # lo importaba en frío dentro del propio comando: medido, 188 ms en un PC
    # normal y segundos en un plan de 0,1 CPU, comiéndose el plazo de 3 s que
    # Discord da para la primera respuesta. Aquí no hay nadie esperando.
    try:
        from tracking.soloq import accounts_from_teams  # noqa: F401
        from tracking.soloq import accounts_from_leaderboard  # noqa: F401
    except Exception:
        log.exception("No se pudieron precalentar los módulos de scraping.")

    log.info("Iniciando bot de Discord...")
    from core.bot_launcher import main as run_bot

    asyncio.run(run_bot())
    return 0


if __name__ == "__main__":
    sys.exit(main())

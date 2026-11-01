"""Refresco de rosters lanzado por la tarea programada de Windows.

Por qué existe
--------------
dpm.lol contesta **403 a las IPs de datacenter** (Render y los runners de
GitHub). La única IP que entra siempre es la de casa: medido el 01-11-2026, 200
en el 100 % de las peticiones desde aquí, 403 en el 100 % desde Render y en 8 de
cada 9 ejecuciones desde un runner.

Así que el refresco que de verdad funciona es este, ejecutado en el PC del dueño.
La tarea programada lo llama cada 6 h con `pythonw.exe` (sin ventana negra) y
aquí se escribe todo a un fichero, porque sin consola no habría forma de saber
qué pasó.

Qué hace
--------
Llama a `scripts/refrescar_rosters.py` con el freno de 5 h: si el censo de la
rama se publicó hace menos, no hace nada y sale con 0. O sea que si el PC estuvo
apagado y la tarea se lanza dos veces seguidas, la segunda es gratis.

Ese freno tiene que ser **menor** que el intervalo de la tarea (6 h) o la tarea
no haría nada nunca — es exactamente el error que tuvo el workflow de GitHub
durante un día: cron cada 3 h con un freno de 5 h.

Uso:
    pythonw scripts/tarea_rosters.py          # lo que lanza la tarea
    python  scripts/tarea_rosters.py --ligas lec   # a mano, para probar
"""

from __future__ import annotations

import logging
import os
import pathlib
import sys
import time
from logging.handlers import RotatingFileHandler

RAIZ = pathlib.Path(__file__).resolve().parent.parent
LOG = RAIZ / "logs" / "tarea_rosters.log"
CANDADO = RAIZ / "logs" / "tarea_rosters.lock"

#: Un refresco completo son ~20 minutos (21 ligas, ~50 fichas cada una, más la
#: reparación de PUUID contra Riot). Si el candado tiene más de esto, es de un
#: proceso que murió sin borrarlo y se puede tomar.
CANDADO_CADUCADO = 3 * 3600


def _configurar_log() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    manejador = RotatingFileHandler(
        LOG, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    manejador.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    # `force` no: si el script de dentro ya puso manejadores, se respetan.
    for previo in list(raiz.handlers):
        if isinstance(previo, RotatingFileHandler):
            raiz.removeHandler(previo)
    raiz.addHandler(manejador)


def _tomar_candado() -> bool:
    """Evita dos refrescos a la vez sobre el mismo `accounts_from_teams.json`.

    Dos procesos escribiendo ese fichero a la vez lo dejan a medias, y de ahí
    sale un censo con la mitad de los jugadores: el bot lo publicaría y el
    barrido perdería cuentas. Barato de evitar.
    """
    CANDADO.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(CANDADO, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            edad = time.time() - CANDADO.stat().st_mtime
        except OSError:
            edad = 0.0
        if edad < CANDADO_CADUCADO:
            return False
        os.unlink(CANDADO)
        fd = os.open(CANDADO, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w") as f:
        f.write(str(os.getpid()))
    return True


def main() -> int:
    _configurar_log()
    log = logging.getLogger("tarea_rosters")

    if not _tomar_candado():
        log.info("Ya hay un refresco en marcha; esta vuelta no hace nada.")
        return 0

    try:
        sys.path.insert(0, str(RAIZ))
        sys.path.insert(0, str(RAIZ / "scripts"))

        import refrescar_rosters

        # 300 minutos = 5 h, menor que el intervalo de 6 h de la tarea.
        argv = sys.argv[1:] or ["--si-mas-de-minutos", "300"]
        sys.argv = ["refrescar_rosters.py", *argv]
        log.info("Refresco desde el PC: %s", " ".join(sys.argv[1:]))
        codigo = refrescar_rosters.main()
        log.info("Refresco terminado con código %d.", codigo)
        return codigo
    except Exception:
        log.exception("El refresco falló sin llegar a terminar.")
        return 1
    finally:
        try:
            os.unlink(CANDADO)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

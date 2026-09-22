"""Prueba del apagado ordenado del bot.

Qué se comprueba y por qué
--------------------------
El bot escribe los rangos **en diferido**: `core.rank_store.guardar()` solo marca
el dato como pendiente y `volcar()` se niega a tocar el disco hasta que pasan
`RANK_FLUSH_INTERVAL` segundos. Eso está bien mientras el proceso vive, pero
significa que al cerrar hay que forzar el volcado o se pierde lo acumulado.
`stop_background_tasks()` lo hacía... y nadie llamaba a `stop_background_tasks()`.

Las tres cosas que se prueban aquí son exactamente las tres que fallaban:

1. **El diferido pierde datos si nadie fuerza el volcado.** Se demuestra, no se
   asume: se guarda un rango y se comprueba que `volcar()` sin forzar devuelve
   `False` y el fichero sigue sin el dato.
2. **`_apagar()` es reentrante de verdad.** El apagado se puede disparar dos
   veces (el manejador de señal y el `finally` de `main()`). Con un booleano a
   secas, la segunda llamada volvía enseguida y `asyncio.run` cancelaba el
   volcado a medias. Ahora la segunda espera a la primera.
3. **Los manejadores de señal se instalan.** Render apaga con SIGTERM, cuya
   acción por defecto termina el proceso *sin* ejecutar ningún `finally`.

Uso:
    python scripts/test_shutdown.py
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from core import rank_store  # noqa: E402

fallos: list[str] = []
comprobaciones = 0


def check(etiqueta: str, obtenido, esperado) -> None:
    global comprobaciones
    comprobaciones += 1
    if obtenido == esperado:
        print(f"   ok   {etiqueta:<54} {obtenido!r}")
    else:
        fallos.append(f"{etiqueta}: esperaba {esperado!r}, salió {obtenido!r}")
        print(f"   FALLO {etiqueta:<54} {obtenido!r} != {esperado!r}")


PUUID = "puuid-de-prueba-" + "x" * 62
RANGO = {"tier": "DIAMOND", "division": "II", "lp": 75}


# ---------------------------------------------------------------------- #
# 1 · La escritura diferida necesita un volcado forzado
# ---------------------------------------------------------------------- #

print("\n-- escritura diferida de rangos " + "-" * 40)


def _redirigir_almacen(destino: Path) -> None:
    """Apunta el almacén a un fichero temporal y limpia su estado en memoria."""
    rank_store.RANKED_DATA_FILE = str(destino)
    rank_store.BACKUP_FILE = str(destino) + ".bak"
    rank_store._ranks = None
    rank_store._mtime = 0.0
    rank_store._dirty = False
    rank_store._last_flush = time.time()  # como si acabara de volcar


def _leer(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


tmpdir = Path(tempfile.mkdtemp(prefix="jeta-shutdown-"))
fichero = tmpdir / "ranked_data.json"
fichero.write_text("{}", encoding="utf-8")

_original = (rank_store.RANKED_DATA_FILE, rank_store.BACKUP_FILE)
_redirigir_almacen(fichero)

check("guardar() acepta el rango", rank_store.guardar(PUUID, RANGO), True)
check("queda pendiente de volcar", rank_store.estado()["pendiente_de_volcar"], True)

# Este es el fallo original: sin forzar, el intervalo manda y no se escribe nada.
check("volcar() sin forzar no escribe", rank_store.volcar(forzar=False), False)
check("el fichero sigue sin el dato", PUUID in _leer(fichero), False)

# Y esto es lo que hace `stop_background_tasks()` al cerrar.
check("volcar(forzar=True) sí escribe", rank_store.volcar(forzar=True), True)
check("el dato llega al disco", _leer(fichero).get(PUUID, {}).get("tier"), "DIAMOND")
check("ya no queda nada pendiente", rank_store.estado()["pendiente_de_volcar"], False)

# Segundo volcado sin cambios: no debe reescribir 316 KB por gusto.
check("volcar() sin cambios no reescribe", rank_store.volcar(forzar=True), False)

rank_store.RANKED_DATA_FILE, rank_store.BACKUP_FILE = _original
rank_store._ranks = None
rank_store._mtime = 0.0
rank_store._dirty = False


# ---------------------------------------------------------------------- #
# 2 · `_apagar()` reentrante
# ---------------------------------------------------------------------- #

print("\n-- apagado reentrante " + "-" * 50)

from core import bot_launcher  # noqa: E402

veces_parado = 0
cerrado = False


class _BotFalso:
    def is_closed(self) -> bool:
        return cerrado

    async def close(self) -> None:
        global cerrado
        cerrado = True


async def _stop_lento() -> None:
    """Simula el volcado: tarda, para que la segunda llamada tenga que esperar."""
    global veces_parado
    await asyncio.sleep(0.20)
    veces_parado += 1


async def probar_reentrancia() -> None:
    bot_launcher.bot = _BotFalso()
    bot_launcher.stop_background_tasks = _stop_lento
    bot_launcher._apagando = False
    bot_launcher._apagado_listo = None

    inicio = time.perf_counter()
    await asyncio.gather(
        bot_launcher._apagar("SIGTERM"),
        bot_launcher._apagar("finally de main"),
    )
    tardanza = time.perf_counter() - inicio

    check("el cuerpo del apagado corre una sola vez", veces_parado, 1)
    check("la segunda llamada espera a la primera", tardanza >= 0.20, True)
    check("se cierra la conexión de Discord", cerrado, True)

    # Una tercera llamada, ya terminado el apagado, no debe colgarse.
    await asyncio.wait_for(bot_launcher._apagar("otra vez"), timeout=1.0)
    check("una llamada posterior no se cuelga", veces_parado, 1)


asyncio.run(probar_reentrancia())


# ---------------------------------------------------------------------- #
# 3 · Instalación de los manejadores de señal
# ---------------------------------------------------------------------- #

print("\n-- manejadores de señal " + "-" * 48)


async def probar_senales() -> None:
    soportadas = bot_launcher._senales_soportadas()
    check("SIGTERM está en la lista (es la de Render)",
          signal.SIGTERM in soportadas, True)
    if sys.platform == "win32":
        # En Windows `SIGTERM` no se puede *enviar*: `os.kill` acaba llamando a
        # `TerminateProcess`, que no ejecuta manejadores. La que sí llega desde
        # otro proceso es `CTRL_BREAK_EVENT` -> `SIGBREAK`.
        check("en Windows también se engancha SIGBREAK",
              getattr(signal, "SIGBREAK", None) in soportadas, True)

    previos = {s: signal.getsignal(s) for s in soportadas}
    try:
        bot_launcher._instalar_senales(asyncio.get_running_loop())
        for sig in soportadas:
            # En POSIX lo engancha el event loop (y `getsignal` devuelve un
            # builtin interno); en Windows se usa `signal.signal`. En los dos
            # casos deja de ser la acción por defecto, que es lo que importa:
            # SIG_DFL para SIGTERM mata el proceso sin ejecutar ningún finally.
            actual = signal.getsignal(sig)
            check(
                f"{sig.name} ya no es la acción por defecto",
                actual not in (signal.SIG_DFL, None),
                True,
            )
    finally:
        for sig, previo in previos.items():
            try:
                signal.signal(sig, previo)
            except (OSError, ValueError, TypeError):
                pass


asyncio.run(probar_senales())


# ---------------------------------------------------------------------- #
# 4 · `stop_background_tasks` toca todo lo que debe
# ---------------------------------------------------------------------- #

print("\n-- contenido de stop_background_tasks " + "-" * 34)

import inspect  # noqa: E402

from core import background_tasks  # noqa: E402

fuente = inspect.getsource(background_tasks.stop_background_tasks)
for aguja, etiqueta in (
    ("flush_rank_data", "vuelca el histórico de rangos"),
    ("close_riot_client", "cierra el cliente de Riot"),
    ("close_session", "cierra la sesión de dpm.lol"),
    ("loop.cancel()", "cancela las tareas periódicas"),
):
    check(etiqueta, aguja in fuente, True)

# Que el arranque y el apagado cubran las mismas tareas: si se añade un
# `tasks.loop` nuevo y se olvida en el apagado, seguiría corriendo tras cerrar.
arranque = set(inspect.getsource(background_tasks.start_background_tasks).split())
apagado = set(fuente.split())
tareas = [
    n for n, v in vars(background_tasks).items()
    if hasattr(v, "is_running") and hasattr(v, "cancel")
]
sin_parar = [t for t in tareas if f"{t}," not in fuente and f"{t}\n" not in fuente]
check("toda tarea periódica se cancela al cerrar", sin_parar, [])
check("hay tareas que cancelar (la prueba no está vacía)", len(tareas) >= 7, True)


# ---------------------------------------------------------------------- #
# Limpieza y resumen
# ---------------------------------------------------------------------- #

for f in (fichero, Path(str(fichero) + ".bak"), Path(str(fichero) + ".tmp")):
    try:
        f.unlink()
    except OSError:
        pass
try:
    os.rmdir(tmpdir)
except OSError:
    pass

print("\n" + "=" * 74)
print("RESUMEN")
print("=" * 74)
print(f"   comprobaciones : {comprobaciones}")
print(f"   fallos         : {len(fallos)}")
for f in fallos:
    print(f"     - {f}")
print(f"\n   RANK_FLUSH_INTERVAL = {config.RANK_FLUSH_INTERVAL}s "
      f"-> es lo que se perdía en cada reinicio sin cierre ordenado.")

sys.exit(1 if fallos else 0)

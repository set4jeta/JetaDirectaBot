"""Prueba de humo del apagado: arranca el bot de verdad y le manda la señal.

`scripts/test_shutdown.py` prueba las piezas por separado (el volcado forzado,
la reentrancia de `_apagar`, que las señales queden enganchadas). Esto prueba lo
único que esas pruebas no pueden: que en un **proceso real**, con Discord
conectado y las tareas de fondo corriendo, la señal llega y el cierre se
completa. Es la diferencia entre "la función existe y funciona" y "el proceso se
apaga bien".

Qué mira:

* Que aparezca `Apagando (...)` -> la señal se recibió y el manejador corrió.
* Que aparezca `Tareas detenidas y clientes HTTP cerrados.` -> el cierre llegó
  hasta el final, incluido el volcado de rangos.
* Que el proceso **termine solo**, sin necesidad de matarlo.

En Windows se manda `CTRL_BREAK_EVENT` porque `SIGTERM` no es enviable: `os.kill`
acaba en `TerminateProcess`, que no ejecuta manejadores. En Linux (Render) se
manda `SIGTERM`, que es exactamente la que usa la plataforma.

Uso:
    python scripts/test_shutdown_live.py [segundos_de_espera]
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ESPERA_ARRANQUE = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
ESPERA_CIERRE = 45.0

# Señales de arranque: no se manda la señal hasta ver que el bot está en marcha.
#
# `"Bot conectado como"` era el hito original y **ya no se imprime nunca** en el
# camino normal: `core/arranque.mostrar()` sustituyó esa línea por el banner, y
# solo la usa como respaldo si el banner revienta. Este test seguía esperándola,
# así que fallaba con "el bot no llegó a arrancar en 25s" con el bot arrancado y
# conectado — un falso negativo que además impedía llegar a probar el apagado,
# que es lo único que este script existe para probar.
HITOS = ("JetaDirectaBot — listo", "Tareas iniciadas")

# Lo que tiene que aparecer *después* de la señal.
CIERRE = "Tareas detenidas y clientes HTTP cerrados."


def main() -> int:
    log_path = ROOT / "shutdown_live.log"
    log = log_path.open("w", encoding="utf-8", errors="replace")

    # En Windows hay que crear el grupo de procesos para poder mandar el
    # CTRL_BREAK; en POSIX, `start_new_session` evita que la señal del terminal
    # llegue por otra vía y confunda el resultado.
    extra = {}
    if sys.platform == "win32":
        extra["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        extra["start_new_session"] = True

    print(f"Arrancando el bot (log en {log_path.name})...")
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        **extra,
    )

    try:
        # 1 · Esperar a que el bot esté realmente en marcha.
        limite = time.time() + ESPERA_ARRANQUE
        vistos: set[str] = set()
        while time.time() < limite and len(vistos) < len(HITOS):
            if proc.poll() is not None:
                print(f"FALLO: el bot murió al arrancar (código {proc.returncode}).")
                return 1
            texto = log_path.read_text(encoding="utf-8", errors="replace")
            vistos = {h for h in HITOS if h in texto}
            time.sleep(0.5)

        if len(vistos) < len(HITOS):
            faltan = [h for h in HITOS if h not in vistos]
            print(f"FALLO: el bot no llegó a arrancar en {ESPERA_ARRANQUE:.0f}s.")
            print(f"       No apareció: {faltan}")
            proc.kill()
            return 1

        print(f"   ok   bot arrancado (pid {proc.pid})")

        # 2 · Mandar la señal de apagado.
        if sys.platform == "win32":
            print("   ->   enviando CTRL_BREAK_EVENT (SIGTERM no es enviable en Windows)")
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        else:
            print("   ->   enviando SIGTERM (la que usa Render)")
            proc.send_signal(signal.SIGTERM)

        t0 = time.time()

        # 3 · Esperar a que termine por su propio pie.
        try:
            codigo = proc.wait(timeout=ESPERA_CIERRE)
        except subprocess.TimeoutExpired:
            print(f"FALLO: no terminó en {ESPERA_CIERRE:.0f}s; se mata a la fuerza.")
            proc.kill()
            proc.wait(timeout=10)
            _informe(log_path)
            return 1

        tardanza = time.time() - t0
        print(f"   ok   terminó solo en {tardanza:.1f}s (código {codigo})")
    finally:
        log.close()
        if proc.poll() is None:
            proc.kill()

    return _informe(log_path)


def _informe(log_path: Path) -> int:
    texto = log_path.read_text(encoding="utf-8", errors="replace")
    fallos = []

    if "Apagando (" not in texto:
        fallos.append("no se recibió la señal: falta la línea 'Apagando (...)'")
    else:
        linea = next(l for l in texto.splitlines() if "Apagando (" in l)
        print(f"   ok   señal recibida: {linea.split('|')[-1].strip()}")

    if CIERRE not in texto:
        fallos.append(f"el cierre no llegó al final: falta '{CIERRE}'")
    else:
        print(f"   ok   cierre completo: se volcaron los rangos y se cerró el HTTP")

    # Un traceback durante el apagado no impide que termine, pero sí que se haya
    # volcado todo: hay que verlo.
    if "Error parando las tareas de fondo" in texto:
        fallos.append("hubo una excepción dentro de stop_background_tasks")

    print()
    if fallos:
        print("RESULTADO: FALLO")
        for f in fallos:
            print(f"   - {f}")
        print(f"\nRevisa el log completo en {log_path}")
        return 1

    print("RESULTADO: OK — el apagado ordenado funciona en un proceso real.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

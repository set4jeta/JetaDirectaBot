"""Prueba headless de `!historial`.

Ejecuta el mismo código que usa el comando (no una copia) contra dpm.lol real
y comprueba:

1. Que el historial global devuelve una partida por jugador.
2. Que la línea sale formateada, con campeón, K/D/A y **posición**.
3. Que la búsqueda por nick y por cuenta encuentra al jugador.
4. Cuánto tarda y cuánta memoria retiene.

Uso:  python scripts/test_historial.py
"""

from __future__ import annotations

import asyncio
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apis.dpm_api import close_session  # noqa: E402
from tracking.soloq.accounts_io import load_tracked_accounts  # noqa: E402
from utils.match_format import formatear_partida, nick_con_equipo  # noqa: E402

from core.historial_commands import (  # noqa: E402
    _buscar_jugador,
    _cuenta_str,
    _partir_mensaje,
    partidas_de_jugadores,
    una_por_jugador,
)


async def main() -> None:
    jugadores = load_tracked_accounts()
    if not jugadores:
        print("No hay jugadores registrados.")
        return

    cuentas = sum(len(j.accounts) for j in jugadores)
    print(f"jugadores={len(jugadores)}  cuentas={cuentas}")
    print()

    # --- 1 · busqueda por nick y por cuenta -------------------------------
    print("== 1 · busqueda de jugadores ==")
    pruebas = [jugadores[0].name]
    if jugadores[0].accounts:
        pruebas.append(_cuenta_str(jugadores[0].accounts[0]))
    if len(jugadores) > 1:
        pruebas.append(jugadores[1].name)
    pruebas.append("noexiste12345")

    for objetivo in pruebas:
        jugador, cuenta = _buscar_jugador(jugadores, objetivo)
        if jugador:
            print(f"  '{objetivo}' -> {jugador.name}" + (f" [cuenta {cuenta}]" if cuenta else ""))
        else:
            print(f"  '{objetivo}' -> no encontrado")
    print()

    # --- 2 · historial global ---------------------------------------------
    print("== 2 · historial global ==")
    tracemalloc.start()
    t0 = time.perf_counter()
    partidas = await partidas_de_jugadores(jugadores)
    dt = time.perf_counter() - t0
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"  partidas recogidas : {len(partidas)}")
    print(f"  tiempo             : {dt:.1f}s")
    print(f"  pico / retenido    : {peak/1024/1024:.1f} MB / {cur/1024/1024:.1f} MB")

    seleccion = una_por_jugador(partidas)
    print(f"  una por jugador    : {len(seleccion)}")

    if not seleccion:
        print("  Sin partidas, no se puede seguir.")
        await close_session()
        return

    # --- 3 · formateo (comprueba que la posicion ya no sale vacia) --------
    print()
    print("== 3 · lineas formateadas ==")
    con_pos = 0
    for i, p in enumerate(seleccion[:6], 1):
        jugador = p["jugador"]
        nick = nick_con_equipo(
            jugador.name, jugador.team,
            _cuenta_str(jugador.accounts[0]) if jugador.accounts else "",
        )
        linea = formatear_partida(p["participante"], p["match"])
        if "(" in linea:
            con_pos += 1
        print(f"  {i}. {linea} | {nick}")

    print()
    print(f"  lineas con posicion: {con_pos}/{min(6, len(seleccion))}")

    # --- 4 · partir mensajes largos ---------------------------------------
    print()
    print("== 4 · partir mensajes largos ==")
    largo = "\n".join(f"{i}. " + "x" * 120 for i in range(40))
    trozos = _partir_mensaje(largo)
    print(f"  texto de {len(largo)} chars -> {len(trozos)} trozos "
          f"(max {max(len(t) for t in trozos)} chars)")

    await close_session()


if __name__ == "__main__":
    asyncio.run(main())

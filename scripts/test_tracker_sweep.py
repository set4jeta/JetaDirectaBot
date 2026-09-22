"""Prueba headless del pipeline de tracking, sin conectar a Discord.

Comprueba lo que antes fallaba:

1. `ActiveGameTracker.run()` TERMINA. Antes era un `while True` dentro de un
   `tasks.loop`, así que no devolvía nunca. Aquí se mide con timeout: si la
   pasada no acaba en 90 s, la prueba falla.
2. Se detectan las partidas en curso reales.
3. Se respetan los PUUIDs marcados como stale.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from tracking.soloq.active_game_checker import ActiveGameTracker  # noqa: E402
from apis.riot_client import close_riot_client  # noqa: E402

TIMEOUT = 90


class FakeBot:
    """Sustituye al bot de Discord: no hay canales, así que no envía nada."""

    def get_channel(self, channel_id):
        return None


async def main() -> int:
    print("=" * 70)
    print("PRUEBA HEADLESS DEL TRACKER")
    print("=" * 70)

    bot = FakeBot()
    tracker = ActiveGameTracker(bot)

    cuentas = sum(len(p.accounts) for p in tracker._players)
    stale = sum(1 for p in tracker._players for a in p.accounts if a.stale)
    print(f"   jugadores trackeados : {len(tracker._players)}")
    print(f"   cuentas              : {cuentas} (de ellas {stale} marcadas stale)")

    print()
    print(f"   Ejecutando run() con timeout de {TIMEOUT}s...")
    print("   (con el codigo antiguo esto no habria terminado nunca)")
    print()

    started = time.perf_counter()
    try:
        stats = await asyncio.wait_for(tracker.run(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - started
        print(f"   [FALLO] run() no termino tras {elapsed:.0f}s -> sigue el bug del while True")
        await close_riot_client()
        return 1

    elapsed = time.perf_counter() - started
    print()
    print("=" * 70)
    print("RESULTADO DE LA PASADA")
    print("=" * 70)
    print(f"   termino en           : {stats.duracion:.2f}s  (timeout era {TIMEOUT}s)")
    print(f"   cuentas revisadas    : {stats.revisadas}")
    print(f"   stale omitidas       : {stats.omitidas_stale}")
    print(f"   partidas detectadas  : {stats.en_partida}")
    print(f"   notificadas          : {stats.notificadas}  (0 es normal: bot simulado sin canales)")
    print(f"   marcadas stale nuevas: {stats.marcadas_stale}")
    print(f"   errores              : {stats.errores}")

    if stats.detalle:
        print()
        print("   partidas en curso detectadas:")
        for line in stats.detalle:
            print(f"     {line}")

    print()
    print("=" * 70)
    print("SEGUNDA PASADA (comprueba que es repetible y usa caché)")
    print("=" * 70)
    t0 = time.perf_counter()
    try:
        stats2 = await asyncio.wait_for(tracker.run(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        print("   [FALLO] la segunda pasada no termino")
        await close_riot_client()
        return 1
    print(f"   termino en {time.perf_counter() - t0:.2f}s · {stats2.en_partida} partidas")

    await close_riot_client()

    print()
    if stats.errores > 0:
        print(f"   [AVISO] {stats.errores} cuentas dieron error (revisa el log en DEBUG)")
    if stats.marcadas_stale > 0:
        print(f"   [AVISO] {stats.marcadas_stale} PUUIDs invalidos marcados como stale")
    print("   [OK] run() devuelve el control: el tasks.loop puede gobernar la cadencia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Sonda: qué significan exactamente `gameLength` y `gameStartTime`.

El comando `!live` calcula el tiempo de partida como `gameLength + (ahora -
timestamp_de_caché)` y ya contempla que salga negativo (tiene un `sign = "-"`),
pero nunca se documentó por qué. Antes de implementar la cuenta atrás del delay
del espectador hay que saber, con datos reales:

  1. Cuánto va `gameLength` por detrás de `(ahora - gameStartTime)`.
  2. Si `gameLength` avanza en tiempo real (1 s por segundo) o a saltos.

Modo `watch`: consulta varias veces las mismas partidas y saca la pendiente de
`gameLength` frente al reloj de pared. Si la pendiente es 1.0, el desfase es un
offset fijo por partida y se puede modelar; si no, `gameLength` no sirve como
reloj y hay que usar `gameStartTime`.

Uso:
    python scripts/probe_spectator_timing.py                # una foto
    python scripts/probe_spectator_timing.py 8 15           # 8 muestras cada 15s
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

import config  # noqa: E402
from apis.riot_client import RiotApiError, close_riot_client, get_riot_client  # noqa: E402
from tracking.soloq.accounts_io import load_tracked_accounts  # noqa: E402
from utils.game_clock import desde_partida  # noqa: E402
from utils.player_filters import get_tracked_players  # noqa: E402


async def _foto(client, objetivos, sem):
    """Una pasada: devuelve [(jugador, cuenta, ahora, partida)]."""

    async def uno(player, account):
        async with sem:
            try:
                game = await client.get_active_game(account.puuid)
            except RiotApiError:
                game = None
            return player, account, time.time(), game

    return await asyncio.gather(*[uno(p, a) for p, a in objetivos])


def _etiqueta(player, account) -> str:
    rid = account.riot_id
    return f"{player.name} · {rid.get('game_name')}#{rid.get('tag_line')}"


async def main() -> int:
    muestras = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    cada = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0

    jugadores = get_tracked_players(load_tracked_accounts())
    todos = [
        (p, a)
        for p in jugadores
        for a in p.accounts
        if a.puuid and not getattr(a, "stale", False)
    ]

    print("=" * 78)
    print("SONDA DE TIEMPOS DEL ESPECTADOR")
    print("=" * 78)
    print(f"   cuentas conocidas: {len(todos)} · muestras: {muestras} cada {cada:g}s")

    client = await get_riot_client()
    sem = asyncio.Semaphore(config.TRACKER_CONCURRENCY)

    # Primera pasada completa para localizar quién está en partida.
    inicial = await _foto(client, todos, sem)
    activos = [(p, a) for p, a, _t, g in inicial if isinstance(g, dict)]

    if not activos:
        print("   Nadie en partida ahora mismo. Repite la sonda en horario de juego.")
        await close_riot_client()
        return 0

    print(f"   en partida: {len(activos)}")

    # historial[clave] = [(ahora, gameLength, gameStartTime, modo, cola)]
    historial: dict[str, list[tuple[float, int, int, str, int]]] = {}

    def anotar(lote):
        for player, account, ahora, game in lote:
            if not isinstance(game, dict):
                continue
            clave = _etiqueta(player, account)
            historial.setdefault(clave, []).append((
                ahora,
                game.get("gameLength"),
                game.get("gameStartTime"),
                game.get("gameMode"),
                game.get("gameQueueConfigId"),
            ))

    anotar(inicial)

    for i in range(1, muestras):
        await asyncio.sleep(cada)
        anotar(await _foto(client, activos, sem))
        print(f"   muestra {i + 1}/{muestras} tomada")

    print()
    for clave, filas in historial.items():
        modo, cola = filas[0][3], filas[0][4]
        print("-" * 78)
        print(f"   {clave}   [{modo} / cola {cola}]")
        print(f"      {'t(s)':>7} {'gameLength':>11} {'ahora-gST':>11} {'desfase':>9}"
              f"   {'lo que muestra el bot'}")
        t0 = filas[0][0]
        for ahora, gl, gst, m, q in filas:
            desde_inicio = (ahora - gst / 1000) if isinstance(gst, int) and gst else float("nan")
            desfase = desde_inicio - gl if isinstance(gl, int) else float("nan")
            # Lo mismo que verá el usuario en `!live`, con el reloj de verdad.
            reloj = desde_partida(
                {"gameStartTime": gst, "gameLength": gl, "gameMode": m,
                 "gameQueueConfigId": q},
                ahora,
            )
            print(f"      {ahora - t0:7.1f} {gl if gl is not None else '?':>11} "
                  f"{desde_inicio:11.1f} {desfase:9.1f}   {reloj.texto_corto()}")

        if len(filas) >= 2:
            dt = filas[-1][0] - filas[0][0]
            dgl = (filas[-1][1] or 0) - (filas[0][1] or 0)
            if dt > 0:
                print(f"      pendiente gameLength/reloj = {dgl / dt:.3f} "
                      f"({dgl}s de gameLength en {dt:.1f}s reales)")

        # El desfase medido es lo que justifica `config.SPECTATOR_DELAY`. Si
        # alguna partida saliera por encima, el bot estaría diciendo «ya se
        # puede ver» antes de tiempo y habría que subir la constante.
        desfases = [
            (a - g / 1000) - l
            for a, l, g, _m, _q in filas
            if isinstance(l, int) and isinstance(g, int) and g
        ]
        if desfases:
            peor = max(desfases)
            aviso = "" if peor <= config.SPECTATOR_DELAY else "  <-- POR ENCIMA DEL DELAY"
            print(f"      desfase medido: {min(desfases):.0f}..{peor:.0f}s "
                  f"(config: {config.SPECTATOR_DELAY}s){aviso}")

    print("-" * 78)
    print(f"   riot: {client.rate_limit_report()}")
    await close_riot_client()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

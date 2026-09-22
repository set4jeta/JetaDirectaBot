"""Reproduce la ráfaga de 429 del arranque.

Qué se vio en el log
--------------------
A 1 s de `Tareas iniciadas` salen **exactamente 12** `429 en
spectator-v5.active-games` con `Retry-After=23`, y luego se repiten en ráfagas
de 12 cada minuto. 12 es justo `TRACKER_CONCURRENCY`, así que las 12 corrutinas
en vuelo reciben el 429 a la vez.

Y no cuadra con los límites que Riot reporta para esta key:

    X-App-Rate-Limit:    500:10,30000:600
    X-Method-Rate-Limit: 3000:10,180000:600   (spectator-v5)

93 cuentas cada 30 s no se acerca a eso. Con 12 peticiones en paralelo tampoco
se reproduce (probado en `_429_probe.py`: 6 rondas, 0 errores). Lo que sí pasa al
arrancar es que **todas** las tareas hacen su primera pasada a la vez:

    check_games_loop      ~93 spectator-v5
    refrescar_rangos      ~93 league-v4   (before_loop -> refrescar_todo)
    actualizar_puuids     ~645 account-v1
    precalentar_historial  22 x2 dpm.lol
    infoplayers            60 dpm.lol
    actualizar_accounts    leaderboard + 12 equipos

Así que aquí se reproduce ese pico y se leen las cabeceras del 429 de verdad,
en vez de suponer de qué límite se trata.
"""
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: F401  (carga el .env)
from apis.riot_client import get_riot_client
from tracking.soloq.accounts_io import load_tracked_accounts
from utils.player_filters import get_tracked_players

CABECERAS = (
    "X-Rate-Limit-Type",
    "Retry-After",
    "X-App-Rate-Limit",
    "X-App-Rate-Limit-Count",
    "X-Method-Rate-Limit",
    "X-Method-Rate-Limit-Count",
)


def puuids() -> list[str]:
    out, vistos = [], set()
    for p in get_tracked_players(load_tracked_accounts()):
        for acc in p.accounts:
            if acc.puuid and not getattr(acc, "stale", False) and acc.puuid not in vistos:
                vistos.add(acc.puuid)
                out.append(acc.puuid)
    return out


async def crudo(client, url: str) -> tuple[str, int, dict, str]:
    """Petición SIN pasar por el limitador: así se ve el límite de Riot, no el nuestro."""
    async with client.session.get(url) as resp:
        cuerpo = (await resp.text())[:160] if resp.status >= 400 else ""
        return url, resp.status, dict(resp.headers), cuerpo


async def main() -> None:
    client = await get_riot_client()
    ps = puuids()
    print(f"{len(ps)} puuids seguidos\n")

    urls = []
    for p in ps:
        urls.append(client._url("euw1", f"/lol/spectator/v5/active-games/by-summoner/{p}"))
        urls.append(client._url("euw1", f"/lol/league/v4/entries/by-puuid/{p}"))
    print(f"disparando {len(urls)} peticiones DE GOLPE (sin limitador)...")

    res = await asyncio.gather(*(crudo(client, u) for u in urls), return_exceptions=True)

    conteo = Counter()
    primer_429 = None
    for r in res:
        if isinstance(r, Exception):
            conteo[f"EXC {type(r).__name__}"] += 1
            continue
        url, status, headers, cuerpo = r
        endpoint = "spectator-v5" if "spectator" in url else "league-v4"
        conteo[f"{endpoint} {status}"] += 1
        if status == 429 and primer_429 is None:
            primer_429 = (endpoint, headers, cuerpo)

    for k in sorted(conteo):
        print(f"   {k}: {conteo[k]}")

    if primer_429:
        endpoint, headers, cuerpo = primer_429
        print(f"\n--- CABECERAS DEL 429 ({endpoint}) ---")
        for h in CABECERAS:
            print(f"   {h}: {headers.get(h, '(ausente)')}")
        print(f"   [cuerpo] {cuerpo!r}")
        print("   --- todas las cabeceras ---")
        for k, v in headers.items():
            print(f"     {k}: {v}")
    else:
        print("\nNingún 429: el pico no basta para reproducirlo.")

    await client.close()


asyncio.run(main())

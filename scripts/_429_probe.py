"""Captura un 429 real de spectator-v5 y enseña TODAS sus cabeceras.

Por qué
-------
El log del bot muestra ráfagas de exactamente 12 x `429 ... Retry-After=23` en
`spectator-v5.active-games`, una cada ~60 s. Con los límites que Riot reporta
para esta key eso no debería ocurrir:

    X-App-Rate-Limit:    500:10,30000:600
    X-Method-Rate-Limit: 3000:10,180000:600   (spectator-v5)

93 peticiones cada 30 s no se acerca a ninguno. Así que el 429 no es de
aplicación ni de método: hay que leer `X-Rate-Limit-Type` y el resto de
cabeceras del 429 de verdad en vez de suponerlo.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: F401  (carga el .env)
from apis.riot_client import get_riot_client
from tracking.soloq.accounts_io import load_tracked_accounts
from utils.player_filters import get_tracked_players

CONCURRENCIA = 12
RONDAS = 6


def puuids(n: int) -> list[str]:
    jugadores = get_tracked_players(load_tracked_accounts())
    out = []
    for p in jugadores:
        for acc in p.accounts:
            if acc.puuid and not getattr(acc, "stale", False):
                out.append(acc.puuid)
                if len(out) >= n:
                    return out
    return out


async def pedir(client, puuid: str) -> tuple[int, dict, str]:
    url = client._url("euw1", f"/lol/spectator/v5/active-games/by-summoner/{puuid}")
    async with client.session.get(url) as resp:
        cuerpo = ""
        if resp.status == 429:
            cuerpo = (await resp.text())[:200]
        return resp.status, dict(resp.headers), cuerpo


async def main() -> None:
    client = await get_riot_client()
    objetivos = puuids(CONCURRENCIA)
    print(f"{len(objetivos)} puuids, {CONCURRENCIA} en paralelo, {RONDAS} rondas\n")

    visto_429 = False
    for ronda in range(1, RONDAS + 1):
        res = await asyncio.gather(*(pedir(client, p) for p in objetivos))
        codigos = {}
        for status, _h, _b in res:
            codigos[status] = codigos.get(status, 0) + 1
        print(f"ronda {ronda}: {codigos}")

        for status, headers, cuerpo in res:
            if status == 429 and not visto_429:
                visto_429 = True
                print("\n--- CABECERAS DEL 429 ---")
                for k, v in headers.items():
                    print(f"   {k}: {v}")
                print(f"   [cuerpo] {cuerpo!r}")
                print("--- fin ---\n")

        await asyncio.sleep(2)

    if not visto_429:
        print("\nNo se reprodujo ningún 429 con esta pauta.")
    print("\nreporte del cliente:", client.rate_limit_report())
    await client.close()


asyncio.run(main())

"""¿Existe un límite de servicio en spectator-v5 que no aparece en las cabeceras?

El hecho a explicar
-------------------
En el arranque real, **1 segundo** después de `Tareas iniciadas`, salen 12 x
`429 en spectator-v5.active-games` con `Retry-After=23`. En ese instante el bot
solo había hecho ~122 peticiones, así que NO puede ser el límite de aplicación
(500:10). Y las 110 peticiones simultáneas a `account-v1` de la misma ráfaga
pasaron sin problema, así que es específico de spectator.

Además, el 429 del límite de aplicación ya está medido y trae
`X-Rate-Limit-Type: application` con `Retry-After: 10`, no 23.

Aquí se disparan ráfagas de 93 peticiones a spectator-v5 (una pasada completa
del tracker) sin pausa, y se anota el tipo y el `Retry-After` de cada 429.
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

RONDAS = 10


def puuids() -> list[str]:
    out, vistos = [], set()
    for p in get_tracked_players(load_tracked_accounts()):
        for acc in p.accounts:
            if acc.puuid and not getattr(acc, "stale", False) and acc.puuid not in vistos:
                vistos.add(acc.puuid)
                out.append(acc.puuid)
    return out


async def crudo(client, url: str):
    async with client.session.get(url) as resp:
        return resp.status, dict(resp.headers)


async def main() -> None:
    client = await get_riot_client()
    ps = puuids()
    urls = [
        client._url("euw1", f"/lol/spectator/v5/active-games/by-summoner/{p}")
        for p in ps
    ]
    print(f"{len(urls)} peticiones a spectator-v5 por ronda, {RONDAS} rondas seguidas\n")

    total = Counter()
    for ronda in range(1, RONDAS + 1):
        res = await asyncio.gather(*(crudo(client, u) for u in urls),
                                  return_exceptions=True)
        conteo = Counter()
        muestra = None
        for r in res:
            if isinstance(r, Exception):
                conteo[f"EXC {type(r).__name__}"] += 1
                continue
            status, headers = r
            if status == 429:
                clave = (headers.get("X-Rate-Limit-Type"), headers.get("Retry-After"))
                conteo[f"429 {clave}"] += 1
                if muestra is None:
                    muestra = headers
            else:
                conteo[status] += 1
        total.update(conteo)
        detalle = "  ".join(f"{k}={v}" for k, v in sorted(conteo.items(), key=str))
        print(f"ronda {ronda:2d}: {detalle}")
        if muestra is not None:
            print(f"           app={muestra.get('X-App-Rate-Limit-Count')} "
                  f"method={muestra.get('X-Method-Rate-Limit-Count')} "
                  f"limite_metodo={muestra.get('X-Method-Rate-Limit')}")

    print("\nTOTAL:", dict(total))
    await client.close()


asyncio.run(main())

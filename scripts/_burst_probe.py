"""Cruza a propósito el límite de 500:10 para leer el 429 de verdad.

Por qué hace falta
-----------------
En el arranque real salen `429 en spectator-v5.active-games` con
`Retry-After=23`, pero con 186 peticiones de golpe no se reproduce
(`_herd_probe.py`: 0 errores). La suma real del arranque es otra:

    puuid_repair (accounts.json)        535  account-v1
    puuid_repair (accounts_from_teams)  110  account-v1
    rank_warm.refrescar_todo             93  league-v4
    check_games_loop                     93  spectator-v5
                                       ----
                                        831  en unos pocos segundos

Eso sí pasa de 500 en 10 s. La pregunta que hay que contestar con datos, no
suponiendo, es de qué límite es el 429 (`X-Rate-Limit-Type`) y por qué el
`Retry-After` es 23 y no 10.

Se lanzan 700 peticiones al endpoint más barato, una sola vez.
"""
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: F401  (carga el .env)
from apis.riot_client import get_riot_client

TOTAL = 700


async def crudo(client, url: str):
    async with client.session.get(url) as resp:
        cuerpo = (await resp.text())[:120] if resp.status >= 400 else ""
        return resp.status, dict(resp.headers), cuerpo


async def main() -> None:
    client = await get_riot_client()

    # by-riot-id con un nombre real: 200 si hay cupo, 429 si no.
    url = client._url("europe", "/riot/account/v1/accounts/by-riot-id/Caps/G2W")

    print(f"lanzando {TOTAL} peticiones de golpe (sin limitador local)...")
    res = await asyncio.gather(*(crudo(client, url) for _ in range(TOTAL)),
                              return_exceptions=True)

    conteo = Counter()
    primer_429 = None
    for r in res:
        if isinstance(r, Exception):
            conteo[f"EXC {type(r).__name__}"] += 1
            continue
        status, headers, cuerpo = r
        conteo[status] += 1
        if status == 429 and primer_429 is None:
            primer_429 = (headers, cuerpo)

    for k in sorted(conteo, key=str):
        print(f"   {k}: {conteo[k]}")

    if primer_429:
        headers, cuerpo = primer_429
        print("\n--- CABECERAS DEL 429 ---")
        for k, v in headers.items():
            print(f"   {k}: {v}")
        print(f"   [cuerpo] {cuerpo!r}")
    else:
        print("\nNingún 429 con 700 de golpe.")

    await client.close()


asyncio.run(main())

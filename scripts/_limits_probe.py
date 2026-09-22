"""Qué límites reales devuelve Riot para esta key.

El log muestra 12 x 429 con Retry-After=23 en `spectator-v5.active-games` cada
dos pasadas. Con una key de producción (500/10s) eso no debería pasar nunca,
así que hay que ver los headers de verdad en vez de suponerlos.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: F401  (carga el .env)
from apis.riot_client import get_riot_client

INTERESAN = (
    "X-App-Rate-Limit",
    "X-App-Rate-Limit-Count",
    "X-Method-Rate-Limit",
    "X-Method-Rate-Limit-Count",
    "Retry-After",
    "X-Rate-Limit-Type",
)


async def main() -> None:
    client = await get_riot_client()

    # 1) Un endpoint de cuenta, barato.
    url = client._url(
        "europe", "/riot/account/v1/accounts/by-riot-id/Caps/G2W"
    )
    async with client.session.get(url) as resp:
        print("account-v1.by-riot-id ->", resp.status)
        for h in INTERESAN:
            if h in resp.headers:
                print(f"   {h}: {resp.headers[h]}")
        data = await resp.json(content_type=None)
    puuid = (data or {}).get("puuid")
    print("   puuid:", "ok" if puuid else "NO")

    if not puuid:
        await client.close()
        return

    # 2) El endpoint que da los 429: spectator-v5.
    url = client._url("euw1", f"/lol/spectator/v5/active-games/by-summoner/{puuid}")
    async with client.session.get(url) as resp:
        print("\nspectator-v5.active-games ->", resp.status)
        for h in INTERESAN:
            if h in resp.headers:
                print(f"   {h}: {resp.headers[h]}")

    await client.close()


asyncio.run(main())

"""Se pueden trackear de verdad las ligas no europeas?

El leaderboard por liga (`/v1/esport/soloq/leagues/<liga>/leaderboard`) es la
fuente del roster. Aqui se comprueba, liga por liga, cuantas de sus cuentas
consigue resolver Riot por riot_id: si son cero, esa liga se puede anunciar pero
no se puede seguir, y eso hay que saberlo antes de venderlo.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from apis.dpm_api import fetch_league_leaderboard  # noqa: E402
from apis.riot_client import (  # noqa: E402
    RiotApiError,
    close_riot_client,
    get_riot_client,
    normalizar_plataforma,
)

LIGAS = ["lec", "lck", "lcs", "lpl", "lla", "cblol"]
MUESTRA = 8


async def resolver(client, gn: str, tl: str) -> str | None:
    try:
        return await client.get_puuid(gn, tl)
    except RiotApiError:
        return None


async def main() -> None:
    client = await get_riot_client()
    print(f"{'liga':<7} {'entradas':>8} {'muestra':>8} {'resueltas':>10} {'plataformas'}")
    print("-" * 78)

    for liga in LIGAS:
        entradas = await fetch_league_leaderboard(liga)
        if not entradas:
            print(f"{liga:<7} {'0':>8}   (el leaderboard vino vacio)")
            continue

        plats = sorted({normalizar_plataforma(e.get("platform")) for e in entradas})
        muestra = entradas[:MUESTRA]
        resueltas = 0
        detalle = []
        for e in muestra:
            gn = e.get("gameName") or ""
            tl = e.get("tagLine") or ""
            puuid = await resolver(client, gn, tl)
            if puuid:
                resueltas += 1
            detalle.append(f"{'OK ' if puuid else '404'} {gn}#{tl}")

        print(f"{liga:<7} {len(entradas):>8} {len(muestra):>8} {resueltas:>10} "
              f"{','.join(plats)}")
        for d in detalle:
            print(f"          {d}")

    print()
    print(client.rate_limit_report())
    await close_riot_client()


if __name__ == "__main__":
    asyncio.run(main())

"""¿De qué límite es el `429 en spectator-v5 Retry-After=23` del arranque?

Ya está verificado que el límite de aplicación (500:10) responde
`X-Rate-Limit-Type: application` con `Retry-After: 10`. El log del bot, en
cambio, muestra **23**, y siempre en `spectator-v5.active-games`, en ráfagas de
exactamente 12 (= TRACKER_CONCURRENCY).

Aquí se reproduce la situación real del arranque: primero se saturan las
ventanas con `account-v1` (que es lo que hace `puuid_repair` con 645 cuentas) y
justo después se disparan 12 `spectator-v5`, que es lo que hace el tracker. Se
imprimen los pares (tipo, Retry-After) que devuelve Riot.
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

SATURAR = 560       # suficiente para pasar de 500:10
CONCURRENCIA = 12   # lo que usa el tracker


def un_puuid() -> str | None:
    for p in get_tracked_players(load_tracked_accounts()):
        for acc in p.accounts:
            if acc.puuid and not getattr(acc, "stale", False):
                return acc.puuid
    return None


async def crudo(client, url: str):
    async with client.session.get(url) as resp:
        return resp.status, dict(resp.headers)


async def main() -> None:
    client = await get_riot_client()
    puuid = un_puuid()
    if not puuid:
        print("sin puuids válidos")
        return

    cuenta_url = client._url("europe", "/riot/account/v1/accounts/by-riot-id/Caps/G2W")
    spec_url = client._url("euw1", f"/lol/spectator/v5/active-games/by-summoner/{puuid}")

    print(f"1) saturando la ventana con {SATURAR} x account-v1 ...")
    res = await asyncio.gather(*(crudo(client, cuenta_url) for _ in range(SATURAR)),
                              return_exceptions=True)
    pares = Counter()
    for r in res:
        if isinstance(r, Exception):
            pares[("EXC", type(r).__name__)] += 1
            continue
        status, headers = r
        if status == 429:
            pares[(headers.get("X-Rate-Limit-Type"), headers.get("Retry-After"))] += 1
        else:
            pares[(status, "-")] += 1
    for k in sorted(pares, key=str):
        print(f"   account-v1 {k}: {pares[k]}")

    print(f"\n2) inmediatamente, {CONCURRENCIA} x spectator-v5 (como el tracker) ...")
    res = await asyncio.gather(*(crudo(client, spec_url) for _ in range(CONCURRENCIA)),
                              return_exceptions=True)
    for i, r in enumerate(res, 1):
        if isinstance(r, Exception):
            print(f"   [{i:2d}] EXC {type(r).__name__}")
            continue
        status, headers = r
        if status == 429:
            print(f"   [{i:2d}] 429  tipo={headers.get('X-Rate-Limit-Type')}  "
                  f"Retry-After={headers.get('Retry-After')}  "
                  f"app={headers.get('X-App-Rate-Limit-Count')}  "
                  f"method={headers.get('X-Method-Rate-Limit-Count')}")
        else:
            print(f"   [{i:2d}] {status}  app={headers.get('X-App-Rate-Limit-Count')}")

    await client.close()


asyncio.run(main())

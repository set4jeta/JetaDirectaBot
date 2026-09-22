"""¿De dónde salen los 429 con `Retry-After=23` en spectator-v5?

El hecho a explicar
-------------------
En el run real de 26 minutos, 114 de los 128 429 fueron de `spectator-v5` con
`Retry-After` 22, 23 o 24. Los de `account-v1` fueron 10, que es lo que Riot
manda cuando se pasa el límite de aplicación (500:10) — medido.

Lo que delata el patrón: siempre son **12** a la vez (la concurrencia del
tracker) y siempre en el segundo :33-:35 del minuto. Sumando el `Retry-After`:

    :33 + 24 = :57      :34 + 23 = :57      :35 + 22 = :57

Los tres apuntan al **mismo segundo de reloj**. Eso es una ventana fija de 60 s
que se reinicia hacia el :57, no una ventana deslizante nuestra. Y las cabeceras
de spectator dicen `3000:10,180000:600`, así que no es el límite de método
publicado ni el de aplicación.

Qué hace esta sonda
-------------------
Imita al tracker exactamente —93 peticiones cada 30 s, nada más— y anota
`X-Rate-Limit-Type` de cada 429. Con `X-App-Rate-Limit-Count` a la vista se
puede descartar de un vistazo que sea nuestro cupo.

Ejecutar (tarda RONDAS × 30 s):
    python scripts/_spec_window_probe.py
"""
import asyncio
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: F401  (carga el .env)
from apis.riot_client import get_riot_client
from tracking.soloq.accounts_io import load_tracked_accounts
from utils.player_filters import get_tracked_players

RONDAS = 8
INTERVALO = 30.0


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
    urls = [
        client._url("euw1", f"/lol/spectator/v5/active-games/by-summoner/{p}")
        for p in puuids()
    ]
    print(f"{len(urls)} peticiones cada {INTERVALO:.0f}s, {RONDAS} rondas "
          f"(igual que el tracker: concurrencia 12)\n")

    sem = asyncio.Semaphore(12)

    async def acotada(url: str):
        async with sem:
            return await crudo(client, url)

    total = Counter()
    for ronda in range(1, RONDAS + 1):
        t0 = time.time()
        res = await asyncio.gather(*(acotada(u) for u in urls), return_exceptions=True)
        conteo, muestra = Counter(), None
        for r in res:
            if isinstance(r, Exception):
                conteo[f"EXC {type(r).__name__}"] += 1
                continue
            status, headers = r
            if status == 429:
                tipo = headers.get("X-Rate-Limit-Type", "sin-cabecera")
                ra = headers.get("Retry-After")
                conteo[f"429 tipo={tipo} Retry-After={ra}"] += 1
                if muestra is None:
                    muestra = headers
            else:
                conteo[status] += 1
        total.update(conteo)
        reloj = time.strftime("%H:%M:%S")
        print(f"ronda {ronda}/{RONDAS} @ {reloj} ({time.time() - t0:.1f}s): "
              + "  ".join(f"{k}={v}" for k, v in sorted(conteo.items(), key=str)))
        if muestra is not None:
            print(f"      app={muestra.get('X-App-Rate-Limit-Count')}"
                  f" / {muestra.get('X-App-Rate-Limit')}"
                  f"   metodo={muestra.get('X-Method-Rate-Limit-Count')}"
                  f" / {muestra.get('X-Method-Rate-Limit')}")
        if ronda < RONDAS:
            await asyncio.sleep(max(0.0, INTERVALO - (time.time() - t0)))

    print("\nTOTAL:", dict(total))
    await client.close()


asyncio.run(main())

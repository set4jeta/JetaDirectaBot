"""Cuantas de las cuentas sin PUUID se pueden recuperar, y de que servidor son.

Esto decide si el enrutado por plataforma sirve de algo HOY: una cuenta sin PUUID
la salta el tracker antes de llegar a preguntar por su servidor.
"""

from __future__ import annotations

import asyncio
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from apis.riot_client import (  # noqa: E402
    RiotApiError,
    close_riot_client,
    get_riot_client,
    normalizar_plataforma,
)
from tracking.soloq.accounts_io import load_tracked_accounts  # noqa: E402


async def main() -> None:
    client = await get_riot_client()
    sem = asyncio.Semaphore(10)

    faltan = []
    for j in load_tracked_accounts():
        for a in j.accounts:
            if not a.puuid:
                faltan.append((j.name, normalizar_plataforma(a.platform), a.riot_id))

    async def uno(entrada):
        nombre, plat, rid = entrada
        gn, tl = rid.get("game_name", ""), rid.get("tag_line", "")
        async with sem:
            try:
                puuid = await client.get_puuid(gn, tl)
            except RiotApiError:
                puuid = None
        return plat, bool(puuid), f"{gn}#{tl}"

    resultados = await asyncio.gather(*(uno(e) for e in faltan))

    rec = collections.Counter()
    perdidas = collections.Counter()
    ejemplos = collections.defaultdict(list)
    for plat, ok, etiqueta in resultados:
        if ok:
            rec[plat] += 1
            ejemplos[plat].append(etiqueta)
        else:
            perdidas[plat] += 1

    print(f"cuentas sin PUUID: {len(faltan)}")
    print()
    print(f"{'servidor':<8} {'recuperables':>13} {'perdidas':>10}")
    print("-" * 34)
    for plat in sorted(set(rec) | set(perdidas)):
        print(f"{plat:<8} {rec[plat]:>13} {perdidas[plat]:>10}")
    print("-" * 34)
    print(f"{'TOTAL':<8} {sum(rec.values()):>13} {sum(perdidas.values()):>10}")

    print()
    for plat, lista in sorted(ejemplos.items()):
        print(f"  {plat}: {', '.join(lista[:6])}")

    print()
    print(client.rate_limit_report())
    await close_riot_client()


if __name__ == "__main__":
    asyncio.run(main())

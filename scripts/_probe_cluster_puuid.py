"""Comprueba si `account-v1/by-riot-id` es realmente global.

`puuid_repair.CLUSTER = "europe"` asume que da igual el cluster. Si no lo fuera,
las cuentas de KR/NA/BR nunca conseguirian PUUID y el bot no las miraria nunca:
eso explicaria por que las 48 cuentas sin PUUID son exactamente las de fuera de
Europa. Aqui se prueban los tres clusters con las cuentas que fallan.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from apis.riot_client import RiotApiError, close_riot_client, get_riot_client  # noqa: E402
from tracking.soloq.accounts_io import load_tracked_accounts  # noqa: E402

CLUSTERS = ("europe", "americas", "asia")


async def probar(client, gn: str, tl: str) -> dict[str, str]:
    out = {}
    for cluster in CLUSTERS:
        try:
            puuid = await client.get_puuid(gn, tl, region=cluster)
            out[cluster] = (puuid[:16] + "...") if puuid else "None"
        except RiotApiError as exc:
            out[cluster] = f"HTTP {exc.status}"
    return out


async def main() -> None:
    sin_puuid = []
    for j in load_tracked_accounts():
        for a in j.accounts:
            if not a.puuid:
                sin_puuid.append((j.name, a.platform or "?", a.riot_id))

    print(f"cuentas sin PUUID: {len(sin_puuid)}")
    por_plat: dict[str, list] = {}
    for nombre, plat, rid in sin_puuid:
        por_plat.setdefault(plat, []).append((nombre, rid))
    print("por plataforma:", {k: len(v) for k, v in por_plat.items()})
    print()

    client = await get_riot_client()
    print(f"{'cuenta':<30} {'plat':<6} " + " ".join(f"{c:<20}" for c in CLUSTERS))
    print("-" * 100)

    for plat, cuentas in sorted(por_plat.items()):
        for _nombre, rid in cuentas[:3]:
            gn, tl = rid.get("game_name", ""), rid.get("tag_line", "")
            res = await probar(client, gn, tl)
            etiqueta = f"{gn}#{tl}"[:29]
            print(f"{etiqueta:<30} {plat:<6} " + " ".join(f"{res[c]:<20}" for c in CLUSTERS))

    print()
    print(client.rate_limit_report())
    await close_riot_client()


if __name__ == "__main__":
    asyncio.run(main())

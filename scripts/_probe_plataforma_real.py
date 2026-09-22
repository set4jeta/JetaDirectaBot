"""Mide el efecto real de enrutar por plataforma, contra la API de Riot.

Toma unas pocas cuentas de cada servidor y pide su rango DOS veces: como se
hacia antes (siempre euw1) y como se hace ahora (en su servidor). Es una prueba
de una sola vez para dejar constancia del numero, no un test del repositorio.
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
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

POR_SERVIDOR = 3


async def rango(client, puuid: str, plataforma: str) -> str:
    try:
        entrada = await client.get_soloq_rank(puuid, plataforma)
    except RiotApiError as exc:
        return f"HTTP {exc.status}"
    if not entrada:
        return "sin datos"
    return f"{entrada.get('tier')} {entrada.get('rank')} {entrada.get('leaguePoints')} LP"


async def main() -> None:
    por_plataforma: dict[str, list] = defaultdict(list)
    for jugador in load_tracked_accounts():
        for cuenta in jugador.accounts:
            if not cuenta.puuid or getattr(cuenta, "stale", False):
                continue
            plat = normalizar_plataforma(getattr(cuenta, "platform", None))
            if len(por_plataforma[plat]) < POR_SERVIDOR:
                por_plataforma[plat].append((jugador.name, cuenta))

    client = await get_riot_client()
    print(f"{'jugador':<14} {'servidor':<6} {'preguntando a euw1':<24} preguntando a su servidor")
    print("-" * 88)

    arregladas = 0
    total = 0
    for plat, cuentas in sorted(por_plataforma.items()):
        for nombre, cuenta in cuentas:
            total += 1
            viejo = await rango(client, cuenta.puuid, "euw1")
            nuevo = await rango(client, cuenta.puuid, plat)
            if viejo != nuevo:
                arregladas += 1
            marca = "  <-- ARREGLADO" if viejo != nuevo else ""
            print(f"{nombre[:13]:<14} {plat:<6} {viejo:<24} {nuevo}{marca}")

    print("-" * 88)
    print(f"{arregladas} de {total} cuentas devuelven un dato distinto al enrutar bien.")
    print(client.rate_limit_report())
    await close_riot_client()


if __name__ == "__main__":
    asyncio.run(main())

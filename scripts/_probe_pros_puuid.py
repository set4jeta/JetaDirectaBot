"""Por que 48 cuentas no consiguen PUUID (y son casi todas de fuera de EUW).

Compara, para unos pocos jugadores, lo que da dpm.lol `/v1/pros/<nombre>` con lo
que Riot reconoce. Tres hipotesis a distinguir:

  A. La cuenta ya no existe / se renombro  -> dato viejo, no hay nada que arreglar
  B. El PUUID de dpm SI vale en Riot       -> podemos usarlo y ganar 48 cuentas
  C. El riot_id de dpm esta mal escrito     -> hay que normalizarlo antes de pedir
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from tracking.soloq.accounts_from_teams import safe_request  # noqa: E402
from apis.riot_client import (  # noqa: E402
    RiotApiError,
    close_riot_client,
    get_riot_client,
    normalizar_plataforma,
)

JUGADORES = ["BrokenBlade", "Caps", "Hans Sama", "Vladi"]


async def main() -> None:
    client = await get_riot_client()

    for nombre in JUGADORES:
        resp = safe_request(f"https://dpm.lol/v1/pros/{quote(nombre)}")
        if resp is None:
            print(f"\n### {nombre}: dpm no responde")
            continue
        try:
            data = resp.json()
        except ValueError:
            print(f"\n### {nombre}: respuesta no-JSON")
            continue

        cuentas = (data or {}).get("players") or []
        print(f"\n### {nombre}: {len(cuentas)} cuentas en dpm")
        for c in cuentas:
            gn = c.get("gameName") or ""
            tl = c.get("tagLine") or ""
            plat = normalizar_plataforma(c.get("platform"))
            dpm_puuid = c.get("puuid") or ""

            # 1. resolver por riot id
            try:
                riot_puuid = await client.get_puuid(gn, tl)
            except RiotApiError as exc:
                riot_puuid = f"HTTP {exc.status}"

            # 2. el puuid de dpm, contra summoner-v4 en SU plataforma
            estado_dpm = "-"
            if dpm_puuid:
                try:
                    s = await client.get_summoner(dpm_puuid, platform=plat)
                    estado_dpm = f"nivel {s.get('summonerLevel')}" if s else "404"
                except RiotApiError as exc:
                    estado_dpm = f"HTTP {exc.status}"

            coincide = "="
            if isinstance(riot_puuid, str) and riot_puuid.startswith("HTTP"):
                coincide = "?"
            elif riot_puuid and dpm_puuid:
                coincide = "IGUALES" if riot_puuid == dpm_puuid else "DISTINTOS"

            print(f"  {gn}#{tl:<10} [{plat:<5}] "
                  f"riot_id->{str(riot_puuid)[:14]:<16} "
                  f"dpm_puuid->{dpm_puuid[:14]:<16} {estado_dpm:<12} {coincide}")

    print()
    print(client.rate_limit_report())
    await close_riot_client()


if __name__ == "__main__":
    asyncio.run(main())

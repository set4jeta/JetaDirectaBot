"""Qué devuelve exactamente /v1/esport/soloq/leagues/<codigo>/leaderboard.

Sirve para decidir si los rosters se pueden derivar del leaderboard (una
petición por liga) en vez de scrapear una página por equipo.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apis.dpm_api import _get_json  # noqa: E402

CODIGOS = ("lec", "lck", "msi", "lcp", "lla", "nacl")


async def main() -> None:
    for code in CODIGOS:
        data = await _get_json(f"/esport/soloq/leagues/{code}/leaderboard")
        if not isinstance(data, list):
            print(f"{code}: respuesta no lista -> {type(data).__name__}")
            continue

        equipos = sorted({
            (p.get("team") or "").strip()
            for p in data
            if isinstance(p, dict) and (p.get("team") or "").strip()
        })
        print(f"--- {code}: {len(data)} jugadores · {len(equipos)} equipos")

        if not data:
            continue

        print("    claves:", ", ".join(sorted(data[0].keys())))
        if code == "lec":
            print("    equipos:", equipos)
            print("    muestra:", json.dumps(data[0], ensure_ascii=False)[:700])


if __name__ == "__main__":
    asyncio.run(main())

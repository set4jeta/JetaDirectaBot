"""¿Se pueden derivar los rosters del leaderboard sin scrapear la ficha por equipo?

El leaderboard de `/esport/soloq/leagues/<liga>/leaderboard` da displayName y
team en una sola petición. Si `displayName` resuelve contra `/v1/pros/<nombre>`,
podemos saltarnos la página de cada equipo: 10 peticiones menos por liga y,
sobre todo, una fuente que se actualiza sola cuando un equipo se renombra.

Comprueba eso y de paso qué plataformas salen (hace falta para saber en qué
servidor consultar spectator-v5).
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apis.dpm_api import _get_json  # noqa: E402

LIGAS = ("lec", "lck", "lcs", "cblol")
MUESTRA = 6  # jugadores por liga, para no tardar una eternidad


async def main() -> None:
    for liga in LIGAS:
        data = await _get_json(f"/esport/soloq/leagues/{liga}/leaderboard")
        if not isinstance(data, list) or not data:
            print(f"{liga}: leaderboard vacío")
            continue

        nombres = [p.get("displayName") for p in data if p.get("displayName")]
        print(f"--- {liga}: {len(data)} jugadores, probando {MUESTRA}")

        plataformas: Counter[str] = Counter()
        for nombre in nombres[:MUESTRA]:
            info = await _get_json(f"/pros/{quote(nombre)}")
            cuentas = (info or {}).get("players", []) if isinstance(info, dict) else []
            if not cuentas:
                print(f"    {nombre}: SIN cuentas en /v1/pros")
                continue
            for c in cuentas:
                plataformas[(c.get("platform") or "?").upper()] += 1
            print(
                f"    {nombre}: {len(cuentas)} cuentas -> "
                + ", ".join(
                    f"{c.get('gameName')}#{c.get('tagLine')} "
                    f"[{(c.get('platform') or '?').upper()}]"
                    for c in cuentas
                )
            )

        print(f"    plataformas: {dict(plataformas)}")


if __name__ == "__main__":
    asyncio.run(main())

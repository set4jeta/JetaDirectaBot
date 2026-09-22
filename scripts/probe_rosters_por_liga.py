"""Prueba la derivación de rosters por liga sin tocar los ficheros del bot.

Comprueba las tres cosas que cambiaron:
  1. los equipos salen del leaderboard (no de un set escrito a mano),
  2. `displayName` resuelve contra `/v1/pros`,
  3. se conservan las cuentas de todas las plataformas, no solo EUW.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracking.soloq.accounts_from_teams import get_pro_players  # noqa: E402

LIGAS = ["lec"]


def main() -> None:
    jugadores = get_pro_players(LIGAS)

    print(f"Jugadores con ficha: {len(jugadores)}")
    equipos = sorted({p.team for p in jugadores if p.team})
    print(f"Equipos: {len(equipos)} -> {' '.join(equipos)}")

    plataformas: Counter[str] = Counter()
    sin_plataforma = 0
    total_cuentas = 0
    for p in jugadores:
        for acc in p.accounts:
            total_cuentas += 1
            plat = (acc.platform or "").upper()
            if plat:
                plataformas[plat] += 1
            else:
                sin_plataforma += 1

    print(f"Cuentas: {total_cuentas} · sin plataforma: {sin_plataforma}")
    print(f"Plataformas: {dict(plataformas.most_common())}")

    con_cuentas = sum(1 for p in jugadores if p.accounts)
    print(f"Jugadores con al menos una cuenta: {con_cuentas}/{len(jugadores)}")

    # Los tres equipos fantasma y el nuevo.
    for nombre in ("BDS", "KOI", "LR", "SHFT"):
        print(f"  {nombre}: {'presente' if nombre in equipos else 'AUSENTE'}")


if __name__ == "__main__":
    main()

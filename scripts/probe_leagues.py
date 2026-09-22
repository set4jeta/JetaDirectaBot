"""¿Qué códigos de liga acepta dpm.lol de verdad?

El bot solo sigue la LEC porque `TRACKED_TEAMS` es un set fijo de 12 equipos.
Para abrirlo a otras ligas hace falta saber dos cosas:

1. Qué códigos son válidos en `/v1/esport/soloq/leagues/<codigo>/leaderboard`.
   Ojo: un código inventado **no da 404**, devuelve el leaderboard genérico de
   1683 jugadores. Hay que comparar tamaños para distinguirlos.
2. Qué equipos trae cada uno, que es el dato que necesitamos para construir el
   registro de ligas.

Ejecutar:
    python scripts/probe_leagues.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: F401
from apis.dpm_api import _get_json

CANDIDATOS = [
    #-tier 1
    "lec", "lck", "lpl", "lta", "ltan", "ltas", "lcs", "lcp",
    # Américas
    "lla", "nacl", "lrs", "cbloo", "north", "south",
    # EMEA
    "lfl", "nlc", "tcl", "el", "hll", "prm", "ul", "pgn",
    # Asia-Pacífico
    "ljl", "lco", "pcs", "vcs", "lpl", "ldl",
    # Torneos
    "msi", "worlds", "ewc",
]

TAMANO_COMODIN = 1683


async def main() -> None:
    print(f"{'codigo':10s} {'jug.':>6s}  equipos")
    print("-" * 78)
    resultados = {}
    for codigo in CANDIDATOS:
        try:
            data = await _get_json(f"/esport/soloq/leagues/{codigo}/leaderboard")
        except Exception as exc:
            print(f"{codigo:10s}  ERROR {type(exc).__name__}: {str(exc)[:50]}")
            continue
        if not isinstance(data, list):
            print(f"{codigo:10s}  no es lista: {type(data).__name__}")
            continue
        if len(data) == TAMANO_COMODIN:
            print(f"{codigo:10s} {len(data):6d}  <- COMODIN (no existe)")
            continue
        equipos = sorted({
            (p.get("team") or "").strip()
            for p in data if isinstance(p, dict) and (p.get("team") or "").strip()
        })
        resultados[codigo] = equipos
        muestra = ", ".join(equipos[:10])
        if len(equipos) > 10:
            muestra += f", ... (+{len(equipos) - 10})"
        print(f"{codigo:10s} {len(data):6d}  {len(equipos):3d} equipos: {muestra}")

    salida = Path(__file__).resolve().parent.parent / "tracking" / "soloq" / "leagues_probe.json"
    with salida.open("w", encoding="utf-8") as fh:
        json.dump(resultados, fh, ensure_ascii=False, indent=2)
    print(f"\nGuardado: {salida.name} ({len(resultados)} ligas válidas)")


asyncio.run(main())

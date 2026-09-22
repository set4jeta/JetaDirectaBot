"""¿Hasta dónde llega el calendario, y qué ligas/equipos existen de verdad?

Tres cosas que el sondeo anterior dejó abiertas y que deciden el diseño:

1. **Paginación.** `getSchedule` devolvió una ventana de -3,3 d a +3,7 d y un
   `pages.newer`. Si se puede paginar hacia delante, la antelación del aviso no
   está limitada a 4 días; si no, sí lo está y hay que decirlo.
2. **`getLeagues`.** El catálogo de `tracking/soloq/leagues.py` es de dpm.lol y
   solo tiene las 20 ligas cuya SoloQ se puede rastrear. Los partidos oficiales
   no dependen de eso: salen del calendario. Así que la lista de ligas
   suscribibles a partidos puede ser mayor, y hace falta la oficial.
3. **`getTeams`.** Para saber si un tricode identifica a un equipo sin ambiguedad
   en todo el circuito, no solo en la ventana de 7 días.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

BASE = "https://esports-api.lolesports.com/persisted/gw"
HEADERS = {
    "x-api-key": config.LOL_API_KEY,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


async def pedir(sesion, ruta: str, **params) -> dict:
    query = "&".join(f"{k}={v}" for k, v in {"hl": "en-US", **params}.items())
    async with sesion.get(f"{BASE}/{ruta}?{query}", headers=HEADERS) as r:
        if r.status != 200:
            print(f"  !! HTTP {r.status} en {ruta} {params}")
            return {}
        return await r.json()


async def main() -> None:
    ahora = datetime.now(timezone.utc)
    async with aiohttp.ClientSession() as sesion:
        # ---------------- 1 · paginación hacia delante ----------------- #
        print("=== paginación de getSchedule ===")
        token = None
        vistos: set[str] = set()
        limite_max = ahora
        for vuelta in range(6):
            datos = await pedir(sesion, "getSchedule", **({"pageToken": token} if token else {}))
            bloque = datos.get("data", {}).get("schedule", {}) or {}
            eventos = bloque.get("events", []) or []
            if not eventos:
                print(f"  vuelta {vuelta}: sin eventos, fin")
                break
            tiempos = [
                datetime.fromisoformat(e["startTime"].replace("Z", "+00:00"))
                for e in eventos
                if isinstance(e, dict) and e.get("startTime")
            ]
            nuevos = {
                (e.get("match") or {}).get("id")
                for e in eventos
                if isinstance(e, dict) and (e.get("match") or {}).get("id")
            }
            repes = len(nuevos & vistos)
            vistos |= nuevos
            limite_max = max(limite_max, max(tiempos))
            print(f"  vuelta {vuelta}: {len(eventos):3d} ev  "
                  f"{min(tiempos).date()} .. {max(tiempos).date()}  "
                  f"(+{(max(tiempos) - ahora).days} d)  repetidos={repes}  "
                  f"acumulados={len(vistos)}")
            token = (bloque.get("pages") or {}).get("newer")
            if not token:
                print("  no hay pages.newer: fin de la paginación")
                break
        print(f"  -> antelación máxima alcanzable: "
              f"{(limite_max - ahora).total_seconds() / 86400:.1f} días")

        # ---------------- 2 · getLeagues ------------------------------- #
        print("\n=== getLeagues ===")
        datos = await pedir(sesion, "getLeagues")
        ligas = (datos.get("data", {}).get("leagues") or [])
        print(f"  {len(ligas)} ligas")
        prioridad = Counter()
        for lg in ligas:
            prioridad[lg.get("region") or "?"] += 1
        for lg in sorted(ligas, key=lambda x: (x.get("priority") or 999)):
            print(f"  prio {str(lg.get('priority')):>4}  {lg.get('slug'):32s} "
                  f"{(lg.get('name') or ''):28s} {lg.get('region')}  id={lg.get('id')}")

        # ---------------- 3 · getTeams --------------------------------- #
        print("\n=== getTeams ===")
        datos = await pedir(sesion, "getTeams")
        equipos = [e for e in (datos.get("data", {}).get("teams") or []) if isinstance(e, dict)]
        print(f"  {len(equipos)} equipos")
        por_code: dict[str, list[str]] = defaultdict(list)
        con_liga = 0
        for e in equipos:
            code = (e.get("code") or "").strip().upper()
            if not code or code == "TBD":
                continue
            ligas_eq = [
                (h.get("slug") or "") for h in (e.get("homeLeague") or {},) if h
            ]
            if e.get("homeLeague"):
                con_liga += 1
            por_code[code].append(f"{e.get('name')}|{'/'.join(filter(None, ligas_eq))}")
        dup = {c: v for c, v in por_code.items() if len(v) > 1}
        print(f"  tricodes distintos: {len(por_code)}   con homeLeague: {con_liga}")
        print(f"  tricodes duplicados: {len(dup)}")
        for c, v in sorted(dup.items())[:25]:
            print(f"    {c:6s} {v}")


if __name__ == "__main__":
    asyncio.run(main())

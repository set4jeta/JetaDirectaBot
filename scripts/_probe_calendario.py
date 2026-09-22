"""Qué trae de verdad `getSchedule`, medido antes de escribir el productor.

Preguntas que hay que contestar con datos, no de memoria:

1. **Cuánto futuro cubre.** Decide cuánta antelación se puede prometer en un
   aviso de "próximo partido". Si el feed solo llega a 3 días, un aviso "24 h
   antes" es posible y uno "una semana antes" no.
2. **Qué `league.slug` aparecen y cuáles resuelven** a una liga del catálogo de
   `tracking/soloq/leagues.py`. El almacén guarda códigos de dpm.lol (`les`) y
   el feed da slugs de lolesports (`superliga`): si no resuelven, la
   suscripción existiría y no dispararía nunca.
3. **Qué `team.code` (tricodes) hay**, y si son únicos entre ligas. Es lo que
   `/seguir t1` tendría que guardar y comparar.
4. **Si `state`/`startTime` sirven para decidir "va a empezar"**, y qué eventos
   no son partidos (shows, TBD).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from esports_extension.services.api import APIClient  # noqa: E402
from tracking.soloq.leagues import LIGAS, resolver  # noqa: E402


async def main() -> None:
    api = APIClient()
    datos = await api.get_schedule()

    bloque = datos.get("data", {}).get("schedule", {}) or {}
    eventos = bloque.get("events", []) or []
    paginas = bloque.get("pages", {}) or {}

    ahora = datetime.now(timezone.utc)
    print(f"eventos: {len(eventos)}   pages: {paginas}")
    print(f"ahora (UTC): {ahora.isoformat()}")

    tipos = Counter()
    estados = Counter()
    por_slug: dict[str, list[float]] = defaultdict(list)
    tricodes: dict[str, set[str]] = defaultdict(set)
    horas: list[float] = []
    sin_resolver: set[str] = set()
    nombres_slug: dict[str, str] = {}
    futuros_sin_equipo = 0

    for ev in eventos:
        if not isinstance(ev, dict):
            continue
        tipos[ev.get("type") or "?"] += 1
        estados[ev.get("state") or "?"] += 1

        slug = ((ev.get("league") or {}).get("slug") or "").strip()
        nombre = ((ev.get("league") or {}).get("name") or "").strip()
        if slug:
            nombres_slug[slug] = nombre

        crudo = ev.get("startTime")
        if not crudo:
            continue
        inicio = datetime.fromisoformat(crudo.replace("Z", "+00:00"))
        delta_h = (inicio - ahora).total_seconds() / 3600
        horas.append(delta_h)
        if slug:
            por_slug[slug].append(delta_h)

        equipos = ((ev.get("match") or {}).get("teams") or [])
        codigos = [
            (t.get("code") or "").strip()
            for t in equipos
            if isinstance(t, dict) and (t.get("code") or "").strip()
        ]
        nombres_eq = [(t.get("name") or "") for t in equipos if isinstance(t, dict)]
        if slug:
            tricodes[slug].update(c for c in codigos if c.upper() != "TBD")
        if delta_h > 0 and (not codigos or "TBD" in {n.upper() for n in nombres_eq}):
            futuros_sin_equipo += 1

    print(f"\ntipos: {dict(tipos)}")
    print(f"estados: {dict(estados)}")
    if horas:
        print(f"ventana: {min(horas):+.1f} h .. {max(horas):+.1f} h "
              f"({min(horas)/24:+.1f} d .. {max(horas)/24:+.1f} d)")
    print(f"eventos futuros con equipo TBD: {futuros_sin_equipo}")

    print("\n--- slugs y resolución al catálogo de dpm ---")
    for slug in sorted(por_slug, key=lambda s: -len(por_slug[s])):
        liga = resolver(slug)
        marca = f"-> {liga.codigo}" if liga else "-> SIN RESOLVER"
        if liga is None:
            sin_resolver.add(slug)
        futuros = [h for h in por_slug[slug] if h > 0]
        print(f"  {slug:34s} {len(por_slug[slug]):3d} ev "
              f"({len(futuros):3d} futuros)  {marca}   [{nombres_slug.get(slug, '')}]")

    print(f"\nslugs sin resolver ({len(sin_resolver)}): {sorted(sin_resolver)}")
    print(f"ligas del catálogo que NO aparecen en el feed: "
          f"{sorted(set(LIGAS) - {resolver(s).codigo for s in por_slug if resolver(s)})}")

    print("\n--- tricodes por liga (los que resuelven) ---")
    vistos: dict[str, list[str]] = defaultdict(list)
    for slug, codigos in sorted(tricodes.items()):
        liga = resolver(slug)
        if liga is None:
            continue
        print(f"  {liga.codigo:6s} {slug:28s} {sorted(codigos)}")
        for c in codigos:
            vistos[c.upper()].append(slug)

    choques = {c: s for c, s in vistos.items() if len(set(s)) > 1}
    print(f"\ntricodes repetidos en varias ligas ({len(choques)}): "
          f"{json.dumps(choques, ensure_ascii=False)[:900]}")


if __name__ == "__main__":
    asyncio.run(main())

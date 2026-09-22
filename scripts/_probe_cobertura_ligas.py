"""Mide qué cobertura real tendría añadir ligas desde el API oficial de esports.

Para qué
--------
El usuario pidió LLA y NACL. dpm.lol **no tiene leaderboard de esas ligas**
(devuelven el comodín de 1684 jugadores), pero el API público de
`esports-api.lolesports.com` sí tiene sus plantillas: 47 ligas, con nombre de
jugador y equipo.

El problema es que la plantilla no da cuentas de SoloQ. Quien mapea
"nombre de pro" -> "cuentas de SoloQ + PUUID" es `dpm.lol/v1/pros/<nombre>`. Así
que la pregunta que decide si la función se puede prometer es:

    ¿qué porcentaje de los jugadores de una liga que dpm.lol no tiene como
    liga son, aun así, resolubles como jugadores en dpm.lol?

Si es alto, se puede seguir la liga. Si es bajo, hay que decirlo en vez de
añadir una liga que no avisa de nada.

Este script solo mide y escribe el resultado en JSON. No toca el bot.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cloudscraper  # noqa: E402
import urllib.request  # noqa: E402

#: Clave pública del cliente web de lolesports.com. Va en el JS de la propia
#: página, no es un secreto y no identifica a nadie.
CLAVE_ESPORTS = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"

SALIDA = os.path.join(os.path.dirname(__file__), "_cobertura_ligas.json")

#: Ligas a medir. Las dos que el usuario nombró, más las candidatas grandes que
#: dpm.lol tampoco tiene como leaderboard.
OBJETIVO = [
    "LLA", "NACL", "LTA North", "LTA South", "LJL", "PCS", "VCS", "LCO",
    "Arabian League", "LCK Challengers", "Circuito Desafiante",
]


def esports(path: str):
    url = f"https://esports-api.lolesports.com/persisted/gw/{path}"
    req = urllib.request.Request(
        url, headers={"x-api-key": CLAVE_ESPORTS, "User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


_scraper = cloudscraper.create_scraper(browser={"custom": "Chrome"}, delay=10)


def resolver_en_dpm(nombre: str) -> dict:
    """Una sola petición, sin reintentos: aquí interesa la tasa, no el dato.

    Con 3 reintentos y 2 s de espera, medir 400 nombres serían 40 minutos casi
    todos gastados en confirmar 404 que ya sabemos.
    """
    try:
        r = _scraper.get(f"https://dpm.lol/v1/pros/{quote(nombre)}", timeout=20)
        if r.status_code == 404:
            return {"ok": False, "motivo": "404"}
        r.raise_for_status()
        d = r.json()
    except Exception as exc:
        return {"ok": False, "motivo": type(exc).__name__}

    cuentas = (d or {}).get("players") or []
    if not cuentas:
        return {"ok": False, "motivo": "sin cuentas"}

    ficha = (d or {}).get("esportPlayer") or {}
    return {
        "ok": True,
        "cuentas": len(cuentas),
        "plataformas": sorted({(c.get("platform") or "?") for c in cuentas}),
        "con_puuid": sum(1 for c in cuentas if c.get("puuid")),
        "equipo_dpm": ficha.get("team"),
    }


def main() -> None:
    equipos = esports("getTeams?hl=en-US")["data"]["teams"]

    por_liga: dict[str, list[tuple[str, str]]] = {}
    for e in equipos:
        if e.get("status") != "active":
            continue
        liga = (e.get("homeLeague") or {}).get("name")
        if liga not in OBJETIVO:
            continue
        for p in e.get("players") or []:
            nombre = (p.get("summonerName") or "").strip()
            if nombre:
                por_liga.setdefault(liga, []).append((nombre, e.get("code") or ""))

    resultado: dict[str, dict] = {}
    for liga in OBJETIVO:
        jugadores = por_liga.get(liga) or []
        if not jugadores:
            print(f"\n=== {liga}: sin plantillas activas ===")
            resultado[liga] = {"total": 0, "resueltos": 0, "detalle": []}
            continue

        print(f"\n=== {liga}: {len(jugadores)} jugadores ===")
        inicio = time.perf_counter()
        # 6 en paralelo: dpm.lol aguanta eso sin dar 429 (el bot ya usa 12 con
        # el semáforo, pero aquí no hay limitador delante).
        with ThreadPoolExecutor(max_workers=6) as pool:
            datos = list(pool.map(lambda t: resolver_en_dpm(t[0]), jugadores))

        detalle = []
        for (nombre, equipo), d in zip(jugadores, datos):
            detalle.append({"nombre": nombre, "equipo": equipo, **d})
            estado = (
                f"{d['cuentas']} cuentas {','.join(d['plataformas'])}"
                if d["ok"] else f"NO ({d['motivo']})"
            )
            print(f"  {nombre[:20]:20} {equipo:6} {estado}")

        resueltos = sum(1 for d in datos if d["ok"])
        cuentas = sum(d.get("cuentas", 0) for d in datos if d["ok"])
        pct = 100 * resueltos / len(jugadores)
        print(
            f"  --> {resueltos}/{len(jugadores)} resueltos ({pct:.0f}%), "
            f"{cuentas} cuentas, {time.perf_counter() - inicio:.0f}s"
        )
        resultado[liga] = {
            "total": len(jugadores),
            "resueltos": resueltos,
            "cuentas": cuentas,
            "pct": round(pct, 1),
            "detalle": detalle,
        }

    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2)

    print("\n" + "=" * 62)
    print(f"{'LIGA':24} {'JUG':>5} {'RESUELTOS':>10} {'%':>6} {'CUENTAS':>8}")
    for liga, r in resultado.items():
        print(
            f"{liga:24} {r['total']:>5} {r['resueltos']:>10} "
            f"{r.get('pct', 0):>6} {r.get('cuentas', 0):>8}"
        )
    print(f"\nDetalle en {SALIDA}")


if __name__ == "__main__":
    main()

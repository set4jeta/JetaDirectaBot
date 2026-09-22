"""Cuántas cuentas cuesta seguir cada liga. Desechable (por eso el `_`).

Para qué
--------
`MAX_LIGAS_POR_SERVIDOR = 4` se calculó cuando el catálogo tenía 12 ligas y se
suponían "~90 cuentas por liga". Ahora hay 20, ocho de ellas regionales
pequeñas, así que el número que se va a *vender* en `/premium` hay que
recalcularlo con datos, no con la suposición vieja.

Qué mide
--------
Una petición por liga al leaderboard de dpm.lol y, de la respuesta:

* filas del leaderboard (que son **cuentas**, no personas);
* `displayName` distintos (que son las personas);
* equipos distintos.

El coste real de una pasada del tracker no es ninguno de los dos: el bot
resuelve cada persona contra `/v1/pros/<nombre>` y se guarda **todas** sus
cuentas, incluidas las de otras regiones que no salen en el leaderboard de su
liga. Medido sobre la LEC ya poblada (`accounts_from_teams.json`): 50 personas
-> 172 cuentas, o sea 3,44 cuentas por persona. Ese es el multiplicador que se
aplica aquí para estimar el coste de las ligas que todavía no están poblada.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apis.dpm_api import fetch_league_leaderboard_sync  # noqa: E402
from tracking.soloq.leagues import LIGAS  # noqa: E402

#: Cuentas por persona, medido sobre la LEC poblada (172/50).
CUENTAS_POR_PERSONA = 3.44


def main() -> None:
    filas_totales = 0
    personas_totales = 0
    salida: dict[str, dict] = {}

    print(f"{'liga':7} {'filas':>6} {'personas':>9} {'equipos':>8}  estimado cuentas")
    print("-" * 58)

    for codigo in LIGAS:
        datos = fetch_league_leaderboard_sync(codigo)
        if not datos:
            print(f"{codigo:7} {'—':>6} {'—':>9} {'—':>8}  sin leaderboard")
            salida[codigo] = {"filas": 0, "personas": 0, "equipos": 0}
            continue

        filas = len(datos)
        personas = len({(p.get("displayName") or "").strip() for p in datos if isinstance(p, dict)})
        equipos = len({(p.get("team") or "").strip() for p in datos if isinstance(p, dict)} - {""})
        estimado = round(personas * CUENTAS_POR_PERSONA)

        filas_totales += filas
        personas_totales += personas
        salida[codigo] = {
            "filas": filas,
            "personas": personas,
            "equipos": equipos,
            "cuentas_estimadas": estimado,
        }
        print(f"{codigo:7} {filas:6} {personas:9} {equipos:8}  ~{estimado}")

    print("-" * 58)
    print(f"{'TOTAL':7} {filas_totales:6} {personas_totales:9}")
    print(f"Coste de seguir las 20: ~{round(personas_totales * CUENTAS_POR_PERSONA)} cuentas/pasada")

    peores = sorted(salida.items(), key=lambda kv: -kv[1].get("personas", 0))[:4]
    print(
        "Las 4 más caras: "
        + ", ".join(f"{c} (~{d['cuentas_estimadas']})" for c, d in peores)
        + f" = ~{sum(d['cuentas_estimadas'] for _, d in peores)} cuentas"
    )

    destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_coste_ligas.json")
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=2)
    print(f"\nEscrito {destino}")


if __name__ == "__main__":
    main()

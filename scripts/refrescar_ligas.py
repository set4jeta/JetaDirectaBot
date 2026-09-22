"""Ranking de SoloQ de las 20 ligas, medido contra el leaderboard de dpm.lol.

El problema que resuelve
-----------------------
La web se genera con datos reales, y eso dejaba 19 de las 20 páginas de liga en
"censo y poco más": solo la LEC está barrida en
`tracking/soloq/accounts_from_teams.json`, porque poblar una liga por esa vía
cuesta una petición a `/v1/pros/<nombre>` **por jugador** (50 jugadores -> 50
peticiones, y 172 cuentas guardadas). Multiplicado por 20 ligas eso son ~900
peticiones para generar HTML, que no se van a hacer.

El leaderboard de liga da casi lo mismo en **una** petición por liga: por cuenta
trae `displayName`, `team`, `lane`, `tier`, `rank`, `leaguePoints`, `wins`,
`losses`, `kda` y `mostChamps`. 20 peticiones, ~1,4 s cada una. Con eso las 19
páginas pasan de censo a ranking de verdad.

Lo que esta vía **no** da, y por eso no se pinta
------------------------------------------------
* **No hay Riot ID.** El leaderboard identifica por `puuid` y `displayName`, no
  por `nombre#tag`. La columna "Cuenta de SoloQ" —el dato que no está en ninguna
  otra web— solo existe donde la liga está barrida de verdad, así que las páginas
  que salen de aquí llevan una tabla distinta, sin esa columna.
* **No hay historial de campeones.** `mostChamps` son 4 ids de campeón sin
  partidas, sin victorias y sin DPM, y **no es** el `last_champions` de
  `/v1/pros`: comprobado sobre 73 jugadores de la LEC, el conjunto de campeones
  coincide en 0 casos. Son ventanas de agregación distintas y por cuenta, no por
  persona. Sustituir uno por otro sería inventarse el dato.

Por qué se guardan los ids de campeón y no los nombres
------------------------------------------------------
El nombre se resuelve al generar la web con `cache/champion_cache.py`. Si aquí se
guardaran los nombres, este fichero envejecería con el catálogo: hoy mismo el
caché estaba dos parches atrás y los ids 805 y 904 —que salen en `mostChamps`—
se pintaban como "ID 904". Guardando el id, refrescar el catálogo arregla también
los datos ya escritos.

Una fila del leaderboard es una cuenta, no una persona
------------------------------------------------------
La LEC devuelve 82 filas para 50 jugadores: 24 personas tienen más de una cuenta
en la lista. Se agrupa por `displayName` y se conserva la fila de más Elo, que es
el mismo criterio que `rank_utils.mejor_cuenta` aplica en el bot. El `lane` es
consistente entre las cuentas de una misma persona (0 discrepancias medidas), así
que agrupar no pierde el rol.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apis.dpm_api import fetch_league_leaderboard_sync  # noqa: E402
from tracking.soloq.leagues import LIGAS  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "tracking", "soloq", "leaderboards_ligas.json")

#: Cuentas por persona, medido sobre la LEC poblada (172 cuentas / 50 personas).
#: Mismo multiplicador que `_coste_ligas.py`, para que las dos mediciones del
#: censo den el mismo número y no haya que explicar por qué difieren.
CUENTAS_POR_PERSONA = 3.44

#: Pausa entre ligas. No la exige dpm.lol; es para no encadenar 20 peticiones
#: seguidas desde la misma IP contra un servicio que va detrás de Cloudflare.
PAUSA = 0.5

#: Por debajo de esta fracción de las personas que ya había en disco para una
#: liga, se conserva lo viejo. Misma regla que `utils/safe_json.py`: una liga que
#: pasa de 55 jugadores a 12 es un fallo de la fuente, no un mercado loco.
MIN_RATIO = 0.7

#: Cuántos campeones se guardan por jugador. El leaderboard da 4 y no más.
TOPE_CAMPEONES = 4

#: `lane` del leaderboard -> vocabulario de rol que ya usa la web
#: (`ROLES` en `scripts/web_datos.py` y el campo `role` de los ficheros de
#: equipos). Traducir aquí evita que la plantilla tenga que saber que dpm.lol
#: llama "UTILITY" al soporte.
LANES = {
    "TOP": "Top",
    "JUNGLE": "Jungle",
    "MIDDLE": "Mid",
    "BOTTOM": "Bot",
    "UTILITY": "Support",
    "SUPPORT": "Support",
}

_TIERS = ("IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD",
          "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER")
_PESO_TIER = {t: i + 1 for i, t in enumerate(_TIERS)}
_DIVISIONES = {"IV": 1, "III": 2, "II": 3, "I": 4}


def valor(fila: dict) -> int:
    """Entero comparable del Elo de una fila. 0 si el tier no se reconoce.

    Mismo cálculo que `web_datos.valor_rango`, con los nombres de campo del
    leaderboard (`leaguePoints` en vez de `lp`). Se repite en vez de importarse
    porque `web_datos` es el módulo del generador y este script corre en el
    intérprete del bot; acoplarlos obligaría a que los dos vivieran en el mismo.
    """
    peso = _PESO_TIER.get(str(fila.get("tier") or "").strip().upper(), 0)
    if not peso:
        return 0
    division = _DIVISIONES.get(str(fila.get("rank") or "").strip().upper(), 0)
    try:
        lp = int(fila.get("leaguePoints") or 0)
    except (TypeError, ValueError):
        lp = 0
    return peso * 1_000_000 + division * 10_000 + lp


def agrupar(filas: list[dict]) -> list[dict]:
    """Filas del leaderboard -> una entrada por persona, la de más Elo.

    Devuelve la lista ya ordenada por Elo descendente, que es el orden en el que
    se va a pintar. Ordenarla aquí y no al generar evita que dos consumidores
    ordenen distinto el mismo fichero.
    """
    mejores: dict[str, dict] = {}
    cuentas: dict[str, int] = {}

    for fila in filas:
        if not isinstance(fila, dict):
            continue
        nombre = str(fila.get("displayName") or "").strip()
        if not nombre:
            continue

        cuentas[nombre] = cuentas.get(nombre, 0) + 1
        previa = mejores.get(nombre)
        if previa is not None and valor(fila) <= valor(previa):
            continue
        mejores[nombre] = fila

    salida = []
    for nombre, fila in mejores.items():
        try:
            victorias = int(fila.get("wins") or 0)
            derrotas = int(fila.get("losses") or 0)
        except (TypeError, ValueError):
            victorias = derrotas = 0
        try:
            kda = round(float(fila.get("kda") or 0.0), 2)
        except (TypeError, ValueError):
            kda = 0.0

        campeones = [
            str(cid) for cid in (fila.get("mostChamps") or [])[:TOPE_CAMPEONES]
            if isinstance(cid, (int, str)) and str(cid).strip()
        ]

        salida.append({
            "nombre": nombre,
            "equipo": str(fila.get("team") or "").strip().upper(),
            "rol": LANES.get(str(fila.get("lane") or "").strip().upper(), ""),
            "tier": str(fila.get("tier") or "").strip().upper(),
            "division": str(fila.get("rank") or "").strip().upper(),
            "lp": int(fila.get("leaguePoints") or 0),
            "victorias": victorias,
            "derrotas": derrotas,
            "kda": kda,
            "campeones": campeones,
            "cuentas": cuentas[nombre],
        })

    salida.sort(key=lambda j: (-valor({
        "tier": j["tier"], "rank": j["division"], "leaguePoints": j["lp"],
    }), j["nombre"].lower()))
    return salida


def _leer_previo() -> dict:
    """Lo que ya hay en disco. Un fichero roto cuenta como vacío.

    Se lee antes de pedir nada porque es la referencia contra la que se decide si
    una liga que viene peor de la fuente se escribe o se conserva.
    """
    if not os.path.exists(DESTINO):
        return {}
    try:
        with open(DESTINO, "r", encoding="utf-8") as fh:
            previo = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  aviso: {DESTINO} no se pudo leer ({exc}); se trata como vacío.")
        return {}
    return previo if isinstance(previo, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresca el ranking de SoloQ de las ligas desde dpm.lol."
    )
    parser.add_argument(
        "--ligas", default="",
        help="Códigos separados por comas. Por defecto, las 20 del catálogo.",
    )
    parser.add_argument(
        "--pausa", type=float, default=PAUSA,
        help=f"Segundos entre peticiones (por defecto {PAUSA}).",
    )
    args = parser.parse_args()

    codigos = [c.strip().lower() for c in args.ligas.split(",") if c.strip()] or list(LIGAS)
    desconocidas = [c for c in codigos if c not in LIGAS]
    if desconocidas:
        print(f"Ligas que no están en el catálogo: {', '.join(desconocidas)}")
        return 2

    previo = _leer_previo()
    anterior_ligas = previo.get("ligas") if isinstance(previo.get("ligas"), dict) else {}

    ligas: dict[str, dict] = dict(anterior_ligas)
    fallos: list[str] = []
    conservadas: list[str] = []
    inicio = time.monotonic()

    print(f"{'liga':7} {'filas':>6} {'personas':>9} {'equipos':>8} {'segundos':>9}")
    print("-" * 46)

    for i, codigo in enumerate(codigos):
        t0 = time.monotonic()
        filas = fetch_league_leaderboard_sync(codigo)
        tardanza = time.monotonic() - t0

        if not filas:
            # Vacío es el fallo silencioso típico de dpm.lol (403, Cloudflare, o
            # que ya no reconozca el código). Lo que había se queda.
            fallos.append(codigo)
            print(f"{codigo:7} {'—':>6} {'—':>9} {'—':>8} {tardanza:9.1f}  sin leaderboard")
            continue

        jugadores = agrupar(filas)
        antes = len((anterior_ligas.get(codigo) or {}).get("jugadores") or [])
        if antes and len(jugadores) < antes * MIN_RATIO:
            conservadas.append(codigo)
            print(
                f"{codigo:7} {len(filas):6} {len(jugadores):9} {'—':>8} {tardanza:9.1f}"
                f"  encogimiento ({antes} antes): se conserva lo viejo"
            )
            continue

        equipos = sorted({j["equipo"] for j in jugadores if j["equipo"]})
        ligas[codigo] = {
            "jugadores": jugadores,
            "equipos": equipos,
            "filas": len(filas),
            "cuentas_estimadas": round(len(jugadores) * CUENTAS_POR_PERSONA),
        }
        print(
            f"{codigo:7} {len(filas):6} {len(jugadores):9} {len(equipos):8} "
            f"{tardanza:9.1f}"
        )

        if args.pausa and i < len(codigos) - 1:
            time.sleep(args.pausa)

    if not ligas:
        print("\nNo se obtuvo ninguna liga y no había nada previo. No se escribe.")
        return 1

    personas = sum(len(d.get("jugadores") or []) for d in ligas.values())
    print("-" * 46)
    print(
        f"{len(ligas)} ligas, {personas} jugadores, "
        f"{time.monotonic() - inicio:.1f} s en total"
    )
    if fallos:
        print(f"Sin leaderboard: {', '.join(fallos)}")
    if conservadas:
        print(f"Se conservó lo anterior en: {', '.join(conservadas)}")

    documento = {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fuente": "dpm.lol /v1/esport/soloq/leagues/<liga>/leaderboard",
        "ligas": ligas,
    }

    # Atómico: `.tmp` y `os.replace`. El generador de la web puede estar leyendo
    # este fichero mientras esto corre, y media escritura no es un dato malo, es
    # un JSON que no parsea.
    tmp = DESTINO + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(documento, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, DESTINO)
    except OSError as exc:
        print(f"Fallo escribiendo {DESTINO}: {exc}")
        if os.path.exists(tmp):
            os.remove(tmp)
        return 1

    print(f"\nEscrito {DESTINO} ({os.path.getsize(DESTINO):,} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

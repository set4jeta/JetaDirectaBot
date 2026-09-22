"""Refresca `cache/champion_data_raw.json` desde Data Dragon.

Por qué hacía falta un script y no valía editarlo a mano
-------------------------------------------------------
El fichero estaba en la versión **15.14.1** (171 campeones) con fecha de julio,
y Riot va por **16.17.1** (173). Los dos que faltaban no son casos raros: son
`805` (Locke) y `904` (Zaahen), y los dos aparecen en el `mostChamps` que
devuelve el leaderboard de dpm.lol *hoy*. Medido antes de arreglarlo, en la LCK:
de 65 campeones distintos que salían en el leaderboard, 2 no se podían nombrar.

Eso no rompía nada visible, y ahí está el problema. `CHAMPION_ID_TO_NAME` lo
usan seis sitios (`ui/active_match_embed.py`, `models/soloq_match.py`,
`core/live_command.py`, `core/rank_data.py`, `utils/champion_names.py`,
`utils/lane_guess.py`) y todos hacen `.get(id, f"ID {id}")` o `"?"`: un aviso de
partida de alguien jugando Zaahen decía **"ID 904"** en el embed en vez del
nombre. Con el catálogo al día, ese caso desaparece; sin script, vuelve con cada
campeón nuevo.

Qué comprueba antes de escribir
-------------------------------
Data Dragon es un CDN estático y responde siempre, así que el riesgo no es que
falle: es que devuelva algo que *parece* válido y encoja el catálogo. Por eso se
rechaza la escritura si vienen menos campeones de los que ya hay, con la misma
lógica que `utils/safe_json.py` aplica a los rosters. La escritura es atómica
(`.tmp` + `os.replace`) porque este fichero se lee al importar
`cache/champion_cache.py`, es decir, en el arranque del bot: un fichero
truncado a mitad de volcado no da un dato malo, impide arrancar.

No usa `requests` ni `cloudscraper` a propósito: Data Dragon no está detrás de
Cloudflare (lo mismo que ya asume `apis/dpm_api.obtener_parche_actual`), así que
con `urllib` de la biblioteca estándar basta y el script corre con cualquier
intérprete, no solo con el que tiene las dependencias del bot.

    python scripts/refrescar_campeones.py            # refresca si hay novedad
    python scripts/refrescar_campeones.py --ver      # solo informa, no escribe
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "cache", "champion_data_raw.json")

VERSIONES = "https://ddragon.leagueoflegends.com/api/versions.json"
CATALOGO = "https://ddragon.leagueoflegends.com/cdn/{version}/data/{idioma}/champion.json"

#: Inglés, y no español, porque es el idioma en el que Riot da los nombres
#: internos que el resto del bot compara ("MonkeyKing", "LeeSin"). Traducir el
#: catálogo rompería `utils/champion_names.py`, que casa el nombre de display
#: con el interno normalizando la puntuación.
IDIOMA = "en_US"

TIMEOUT = 25


def _pedir_bytes(url: str) -> bytes:
    """GET crudo. Data Dragon no necesita cabeceras ni scraper."""
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        return resp.read()


def _pedir(url: str):
    """GET de JSON."""
    return json.loads(_pedir_bytes(url))


def ultima_version() -> str:
    versiones = _pedir(VERSIONES)
    if not isinstance(versiones, list) or not versiones:
        raise SystemExit("Data Dragon no devolvió la lista de versiones.")
    return str(versiones[0])


def _nombres(catalogo: dict) -> dict[str, str]:
    """`{id numérico: nombre de display}` de un catálogo de Data Dragon."""
    datos = catalogo.get("data") if isinstance(catalogo, dict) else None
    if not isinstance(datos, dict):
        return {}
    return {
        str(champ["key"]): str(champ["name"])
        for champ in datos.values()
        if isinstance(champ, dict) and champ.get("key") and champ.get("name")
    }


def _en_disco() -> tuple[str, dict[str, str]]:
    try:
        with open(DESTINO, encoding="utf-8") as fh:
            actual = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return "", {}
    return str(actual.get("version") or ""), _nombres(actual)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ver", action="store_true",
        help="Solo informa de la diferencia; no escribe nada.",
    )
    parser.add_argument(
        "--version", default="", metavar="X.Y.Z",
        help="Versión concreta de Data Dragon. Por defecto, la última.",
    )
    args = parser.parse_args(argv)

    version_vieja, viejos = _en_disco()
    version = args.version or ultima_version()
    crudo = _pedir_bytes(CATALOGO.format(version=version, idioma=IDIOMA))
    catalogo = json.loads(crudo)
    nuevos = _nombres(catalogo)

    if not nuevos:
        raise SystemExit(f"El catálogo de {version} vino sin campeones. No se toca nada.")

    anadidos = {k: v for k, v in nuevos.items() if k not in viejos}
    quitados = {k: v for k, v in viejos.items() if k not in nuevos}
    renombrados = {k: (viejos[k], nuevos[k]) for k in viejos if k in nuevos and viejos[k] != nuevos[k]}

    print(f"En disco: {version_vieja or '(nada)'} · {len(viejos)} campeones")
    print(f"Remoto:   {version} · {len(nuevos)} campeones")
    for etiqueta, mapa in (("Nuevos", anadidos), ("Desaparecidos", quitados)):
        if mapa:
            print(f"  {etiqueta}: " + ", ".join(f"{v} ({k})" for k, v in sorted(mapa.items())))
    for id_, (antes, ahora) in sorted(renombrados.items()):
        print(f"  Renombrado {id_}: {antes} -> {ahora}")

    if version == version_vieja and not anadidos and not quitados and not renombrados:
        print("Ya estaba al día. No se escribe.")
        return 0

    # Un catálogo que encoge es un catálogo malo: Riot no retira campeones. Es la
    # misma regla que `utils/safe_json.py` aplica a los rosters, y por el mismo
    # motivo: sobrescribir con menos datos destruye información a cambio de nada.
    if len(nuevos) < len(viejos):
        raise SystemExit(
            f"El catálogo remoto tiene {len(nuevos)} campeones y el local "
            f"{len(viejos)}. Riot no retira campeones: esto es un error de la "
            "fuente. No se sobrescribe."
        )

    if args.ver:
        print("(--ver: no se escribe nada)")
        return 0

    tmp = DESTINO + ".tmp"
    # Se escriben los bytes tal como vinieron y no un `json.dump` reindentado:
    # el fichero se llama `_raw` porque es la respuesta literal del CDN, y
    # reformatearlo lo engorda un 55 % (157 kB -> 246 kB medido) sin que nadie
    # lo lea a mano. La escritura es atómica porque `cache/champion_cache.py`
    # abre este fichero al importarse, o sea en el arranque del bot: un volcado
    # truncado no da un dato malo, impide arrancar.
    with open(tmp, "wb") as fh:
        fh.write(crudo)
    os.replace(tmp, DESTINO)

    print(f"\nEscrito {DESTINO} en la versión {version} ({len(nuevos)} campeones).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

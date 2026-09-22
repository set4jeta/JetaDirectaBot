"""Próximos partidos profesionales, medidos contra el calendario de lolesports.

El problema que resuelve
-----------------------
La web se genera con datos reales y hasta ahora todos eran de SoloQ: rangos,
cuentas y campeones. Eso deja fuera la mitad de la pregunta que trae a alguien
a una página de liga, que es **cuándo juega su equipo**. Y es la mitad que se
busca todos los días, no una vez al mes.

`tracked_matches.json` ya tenía partidos, pero es el estado interno del tracker
de esports: 13 registros cuyo `last_checked` más reciente es de julio de 2025,
porque solo se rellena mientras el bot corre y sigue una partida. Para publicar
un calendario hay que preguntarle al calendario, no al tracker.

De dónde sale
-------------
`https://esports-api.lolesports.com/persisted/gw/getSchedule`, la misma API que
usa `esports_extension/services/api.py` y con la misma clave pública. Una
petición devuelve 80 eventos alrededor de hoy y `pages.newer` pagina hacia
delante; con dos páginas se llega a 159 eventos y a cinco semanas de calendario.
Medido el 2026-09-03: 116 futuros, de los cuales **89 son de las 20 ligas del
catálogo** y 27 de ligas que el bot no sigue.

Por qué se filtra por nuestras ligas
------------------------------------
Publicar los 116 sería publicar el calendario de Riot, que ya existe y está
mejor. Los 89 que quedan son los que tienen una página de liga detrás a la que
enlazar y jugadores cuyo Elo de SoloQ sí publicamos: eso es lo que no está en
ningún otro sitio junto.

El slug de lolesports **no** es el código de dpm
------------------------------------------------
`cblol-brazil`, `turkiye-sampiyonluk-ligi` y `hellenic_legends_league` no
resolvían con `leagues.resolver()`; se han añadido a `ALIAS` en vez de mapearse
aquí, porque el mismo desajuste afecta a `/seguir` y a cualquier otra cosa que
reciba un slug oficial. Los que siguen sin resolver son ligas reales que el bot
no sigue (`nacl`, `pcs`, `vcs`, `lla`, `lck_challengers_league`, `ljl-japan`,
`liga_portuguesa`, `fls`, las dos regionales de Latinoamérica): no son un fallo,
son el filtro funcionando.

Qué se guarda y qué no
----------------------
Se guarda lo que se pinta: hora de inicio en UTC, liga, fase (`blockName`), el
Bo, y por equipo el nombre, el tricode, el logo y el récord de la temporada.

No se guarda `flags`, ni los vods, ni el `id` de los juegos individuales. Y
sobre todo **no se reescribe la URL del logo**: `static.lolesports.com` sirve
las imágenes por `http` en la respuesta de la API pero responde a `https`
(verificado: 200, `image/png`), así que se normaliza el esquema y se deja el
resto tal cual. Un logo servido por `http` desde una página `https` es contenido
mixto y el navegador lo bloquea.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracking.soloq.leagues import LIGAS, resolver  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "tracking", "esports", "proximos.json")

#: La clave pública del portal de esports. Es la misma que trae `config.py` y
#: la misma que aparece en cualquier cliente de lolesports: no es un secreto,
#: es una constante del servicio. Se deja aquí para que este script pueda correr
#: sin las dependencias del bot (`config` importa `python-dotenv`), igual que
#: `web_datos.ajuste()` evita importar `config` por lo mismo.
CLAVE = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"

BASE = "https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US"

#: Cloudflare rechaza el User-Agent por defecto de urllib con 403, igual que
#: rechaza el de aiohttp (está documentado en `esports_extension/services/api.py`).
CABECERAS = {
    "x-api-key": CLAVE,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

#: Cuántas páginas hacia delante se piden. Con 2 se cubren ~5 semanas, que es
#: más de lo que nadie mira en una página de liga.
PAGINAS = 2

#: Estados que se publican. `inProgress` va incluido porque un partido que está
#: ocurriendo ahora es justo el que hay que enseñar arriba.
PUBLICABLES = ("unstarted", "inProgress")


def _pedir(url: str, tiempo: int = 30) -> dict:
    peticion = urllib.request.Request(url, headers=CABECERAS)
    with urllib.request.urlopen(peticion, timeout=tiempo) as respuesta:
        return json.load(respuesta)


def _https(url: str) -> str:
    """`http://static.lolesports.com/...` -> `https://...`.

    La API devuelve los logos por `http`. Insertados en una página `https` son
    contenido mixto y el navegador los bloquea sin decir nada visible: el hueco
    del logo sale vacío y parece que falta la imagen.
    """
    limpio = (url or "").strip()
    if limpio.startswith("http://"):
        return "https://" + limpio[len("http://"):]
    return limpio


def _equipo(bruto: dict) -> dict:
    registro = bruto.get("record") or {}
    return {
        "nombre": bruto.get("name") or "",
        "codigo": (bruto.get("code") or "").upper(),
        "logo": _https(bruto.get("image") or ""),
        "victorias": registro.get("wins"),
        "derrotas": registro.get("losses"),
    }


def normalizar(evento: dict) -> dict | None:
    """Un evento del calendario -> el registro que se publica, o `None`.

    Devuelve `None` en cuatro casos, y ninguno es un error: el evento no es un
    partido (hay `show`), ya ha terminado, su liga no está en el catálogo, o no
    trae los dos equipos. El último pasa de verdad: un partido de playoffs
    anunciado antes de conocerse los clasificados sale con equipos sin nombre.
    """
    if evento.get("type") != "match":
        return None
    if evento.get("state") not in PUBLICABLES:
        return None

    slug = ((evento.get("league") or {}).get("slug") or "").strip()
    liga = resolver(slug)
    if liga is None:
        return None

    partido = evento.get("match") or {}
    equipos = [_equipo(t) for t in (partido.get("teams") or [])]
    if len(equipos) != 2 or not all(eq["codigo"] for eq in equipos):
        return None

    estrategia = partido.get("strategy") or {}
    return {
        "inicio": evento.get("startTime") or "",
        "liga": liga.codigo,
        "liga_nombre": (evento.get("league") or {}).get("name") or liga.nombre,
        "fase": evento.get("blockName") or "",
        "estado": evento.get("state"),
        "bo": estrategia.get("count") if estrategia.get("type") == "bestOf" else None,
        "partido_id": partido.get("id") or "",
        "equipos": equipos,
    }


def descargar(paginas: int = PAGINAS) -> tuple[list[dict], list[str]]:
    """Los eventos del calendario y los avisos de lo que no se pudo leer.

    Nunca lanza: si la primera página falla se devuelve lista vacía y el
    llamante decide. Igual que `refrescar_ligas.py`, este script no puede tirar
    la generación de la web por un 403 de Cloudflare.
    """
    eventos: list[dict] = []
    avisos: list[str] = []
    url = BASE

    for numero in range(paginas):
        try:
            documento = _pedir(url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            avisos.append(f"página {numero + 1}: {exc}")
            break

        calendario = (documento.get("data") or {}).get("schedule") or {}
        eventos.extend(calendario.get("events") or [])

        testigo = (calendario.get("pages") or {}).get("newer")
        if not testigo:
            break
        url = f"{BASE}&pageToken={testigo}"

    return eventos, avisos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresca los próximos partidos desde el calendario de lolesports."
    )
    parser.add_argument(
        "--paginas", type=int, default=PAGINAS,
        help=f"Páginas del calendario hacia delante (por defecto {PAGINAS}).",
    )
    parser.add_argument(
        "--destino", default=DESTINO,
        help="Fichero de salida (por defecto tracking/esports/proximos.json).",
    )
    args = parser.parse_args(argv)

    eventos, avisos = descargar(args.paginas)
    for aviso in avisos:
        print(f"  aviso: {aviso}")
    if not eventos:
        print("No se obtuvo ningún evento del calendario. No se escribe nada.")
        return 1

    partidos = [p for p in (normalizar(e) for e in eventos) if p]
    partidos.sort(key=lambda p: p["inicio"])

    por_liga: dict[str, int] = {}
    for partido in partidos:
        por_liga[partido["liga"]] = por_liga.get(partido["liga"], 0) + 1

    descartados = len(eventos) - len(partidos)
    print(f"{len(eventos)} eventos leídos · {len(partidos)} publicables · "
          f"{descartados} descartados (terminados, ligas ajenas o sin equipos)")
    print(f"{len(por_liga)} de las {len(LIGAS)} ligas tienen partido:")
    for codigo, cuantos in sorted(por_liga.items(), key=lambda par: -par[1]):
        print(f"  {codigo:7} {cuantos:3}")
    if partidos:
        print(f"rango: {partidos[0]['inicio']} -> {partidos[-1]['inicio']}")

    documento = {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fuente": "esports-api.lolesports.com/persisted/gw/getSchedule",
        "partidos": partidos,
    }

    # Atómico, igual que `refrescar_ligas.py`: el generador de la web puede
    # estar leyendo esto, y media escritura no es un dato viejo, es un JSON que
    # no parsea.
    os.makedirs(os.path.dirname(args.destino), exist_ok=True)
    tmp = args.destino + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(documento, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, args.destino)
    except OSError as exc:
        print(f"Fallo escribiendo {args.destino}: {exc}")
        if os.path.exists(tmp):
            os.remove(tmp)
        return 1

    print(f"\nEscrito {args.destino} ({os.path.getsize(args.destino):,} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

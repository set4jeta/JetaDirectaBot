"""Cuentas de pros desde las escaleras de SoloQ de dpm.lol.

Cambios respecto a la versión anterior
--------------------------------------
1. **La paginación no tenía tope.** `while True` con `page += 1` y solo salía
   cuando la respuesta traía 0 jugadores. Si dpm.lol devolvía siempre la misma
   página (o un 200 con el mismo contenido), el bucle no terminaba nunca.
   Ahora hay `MAX_PAGES` y detección de página repetida.
2. **Un error de red rompía la paginación en silencio.** El `except` hacía
   `break`, así que un fallo en la página 3 de 10 daba un resultado parcial que
   luego se escribía como si fuera completo. Ahora se marca la descarga como
   incompleta y `main()` no escribe si el recuento cayó.
3. **La escritura era incondicional.** `json.dump(nuevos, ...)` sin comprobar
   nada. Ahora pasa por `utils.safe_json.guardar_lista_json`.
4. Los `print` pasan a `log`, para que el arranque de la consola sea legible.
5. **Ya no es solo Europa.** La plataforma estaba escrita a mano (`platform=euw1`)
   y el resto del mundo no existía para `/info` ni `/ranking`. Ahora se baja la
   escalera de varias plataformas (`PLATAFORMAS`) y se guarda **la plataforma de
   cada cuenta**, que la API manda en cada fila y antes se descartaba. Medido:
   EUW1 539, KR 271, BR1 140, NA1 108, y unas pocas en EUN1/LA1/JP1.

Qué es y qué no es este fichero
-------------------------------
Es una **lista de nombres, equipo y plataforma** para poder resolver a alguien en
`/info` y `/ranking`. **No trae rangos**: las filas del leaderboard no los dan
(`rank` sale `None`), y los rangos de verdad viven en `ranked_data.json`, que se
llena consultando a Riot y tiene su propio TTL. Por eso este fichero se puede
refrescar despacio: lo que caduca rápido son los LP, no la lista.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from models.bootcamp_player import BootcampPlayer
from utils.logger import get_logger
from utils.safe_json import cargar_lista_json, guardar_lista_json

log = get_logger(__name__)

ENDPOINT = (
    "https://dpm.lol/v1/leaderboards/soloq"
    "?page={page}&platform={platform}&isPro=true"
)
JSON_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")

#: Plataformas de las que se baja la escalera. Son las que tienen liga en el
#: catálogo (`leagues.LIGAS`): EUW1 y EUN1 cubren la LEC y las nueve europeas,
#: NA1 la LCS, BR1 la CBLOL, LA1/LA2 la LLA (que no se puede soportar para avisos
#: pero su escalera existe y sirve para consultar), KR la LCK y JP1 la LJL.
#:
#: Se puede acortar sin tocar código: `LEADERBOARD_PLATFORMS=euw1,kr`.
PLATAFORMAS: tuple[str, ...] = tuple(
    p.strip().lower()
    for p in os.getenv("LEADERBOARD_PLATFORMS", "euw1,eun1,na1,br1,la1,la2,kr,jp1").split(",")
    if p.strip()
)

#: Tope de seguridad por plataforma. Con ~540 jugadores y 50 por página sobra.
MAX_PAGES = 40
TIMEOUT = 25


def _fetch_plataforma(plataforma: str) -> tuple[list[dict[str, Any]], bool]:
    """Todas las páginas de UNA plataforma. Devuelve `(filas, completo)`.

    Va por `apis.transporte_dpm`, que intenta cloudscraper y **reintenta con
    curl_cffi** cuando Cloudflare no deja pasar. Este módulo tenía su propio
    `cloudscraper` y era el último que seguía fallando desde Render: los logs
    decían `Leaderboard: 0 cuentas de 8 plataformas` mientras el resto del
    scraping ya se había recuperado con el respaldo.

    `completo=False` significa que la descarga se cortó a mitad, y quien llame no
    debe tratar el resultado como definitivo.
    """
    from apis import transporte_dpm

    todos: list[dict[str, Any]] = []
    vistos: set[str] = set()
    completo = True
    page = 0

    for page in range(1, MAX_PAGES + 1):
        resp = transporte_dpm.pedir(
            ENDPOINT.format(page=page, platform=plataforma), timeout=TIMEOUT
        )
        if resp is None:
            log.error("%s página %d: sin respuesta. Incompleta.", plataforma, page)
            completo = False
            break

        if resp.status != 200:
            # 422 = dpm no conoce esa plataforma, y 404 = no hay escalera ahí: no
            # es un fallo, es que no existe, así que se salta y se sigue.
            #
            # Cualquier otro estado **sí es un fallo** y se marca la descarga como
            # incompleta. Antes se trataba todo igual y un **403 de Cloudflare**
            # (que es justo lo que pasaba desde Render) se leía como "esa escalera
            # no existe": las ocho plataformas se saltaban en silencio, el
            # resultado salía "completo" con 0 cuentas, y el único que lo frenaba
            # era la guarda de `guardar_lista_json`. El log lo enseñó tal cual:
            # `euw1: HTTP 403 en la página 1. Se salta esa escalera.`
            if resp.status in (404, 422):
                log.warning(
                    "%s: HTTP %s en la página %d. Esa escalera no existe; se salta.",
                    plataforma, resp.status, page,
                )
                return todos, True
            log.error(
                "%s: HTTP %s en la página %d. Se corta esa escalera y la descarga "
                "queda incompleta.",
                plataforma, resp.status, page,
            )
            completo = False
            break

        try:
            data = resp.json()
        except ValueError as exc:
            log.error("%s página %d: respuesta no-JSON (%s). Incompleta.", plataforma, page, exc)
            completo = False
            break

        players = data.get("players", []) if isinstance(data, dict) else []
        if not players:
            break

        # Detección de página repetida: sin esto, un endpoint que ignore `page`
        # dejaría el bucle girando hasta MAX_PAGES duplicando datos.
        claves = {f"{p.get('gameName')}#{p.get('tagLine')}" for p in players}
        if claves and claves <= vistos:
            log.warning(
                "%s página %d repite jugadores ya vistos; se corta ahí.", plataforma, page
            )
            break
        vistos |= claves

        todos.extend(players)
        log.debug("%s página %d: %d jugadores.", plataforma, page, len(players))
    else:
        log.warning("%s: se alcanzó el tope de %d páginas.", plataforma, MAX_PAGES)
        completo = False

    log.info("%s: %d cuentas en %d páginas%s.", plataforma, len(todos), page,
             "" if completo else " (INCOMPLETA)")
    return todos, completo


def fetch_players() -> tuple[list[dict[str, Any]], bool]:
    """Descarga la escalera de pros de cada plataforma. `(jugadores, completo)`.

    Sin cliente propio: cada petición va por `transporte_dpm`, que ya lleva el
    respaldo de curl_cffi. Antes se creaba aquí un `cloudscraper` (con el
    comentario de que uno solo valía para todas, que era cierto) y desde Render
    Cloudflare le contestaba 403 a todas.
    """
    todos: list[dict[str, Any]] = []
    completo = True

    for plataforma in PLATAFORMAS:
        filas, ok = _fetch_plataforma(plataforma)
        # La API ya manda `platform` en cada fila, pero se reescribe con la que se
        # ha pedido: es de lo que depende que la cuenta se consulte contra el
        # servidor correcto, y no se deja al criterio de un campo que puede
        # desaparecer.
        for fila in filas:
            fila["platform"] = plataforma
        todos.extend(filas)
        if not ok:
            completo = False

    log.info(
        "Leaderboard: %d cuentas de %d plataformas%s.",
        len(todos), len(PLATAFORMAS), "" if completo else " (INCOMPLETO)",
    )
    return todos, completo


def agrupar_por_display_name(players: list[dict[str, Any]]) -> dict[str, list[dict]]:
    agrupados: dict[str, list[dict]] = defaultdict(list)
    for p in players:
        nombre = p.get("displayName") or p.get("gameName")
        if nombre:
            agrupados[nombre].append(p)
    return agrupados


def cargar_existentes() -> list[dict]:
    return cargar_lista_json(JSON_PATH)


def main() -> bool:
    """Refresca `accounts.json`. Devuelve True si escribió."""
    raw_players, completo = fetch_players()

    if not raw_players:
        log.error("El leaderboard devolvió 0 cuentas; no se toca %s.", JSON_PATH)
        return False

    agrupados = agrupar_por_display_name(raw_players)
    antiguos = cargar_existentes()
    nuevos: list[dict] = []

    for nombre, cuentas in agrupados.items():
        player = BootcampPlayer.from_leaderboard_group(nombre, cuentas)
        previo = next(
            (p for p in antiguos if p.get("name", "").lower() == player.name.lower()),
            None,
        )
        for acc in player.accounts:
            if not previo:
                continue
            for acc_ant in previo.get("accounts", []):
                riot_ant = acc_ant.get("riot_id") or {}
                if (
                    acc.riot_id["game_name"].lower() == (riot_ant.get("game_name") or "").lower()
                    and acc.riot_id["tag_line"].lower() == (riot_ant.get("tag_line") or "").lower()
                    and acc_ant.get("puuid")
                ):
                    acc.puuid = acc_ant["puuid"]
                    acc.stale = acc_ant.get("stale", False)
                    break
        nuevos.append(player.to_dict())

    # Si la descarga se cortó, exigimos que el resultado sea prácticamente igual
    # al anterior; cualquier pérdida apreciable se rechaza.
    min_ratio = 0.95 if not completo else 0.8
    return guardar_lista_json(
        JSON_PATH,
        nuevos,
        etiqueta="accounts (leaderboard)",
        min_ratio=min_ratio,
    )


if __name__ == "__main__":
    main()

"""Cuentas de pros europeos desde el leaderboard de SoloQ de dpm.lol.

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
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

import cloudscraper

from models.bootcamp_player import BootcampPlayer
from utils.logger import get_logger
from utils.safe_json import cargar_lista_json, guardar_lista_json

log = get_logger(__name__)

ENDPOINT = "https://dpm.lol/v1/leaderboards/soloq?page={page}&platform=euw1&isPro=true"
JSON_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")

#: Tope de seguridad. Con ~520 jugadores y 50 por página sobra de largo.
MAX_PAGES = 40
TIMEOUT = 25


def fetch_players() -> tuple[list[dict[str, Any]], bool]:
    """Descarga el leaderboard paginado.

    Devuelve `(jugadores, completo)`. `completo=False` significa que la descarga
    se cortó a mitad, y quien llame no debe tratar el resultado como definitivo.
    """
    scraper = cloudscraper.create_scraper()
    todos: list[dict[str, Any]] = []
    vistos: set[str] = set()
    completo = True

    for page in range(1, MAX_PAGES + 1):
        try:
            resp = scraper.get(ENDPOINT.format(page=page), timeout=TIMEOUT)
        except Exception as exc:
            log.error("Página %d: fallo de red (%s). Descarga incompleta.", page, exc)
            completo = False
            break

        if resp.status_code != 200:
            log.error("Página %d: HTTP %s. Descarga incompleta.", page, resp.status_code)
            completo = False
            break

        try:
            data = resp.json()
        except ValueError as exc:
            log.error("Página %d: respuesta no-JSON (%s). Descarga incompleta.", page, exc)
            completo = False
            break

        players = data.get("players", []) if isinstance(data, dict) else []
        if not players:
            break

        # Detección de página repetida: sin esto, un endpoint que ignore `page`
        # dejaría el bucle girando hasta MAX_PAGES duplicando datos.
        claves = {f"{p.get('gameName')}#{p.get('tagLine')}" for p in players}
        if claves and claves <= vistos:
            log.warning("Página %d repite jugadores ya vistos; se corta ahí.", page)
            break
        vistos |= claves

        todos.extend(players)
        log.debug("Página %d: %d jugadores.", page, len(players))
    else:
        log.warning("Se alcanzó el tope de %d páginas; puede faltar gente.", MAX_PAGES)
        completo = False

    log.info(
        "Leaderboard: %d cuentas en %d páginas%s.",
        len(todos),
        page,
        "" if completo else " (INCOMPLETO)",
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

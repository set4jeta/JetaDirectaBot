"""Deducción de la línea (rol) a partir del campeón.

dpm.lol no devuelve la posición en la que se jugó una partida: su historial
trae `role` con valores como "PRO" y `team` con el nombre del equipo, pero
nada de líneas. Por eso `!historial` (y `!live`) buscaban los campos
`teamPosition` / `position`, que esa API no envía, y acababan mostrando el
rol vacío.

En lugar de dejarlo en blanco se deduce la línea más probable a partir del
campeón, usando los pickrates por línea que el propio bot ya descarga de
dpm.lol en `champion_lane_pickrates.json`.

No es adivinación a ciegas: si un campeón se juega en su línea con una
probabilidad alta (Cassiopeia en mid, Morgana de support), la deducción es
fiable. Cuando la probabilidad es baja se devuelve cadena vacía y el bot
simplemente no muestra rol, en vez de inventarlo.
"""

from __future__ import annotations

import json
import os
import threading

from utils.logger import get_logger

log = get_logger("utils.lane_guess")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKRATES_PATH = os.path.join(BASE_DIR, "champion_lane_pickrates.json")

# Por debajo de esta probabilidad no se afirma nada: el campeón es demasiado
# flexible (por ejemplo un flex de mid/top) como para asegurar la línea.
UMBRAL = 40.0

# Las líneas en el JSON de pickrates usan los nombres de la API de Riot.
_TRADUCCION = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MID",
    "MID": "MID",
    "BOTTOM": "ADC",
    "ADC": "ADC",
    "UTILITY": "SUPPORT",
    "SUPPORT": "SUPPORT",
}


from utils.champion_names import ALIAS_A_DISPLAY, normalizar

_lock = threading.Lock()
_lanes_por_campeon: dict[str, str] | None = None


def _cargar() -> dict[str, str]:
    """Construye {nombre_campeon: linea} una sola vez y lo deja en memoria."""
    global _lanes_por_campeon
    if _lanes_por_campeon is not None:
        return _lanes_por_campeon

    with _lock:
        if _lanes_por_campeon is not None:
            return _lanes_por_campeon

        if not os.path.exists(PICKRATES_PATH):
            log.warning("No existe %s: no se podrá deducir la línea.", PICKRATES_PATH)
            _lanes_por_campeon = {}
            return _lanes_por_campeon

        from cache.champion_cache import CHAMPION_ID_TO_NAME

        with open(PICKRATES_PATH, "r", encoding="utf-8") as f:
            por_id = json.load(f)

        resultado: dict[str, str] = {}
        for champ_id, lanes in por_id.items():
            nombre = CHAMPION_ID_TO_NAME.get(str(champ_id))
            if not nombre or not isinstance(lanes, dict) or not lanes:
                continue
            linea_cruda, prob = max(lanes.items(), key=lambda kv: kv[1])
            if prob < UMBRAL:
                continue
            linea = _TRADUCCION.get(str(linea_cruda).upper())
            if linea:
                resultado[normalizar(nombre)] = linea

        _lanes_por_campeon = resultado
        log.debug("Líneas deducibles para %d campeones.", len(resultado))

    return _lanes_por_campeon


def guess_lane(champion_name: str | None) -> str:
    """Devuelve la línea probable ('TOP', 'JUNGLE', 'MID', 'ADC', 'SUPPORT').

    Devuelve cadena vacía si no se puede afirmar con seguridad, que es lo que
    pasa con los campeones recién lanzados o sin datos suficientes.
    """
    if not champion_name:
        return ""
    clave = normalizar(champion_name)
    tabla = _cargar()
    return tabla.get(clave) or tabla.get(normalizar(ALIAS_A_DISPLAY.get(clave, "")))


def recargar() -> None:
    """Fuerza la recarga tras actualizar el JSON de pickrates."""
    global _lanes_por_campeon
    with _lock:
        _lanes_por_campeon = None

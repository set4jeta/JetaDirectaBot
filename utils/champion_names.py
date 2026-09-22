"""Traducción entre los dos nombres que tiene cada campeón.

Riot maneja dos identificadores distintos y el bot se los encuentra mezclados:

- **Nombre de display**, el que ve el jugador: "Lee Sin", "Wukong", "Bel'Veth",
  "Cho'Gath". Es el que trae `cache/champion_cache.py`.
- **Nombre interno**, el que usan las APIs: "LeeSin", "MonkeyKing", "Belveth",
  "Chogath". Es el que devuelven dpm.lol y Riot.

Compararlos tal cual hace que un tercio de los campeones no se reconozca: al
generar `champion_lane_pickrates.json` se perdían 24 de 173 porque dpm.lol
decía "MonkeyKing" y el caché solo conocía "Wukong".

Comparando sin espacios ni puntuación coinciden todos salvo tres que cambian
de raíz por completo y necesitan un alias explícito.
"""

from __future__ import annotations

import threading

# Casos en los que normalizar no basta: el nombre interno y el de display no
# comparten raíz.
ALIAS_A_DISPLAY = {
    "monkeyking": "wukong",
    "nunu": "nunu & willump",
    "renata": "renata glasc",
}


def normalizar(nombre: str) -> str:
    """Deja el nombre en minúsculas y sin espacios ni puntuación.

    "Bel'Veth" y "Belveth" quedan ambos como "belveth".
    """
    return "".join(c for c in nombre.lower() if c.isalnum())


_lock = threading.Lock()
_id_por_nombre: dict[str, str] | None = None


def id_por_nombre_interno() -> dict[str, str]:
    """Mapa {nombre normalizado: id de campeón} construido una sola vez.

    Acepta tanto el nombre de display como el interno, así que
    "LeeSin", "Lee Sin" y "leesin" llevan todos al mismo id.
    """
    global _id_por_nombre
    if _id_por_nombre is not None:
        return _id_por_nombre

    with _lock:
        if _id_por_nombre is not None:
            return _id_por_nombre

        from cache.champion_cache import CHAMPION_ID_TO_NAME

        mapa: dict[str, str] = {}
        for champ_id, display in CHAMPION_ID_TO_NAME.items():
            mapa[normalizar(display)] = champ_id
            mapa[normalizar(str(display).replace(" ", ""))] = champ_id

        # Los alias se resuelven al nombre de display y de ahí al id.
        display_por_normalizado = {normalizar(v): v for v in CHAMPION_ID_TO_NAME.values()}
        for interno, display in ALIAS_A_DISPLAY.items():
            destino = display_por_normalizado.get(normalizar(display))
            if destino is not None:
                mapa[interno] = mapa[normalizar(destino)]

        _id_por_nombre = mapa

    return _id_por_nombre


def a_id(nombre: str) -> str | None:
    """Id de campeón a partir de cualquiera de sus dos nombres."""
    if not nombre:
        return None
    clave = normalizar(nombre)
    mapa = id_por_nombre_interno()
    return mapa.get(clave) or mapa.get(normalizar(ALIAS_A_DISPLAY.get(clave, "")))

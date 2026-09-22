"""Extractor del payload embebido de dpm.lol (React Server Components).

Por qué existe
--------------
`accounts_from_teams.py` sacaba los nombres de los jugadores con un selector de
clases de Tailwind:

    soup.find_all("span", class_="font-semibold text-bm lg:text-bxl")

Eso funciona hoy y se rompe el día que dpm.lol recompile su CSS, porque
`text-bm` o `lg:text-bxl` son nombres generados. Y además solo daba el **nombre
visible**: para todo lo demás (cuentas, plataforma, PUUID) había que hacer una
petición extra por jugador a `/v1/pros/<nombre>`.

Lo que se comprobó
------------------
dpm.lol es un Next.js con React Server Components. El HTML trae el estado
serializado en llamadas `self.__next_f.push([1,"..."])`. Concatenando esos trozos
y decodificándolos aparece el array `"players":[...]` con **todo** lo que el bot
necesita, ya estructurado:

    puuid, gameName, tagLine, displayName, role, team, lane, platform,
    summonerLevel, profileIcon, updatedAt,
    ranks: [{queue, tier, rank, leaguePoints, wins, losses, platform, puuid}]

Medido en G2 y FNC: 5 jugadores cada uno, con `lane` incluido (JUNGLE, MID...),
que antes se inferían por pickrates. Un equipo entero en **una** petición.

Ventaja de robustez: `"players":[{"puuid":...` es una clave de datos, no una clase
de CSS. Un rediseño visual de dpm.lol no la toca. Y si algún día desaparece,
`extraer_jugadores_de_equipo` avisa devolviendo lista vacía, que la guarda de
`utils.safe_json` convierte en "no escribo nada" en vez de en pérdida de datos.
"""

from __future__ import annotations

import json
import re
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)

_PUSH = re.compile(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)')

#: Clave que abre el array de jugadores dentro del flujo RSC.
_ANCLA = '"players":['


def reconstruir_payload(html: str) -> str:
    """Concatena y desescapa todos los `__next_f.push` de la página.

    Next.js parte el estado en varios `push` porque va enviándolo a trozos
    mientras renderiza; un objeto JSON puede quedar cortado entre dos trozos, así
    que hay que unirlos **antes** de intentar parsear nada.
    """
    partes: list[str] = []
    for crudo in _PUSH.findall(html):
        try:
            partes.append(json.loads(f'"{crudo}"'))
        except json.JSONDecodeError:
            # Un trozo ilegible no invalida el resto del flujo.
            continue
    return "".join(partes)


def _recortar_array(texto: str, inicio: int) -> str | None:
    """Devuelve el array JSON que empieza en `inicio` contando corchetes.

    No se puede usar una expresión regular: los objetos anidan y las cadenas
    pueden contener corchetes (los `path` de los SVG están llenos). Hay que
    llevar la cuenta a mano respetando comillas y escapes.
    """
    profundidad = 0
    en_cadena = False
    escapado = False

    for i in range(inicio, len(texto)):
        c = texto[i]

        if escapado:
            escapado = False
            continue
        if c == "\\":
            escapado = True
            continue
        if c == '"':
            en_cadena = not en_cadena
            continue
        if en_cadena:
            continue

        if c == "[":
            profundidad += 1
        elif c == "]":
            profundidad -= 1
            if profundidad == 0:
                return texto[inicio : i + 1]

    return None


def extraer_jugadores(html: str) -> list[dict[str, Any]]:
    """Saca la lista de jugadores del HTML de una página de dpm.lol.

    Devuelve `[]` si no encuentra nada. Quien llame **tiene que** tratar la lista
    vacía como fallo, nunca como "el equipo no tiene jugadores".
    """
    flujo = reconstruir_payload(html)
    if not flujo:
        log.warning("No se encontró ningún payload __next_f en la página.")
        return []

    candidatos: list[dict[str, Any]] = []
    desde = 0
    while True:
        pos = flujo.find(_ANCLA, desde)
        if pos == -1:
            break
        arranque = pos + len(_ANCLA) - 1  # el '[' del array
        bruto = _recortar_array(flujo, arranque)
        desde = pos + len(_ANCLA)
        if not bruto:
            continue
        try:
            datos = json.loads(bruto)
        except json.JSONDecodeError:
            continue
        if isinstance(datos, list):
            utiles = [d for d in datos if isinstance(d, dict) and d.get("gameName")]
            if len(utiles) > len(candidatos):
                candidatos = utiles

    if not candidatos:
        log.warning(
            "Payload encontrado (%d caracteres) pero sin array 'players' usable. "
            "dpm.lol pudo cambiar la estructura.",
            len(flujo),
        )
    return candidatos


# ---------------------------------------------------------------------- #
# Normalización a la forma que ya usa el bot
# ---------------------------------------------------------------------- #

_LANES = {
    "TOP": "top",
    "JUNGLE": "jungle",
    "MIDDLE": "mid",
    "MID": "mid",
    "BOTTOM": "bot",
    "BOT": "bot",
    "ADC": "bot",
    "UTILITY": "support",
    "SUPPORT": "support",
}


def normalizar_lane(valor: str | None) -> str | None:
    """`JUNGLE` -> `jungle`. dpm.lol y Riot no usan los mismos nombres."""
    if not valor:
        return None
    return _LANES.get(valor.strip().upper())


def mejor_rango_soloq(jugador: dict[str, Any]) -> dict[str, Any] | None:
    """Devuelve la entrada de SoloQ, o `None` si el jugador no tiene rango."""
    for r in jugador.get("ranks") or []:
        if isinstance(r, dict) and r.get("queue") == "RANKED_SOLO_5x5":
            return r
    return None


def resumen(jugadores: list[dict[str, Any]]) -> str:
    """Una línea legible para el log, sin volcar el JSON entero."""
    if not jugadores:
        return "sin jugadores"
    partes = []
    for j in jugadores:
        nombre = j.get("displayName") or j.get("gameName") or "?"
        lane = normalizar_lane(j.get("lane")) or "?"
        partes.append(f"{nombre}({lane})")
    return ", ".join(partes)

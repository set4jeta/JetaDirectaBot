# tracking/soloq/censo.py
"""Copia **compacta** del censo de jugadores, para que el bot no arranque ciego.

Por qué existe
--------------
`accounts_from_teams.json` es el censo: 908 jugadores y 1950 cuentas, 1,7 MB. Lo
escribe el refresco de rosters a partir de dpm.lol. El problema es que **no se
puede reconstruir si dpm.lol no responde**, y eso dejó de ser hipotético el
01-11-2026: Cloudflare empezó a contestar **403 a la IP de Render** (ver
`apis/transporte_dpm.py`), así que el fichero no llegaba a crearse, el barrido se
quedaba con 0 cuentas y el bot seguía «encendido» —`/health` en 200, `/live-games`
en 200— sin avisar de absolutamente nada. El síntoma era mudo: 0 MB de consumo y
cero errores propios.

Por qué no basta con subir el censo grande a la rama de estado
-------------------------------------------------------------
Porque son 1,7 MB y la API de contenidos de GitHub trabaja cómoda por debajo de
1 MB. Además el 80 % de ese peso son datos que el barrido **no usa**:
`last_champions`, `rank`, `profile_icon`, `summoner_level`, `kda`, `links`,
`contract`… Eso es para pintar fichas, no para saber a quién sondear.

Este fichero guarda solo lo que el barrido necesita —nombre, equipo, liga, rol y
las cuentas con su PUUID y su plataforma— y **medido sobre el censo real son
274 KB**, con las mismas 1950 cuentas. Cabe de sobra en la rama de estado, que ya
sobrevive a reinicios y despliegues (`core/estado_remoto.py`).

Qué garantiza y qué no
----------------------
Garantiza que el bot **nunca arranca con cero jugadores**: si el censo grande no
está, se lee este y el barrido funciona con lo último que se supo. No garantiza
que el censo esté al día: un fichaje de ayer no aparece hasta que dpm.lol vuelva
a responder. Por eso el fichero guarda la fecha en que se escribió
(`escrito_en`) y `edad_dias()` la expone, para que `/health` y el log puedan decir
«el censo tiene 12 días» en vez de callarse.

Formato
-------
Lista de jugadores con claves cortas, porque el objetivo es el tamaño:

    {"n": "Faker", "tm": "T1", "tn": "T1", "lg": "lck", "r": "Mid",
     "a": [{"g": "Hide on bush", "t": "KR1", "p": "<puuid>", "s": "KR"}]}

`leer()` devuelve la **forma larga** que espera `BootcampPlayer.from_dict`, así
que quien lo consume no tiene que saber que viene de aquí.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Iterable

from utils.logger import get_logger

log = get_logger("tracking.censo")

#: Va junto al censo grande y, como él, **no** en `main`: es estado que el bot
#: reconstruye. Lo que sí viaja es su copia en la rama de estado.
RUTA = os.environ.get("CENSO_COMPACTO_RUTA") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "censo_compacto.json"
)

#: Campos del jugador que el barrido y `/info` necesitan. El resto se descarta.
_CAMPOS_JUGADOR = (
    ("name", "n"),
    ("team", "tm"),
    ("team_name", "tn"),
    ("league", "lg"),
    ("role", "r"),
)


def _compactar_cuenta(cuenta: dict[str, Any]) -> dict[str, Any] | None:
    """Una cuenta reducida a lo mínimo. `None` si no sirve para sondear."""
    riot = cuenta.get("riot_id") or {}
    game_name = (riot.get("game_name") or "").strip()
    if not game_name:
        return None
    return {
        "g": game_name,
        "t": (riot.get("tag_line") or "").strip(),
        "p": cuenta.get("puuid") or "",
        "s": (cuenta.get("platform") or "").strip(),
        # `stale` es una decisión que el bot ya tomó (Riot no conoce esa
        # cuenta). Si no se guarda, al restaurar se reintentaría en cada
        # pasada una cuenta que se sabe muerta.
        "x": 1 if cuenta.get("stale") else 0,
    }


def compactar(jugadores: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Censo completo -> censo compacto. Descarta jugadores sin cuentas útiles.

    Un jugador sin ninguna cuenta no se puede barrer, así que no ocupa sitio: es
    el mismo criterio que aplica `refrescar_ligas` al guardar.
    """
    salida: list[dict[str, Any]] = []
    for jugador in jugadores or []:
        if not isinstance(jugador, dict):
            continue
        cuentas = [
            c for c in (
                _compactar_cuenta(a)
                for a in (jugador.get("accounts") or [])
                if isinstance(a, dict)
            ) if c
        ]
        if not cuentas:
            continue
        fila: dict[str, Any] = {}
        for largo, corto in _CAMPOS_JUGADOR:
            valor = jugador.get(largo)
            if valor:
                fila[corto] = valor
        fila["a"] = cuentas
        salida.append(fila)
    return salida


def _expandir(fila: dict[str, Any]) -> dict[str, Any]:
    """Censo compacto -> forma larga que entiende `BootcampPlayer.from_dict`."""
    jugador: dict[str, Any] = {}
    for largo, corto in _CAMPOS_JUGADOR:
        if fila.get(corto):
            jugador[largo] = fila[corto]
    # `displayName` es lo que resuelve `/track <nick>` contra dpm; el nombre ya
    # cumple esa función y sin él la búsqueda por nick se queda sin índice.
    jugador.setdefault("displayName", jugador.get("name", ""))
    jugador["accounts"] = [
        {
            "riot_id": {"game_name": c.get("g", ""), "tag_line": c.get("t", "")},
            "puuid": c.get("p") or None,
            "platform": c.get("s") or None,
            "stale": bool(c.get("x")),
        }
        for c in (fila.get("a") or [])
        if isinstance(c, dict) and c.get("g")
    ]
    return jugador


def escribir(jugadores: Iterable[dict[str, Any]]) -> bool:
    """Escribe la copia compacta a partir del censo completo. True si escribió.

    Nunca lanza: quien llama acaba de guardar el censo grande y eso es lo
    importante; que falle la copia no puede costar el refresco entero.
    """
    try:
        compacto = compactar(jugadores)
        if not compacto:
            log.warning("Censo compacto: no hay jugadores con cuentas; no se escribe.")
            return False
        sobre = {
            "escrito_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "jugadores": compacto,
        }
        os.makedirs(os.path.dirname(RUTA), exist_ok=True)
        tmp = RUTA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sobre, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, RUTA)
        log.info(
            "Censo compacto escrito: %d jugadores, %.0f KB.",
            len(compacto), os.path.getsize(RUTA) / 1024,
        )
        return True
    except (OSError, TypeError, ValueError) as exc:
        log.warning("No se pudo escribir el censo compacto: %s", exc)
        return False


def _sobre() -> dict[str, Any] | None:
    try:
        with open(RUTA, encoding="utf-8") as fh:
            datos = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("Censo compacto ilegible (%s); se ignora.", exc)
        return None
    if not isinstance(datos, dict) or not isinstance(datos.get("jugadores"), list):
        return None
    return datos


def leer() -> list[dict[str, Any]]:
    """El censo guardado, en forma larga. Lista vacía si no hay copia."""
    sobre = _sobre()
    if sobre is None:
        return []
    return [
        _expandir(f) for f in sobre["jugadores"]
        if isinstance(f, dict) and f.get("a")
    ]


def edad_dias() -> float | None:
    """Días desde que se escribió la copia. `None` si no hay copia o no se sabe.

    Existe para que la antigüedad del censo se pueda **decir**. Un censo de hace
    tres semanas no es lo mismo que uno de ayer, y hasta ahora la única forma de
    saberlo era mirar la fecha del fichero a mano.
    """
    sobre = _sobre()
    if sobre is None:
        return None
    try:
        cuando = datetime.fromisoformat(str(sobre.get("escrito_en")))
    except (TypeError, ValueError):
        # Copia escrita antes de que existiera `escrito_en`: se usa el mtime, que
        # para esto vale igual y no obliga a descartar el fichero.
        try:
            return max(0.0, (time.time() - os.path.getmtime(RUTA)) / 86400)
        except OSError:
            return None
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - cuando).total_seconds() / 86400)


def resumen() -> str:
    """Una línea para el log de arranque."""
    edad = edad_dias()
    if edad is None:
        return "sin copia"
    return f"{edad:.1f} días de antigüedad"

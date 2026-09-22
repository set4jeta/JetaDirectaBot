"""Formateo de líneas de partida para los comandos.

El mismo bloque (diccionario de emojis, resolución de posición, construcción
de la línea) estaba copiado tres veces dentro de `historial_commands.py` y
otra vez en el comando en vivo. Aquí está una sola vez.

También se corrige el problema de la posición: dpm.lol no envía ni
`teamPosition` ni `position`, así que siempre salía vacía. Ahora, si la API no
da la línea, se deduce del campeón con `utils.lane_guess`.
"""

from __future__ import annotations

from utils.lane_guess import guess_lane

POS_EMOJI = {
    "TOP": "🗻",
    "JUNGLE": "🌲",
    "MID": "✨",
    "ADC": "🏹",
    "BOTTOM": "🏹",
    "SUPPORT": "🛡️",
}

# La API de Riot nombra las líneas distinto a como las muestra el bot.
_EQUIVALENCIAS = {
    "UTILITY": "SUPPORT",
    "MIDDLE": "MID",
    "BOTTOM": "ADC",
}


def resolver_posicion(participante: dict) -> str:
    """Devuelve la línea normalizada o cadena vacía si no se puede saber.

    Orden: lo que diga la API y, si no viene, deducción por campeón.
    """
    if not isinstance(participante, dict):
        return ""

    cruda = (
        participante.get("teamPosition")
        or participante.get("position")
        or participante.get("role")
        or ""
    )
    if not isinstance(cruda, str) or not cruda:
        return guess_lane(participante.get("championName"))

    # `role` en dpm.lol vale "PRO" (indica que es profesional), no una línea.
    normalizada = cruda.strip().upper()
    if normalizada in ("PRO", "NONE", "UNKNOWN"):
        return guess_lane(participante.get("championName"))

    return _EQUIVALENCIAS.get(normalizada, normalizada)


def emoji_posicion(pos: str) -> str:
    return POS_EMOJI.get(pos.upper(), "") if pos else ""


def formatear_partida(participante: dict, match: dict, cuenta: str | None = None,
                      idioma: str | None = None) -> str:
    """Una línea del historial: `✅ **Campeón** (Mid) ✨ | 5/2/8 | 28 min | 🕒 ...`.

    `cuenta` se añade al final entre paréntesis cuando el jugador tiene varias.

    Lo único traducible de la línea es ese sufijo: el nombre del campeón y la
    línea son términos de Riot. `idioma` va al final para no romper a
    `scripts/test_historial.py`, que llama con dos argumentos.
    """
    from utils.i18n import t

    campeon = participante.get("championName", "???")
    kills = participante.get("kills", 0)
    deaths = participante.get("deaths", 0)
    assists = participante.get("assists", 0)
    win = participante.get("win", False)
    minutos = (match.get("gameDuration", 0) or 0) // 60

    pos = resolver_posicion(participante)
    pos_str = f" ({pos.title()})" if pos else ""
    emoji = emoji_posicion(pos)

    inicio = match.get("gameCreation")
    hora = f"<t:{int(inicio / 1000)}:f>" if isinstance(inicio, (int, float)) else "¿?"

    linea = (
        f"{'✅' if win else '❌'} **{campeon}**{pos_str} {emoji} "
        f"| {kills}/{deaths}/{assists} | {minutos} min | 🕒 {hora}"
    )
    if cuenta:
        linea += t("historial.cuenta_sufijo", idioma, cuenta=cuenta)
    return linea


def nick_con_equipo(nombre: str, equipo: str | None, cuenta: str | None = None) -> str:
    """`Caps [G2] (Caps#G2W)`."""
    tricode = (equipo or "").upper()
    base = f"{nombre} [{tricode}]" if tricode else nombre
    return f"{base} ({cuenta})" if cuenta else base

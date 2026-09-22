"""Qué jugadores se siguen.

Cómo se decidía antes
---------------------
    TRACKED_TEAMS = {"G2", "FNC", "VIT", "TH", "KC", "NAVI",
                     "GX", "BDS", "SK", "MKOI", "KOI", "LR"}

Un set escrito a mano, igual para todos los servidores. Medido el 2026-09-01
contra el leaderboard real de la LEC, los equipos son `FNC G2 GX KC MKOI NAVI
SHFT SK TH VIT`: **`BDS`, `KOI` y `LR` ya no existen** y el bot se perdía
`SHFT`. Ningún log lo decía porque el scraper simplemente no encontraba esos
equipos.

Cómo se decide ahora
--------------------
Cada jugador lleva la liga por la que entró (`BootcampPlayer.league`) y cada
servidor elige las suyas en `tracking/soloq/leagues.py`. Esta función filtra
por eso:

* Con `guild_id`, devuelve solo los jugadores de las ligas de ese servidor.
* Sin `guild_id`, devuelve todos: es lo que necesita la pasada global del
  tracker, que luego decide a quién avisa según cada canal.

`TRACKED_TEAMS` se conserva para no romper los scripts que la importan, pero
ya no decide el seguimiento.
"""

from __future__ import annotations

from utils.logger import get_logger

log = get_logger("utils.player_filters")

#: Obsoleto. Se mantiene solo por compatibilidad con scripts antiguos; el
#: seguimiento se decide por liga, no por equipo. Ver el docstring del módulo.
TRACKED_TEAMS = {"G2", "FNC", "VIT", "TH", "KC", "NAVI", "GX", "BDS", "SK", "MKOI", "KOI", "LR"}


def get_tracked_players(players, guild_id=None):
    """Jugadores a los que hay que hacer seguimiento.

    `guild_id=None` significa "todos", que es lo que usa la pasada global.
    """
    if guild_id is None:
        tracked = list(players)
    else:
        from tracking.soloq.leagues import ligas_de

        elegidas = set(ligas_de(guild_id))
        tracked = [p for p in players if _liga_de(p) in elegidas]

    equipos_encontrados = sorted({(p.team or "").upper() for p in tracked if p.team})
    total_cuentas = sum(len(p.accounts) for p in tracked)
    log.debug(
        "Trackeando %d jugadores (%d cuentas) de %d totales | equipos: %s",
        len(tracked), total_cuentas, len(players),
        ", ".join(equipos_encontrados) or "ninguno",
    )
    return tracked


def _liga_de(player) -> str:
    """Liga de un jugador, con respaldo para los JSON antiguos.

    Un jugador guardado antes de que existieran las ligas tiene `league=""`.
    Se trata como LEC porque es lo que el bot seguía cuando se escribieron, así
    que nadie que ya lo tuviera configurado pierde a sus jugadores.
    """
    from tracking.soloq.leagues import LIGA_POR_DEFECTO

    return getattr(player, "league", "") or LIGA_POR_DEFECTO

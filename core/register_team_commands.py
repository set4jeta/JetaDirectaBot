"""Comando `!team` / `/team`: jugadores de un equipo con su mejor cuenta.

Qué se cambió
-------------

0. **Ahora también es `/team equipo:G2`.** El cuerpo es el mismo: se extrajo del
   decorador a `_cuerpo_team`, así que las dos formas responden idéntico. El
   argumento sigue admitiendo el tricode en cualquier capitalización.
- **Los textos pasan por `utils.i18n`.** El comando hablaba solo español, así
  que un servidor con `/lang en` recibía "Jugadores de G2" igual. El tricode, el
  nombre largo del equipo y el rango (tier y división) **no** se traducen: son
  nombres propios de Riot y de los equipos.
- Antes se usaba `p.accounts[0]`, la primera cuenta que apareciera en el JSON,
  sin mirar su Elo. Un pro podía salir con su cuenta secundaria de Diamante
  teniendo la principal en Challenger. Ahora se consultan todas las cuentas y
  se muestra la de mayor rango (ver `utils/rank_utils`).
- Se reutiliza el caché de rangos cuando está fresco y solo se llama a la API
  por las cuentas que no lo están, en paralelo y con límite. Con la tarea de
  fondo `refrescar_rangos` lo normal es que no haga falta ninguna petición.
- Se usa el cliente central de Riot en vez de abrir un `aiohttp.ClientSession`
  por comando: así se comparte el rate limiter y el pool de conexiones.
- El formateo de rangos estaba repetido cuatro veces; ahora es una función.
- La lista de jugadores se recarga si `accounts_from_teams.json` cambió: antes
  se leía una sola vez al importar el módulo, así que un equipo nuevo no
  aparecía hasta reiniciar el bot.
- Las peticiones de todo el equipo se lanzan juntas en vez de jugador por
  jugador: 5 jugadores en serie eran 5 esperas encadenadas.
- `await ctx.typing()` era un error latente: en nextcord 3.x `typing()` devuelve
  un gestor de contexto que **no es awaitable**, así que la línea habría
  lanzado `TypeError` en cuanto alguien usara el comando. Ahora el aviso lo da
  `Respuesta.esperando`.
"""

from __future__ import annotations

import asyncio

from nextcord.ext import commands

import config
from core.dual_command import dual_texto
from core.rank_data import get_cached_rank, save_rank_data
from core.ranked_cache import get_rank_data_or_cache
from core.responder import Respuesta
from tracking.soloq.accounts_io import load_tracked_accounts
from utils.constants import TEAM_TRICODES
from utils.i18n import idioma_de, tr
from utils.logger import get_logger
from utils.rank_utils import es_rank_valido, formatear_rank, mejor_cuenta

log = get_logger("core.team")

ROLE_ORDER = ["Top", "Jungle", "Mid", "ADC", "Support"]


async def _rank_de_cuenta(account, semaforo: asyncio.Semaphore) -> dict | None:
    """Rango de una cuenta: del caché si está fresco, si no de la API."""
    cacheado = get_cached_rank(account)
    if es_rank_valido(cacheado):
        return cacheado

    if not getattr(account, "puuid", None) or getattr(account, "stale", False):
        return cacheado

    async with semaforo:
        try:
            datos = await get_rank_data_or_cache(
                account.puuid, platform=getattr(account, "platform", None)
            )
        except Exception as exc:
            log.debug("No se pudo obtener el rango de %s: %s", account.puuid[:12], exc)
            return cacheado

    if es_rank_valido(datos):
        account.rank = datos
        # Escritura diferida: el volcado a disco lo hace `rank_store`.
        save_rank_data(account)
        return datos

    return cacheado


async def _mejor_cuenta_de(player, semaforo: asyncio.Semaphore):
    """Devuelve (cuenta, rango, total_cuentas) con la mejor cuenta del jugador."""
    cuentas = list(player.accounts)
    if not cuentas:
        return None, None, 0

    rangos = await asyncio.gather(
        *[_rank_de_cuenta(a, semaforo) for a in cuentas],
        return_exceptions=True,
    )

    pares = []
    for cuenta, rango in zip(cuentas, rangos):
        if isinstance(rango, Exception):
            log.debug("Fallo obteniendo rango: %s", rango)
            continue
        pares.append((cuenta, rango))

    elegida = mejor_cuenta(pares)
    if elegida:
        return elegida[0], elegida[1], len(cuentas)

    # Ninguna cuenta tiene rango válido: se muestra la primera para no dejar
    # al jugador fuera del listado.
    return cuentas[0], (pares[0][1] if pares else None), len(cuentas)


def equipos_disponibles() -> list[str]:
    """Tricodes con jugadores registrados, en mayúsculas y sin repetir."""
    vistos = {
        (p.team or "").upper()
        for p in load_tracked_accounts()
        if p.team
    }
    return sorted(t for t in vistos if t)


async def _cuerpo_team(res: Respuesta, team_tag: str) -> None:
    """Cuerpo compartido por `!team` y `/team`."""
    _ = tr(res.guild_id)
    idioma = idioma_de(res.guild_id)

    team_tag = (team_tag or "").lower().strip()
    if not team_tag:
        disponibles = equipos_disponibles()
        await res.error(
            _("team.falta_equipo") + "\n"
            + (_("team.equipos_con_jugadores", equipos=", ".join(disponibles))
               if disponibles else "")
        )
        return

    await res.esperando(_("team.consultando", equipo=team_tag.upper()))

    # Se recarga en cada uso: el fichero lo reescribe la tarea diaria.
    players = load_tracked_accounts()
    team_players = [p for p in players if p.team and p.team.lower() == team_tag]
    if not team_players:
        disponibles = equipos_disponibles()
        await res.error(
            _("team.sin_jugadores", equipo=team_tag.upper()) + "\n"
            + (_("team.equipos_disponibles", equipos=", ".join(disponibles))
               if disponibles else "")
        )
        return

    team_players.sort(
        key=lambda p: ROLE_ORDER.index(p.role) if p.role in ROLE_ORDER else len(ROLE_ORDER)
    )

    # No se lanzan todas las peticiones a la vez: se acota la concurrencia
    # para no acercarse al límite de la API de Riot.
    semaforo = asyncio.Semaphore(config.TRACKER_CONCURRENCY)

    # Todos los jugadores en paralelo: en serie, cada uno esperaba su turno
    # aunque el semáforo tuviera huecos libres.
    resultados = await asyncio.gather(
        *[_mejor_cuenta_de(j, semaforo) for j in team_players],
        return_exceptions=True,
    )

    lineas: list[str] = []
    sin_datos = 0

    for jugador, resultado in zip(team_players, resultados):
        if isinstance(resultado, Exception):
            log.debug("Fallo con %s: %s", jugador.name, resultado)
            lineas.append(_("team.error_rango", jugador=jugador.name))
            sin_datos += 1
            continue

        cuenta, rango, total = resultado
        if cuenta is None:
            lineas.append(_("team.sin_cuentas", jugador=jugador.name))
            continue

        game_name = cuenta.riot_id.get("game_name", "")
        tag_line = cuenta.riot_id.get("tag_line", "")
        cuenta_str = f"{game_name}#{tag_line}" if game_name else _("team.sin_cuenta")

        if not es_rank_valido(rango):
            sin_datos += 1

        # Si el jugador tiene varias cuentas se indica cuántas se han
        # comparado, para que se vea que el rango es el mejor de todas.
        extra = _("team.mejor_de", total=total) if total > 1 else ""
        lineas.append(
            f"**{jugador.name}** ({cuenta_str}) - "
            f"{formatear_rank(rango, idioma)}{extra}"
        )

    team_name_full = TEAM_TRICODES.get(team_tag.upper(), team_tag.upper())
    msg = (
        _("team.titulo", equipo=team_tag.upper(), nombre=team_name_full) + "\n\n"
        + "\n".join(lineas)
    )
    if sin_datos:
        msg += "\n\n" + _("team.aviso_sin_datos", n=sin_datos)

    await res.enviar_partido(msg)


def register_team_commands(bot: commands.Bot):
    dual_texto(
        bot,
        "team",
        "cmd.team.desc",
        _cuerpo_team,
        arg_nombre="cmd.team.arg",
        arg_desc="cmd.team.arg_desc",
    )

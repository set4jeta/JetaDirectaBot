"""Comando `!match` / `/match`: partida activa de un jugador.

Qué se cambió
-------------
0. **Ahora también es `/match jugador:elk`.**

1. **La lista de jugadores se recarga en cada uso.** Estaba en el nivel del
   módulo (`players = load_tracked_accounts()` al importar), así que un jugador
   nuevo no existía para el comando hasta reiniciar el bot. Es el mismo fallo
   que ya se corrigió en `!team`.

2. **Se acabaron los 8 intentos con `sleep(2)` por cuenta.** El bucle podía
   tardar 16 segundos *por cuenta* antes de pasar a la siguiente, y la mayoría
   de esos reintentos eran contra un 404 que ya se sabía definitivo. Ahora se
   consultan todas las cuentas en paralelo con el cliente compartido, que ya
   tiene su propio limitador y sus reintentos.

3. **Se usa el cliente central de Riot.** Antes abría un `aiohttp.ClientSession`
   por invocación, fuera del rate limiter de la key nueva.

4. **El rate limit se resuelve una vez, no por cuenta.** Si Riot limita, se cae
   a la caché de partidas activas igual que antes, pero sin repetir el intento
   por cada cuenta del jugador.
"""

from __future__ import annotations

import asyncio

from nextcord.ext import commands

import config
from apis.riot_api import get_active_game
from core.dual_command import dual_texto
from core.rank_data import get_cached_rank, save_rank_data
from core.responder import Respuesta
from core.retry_handler import add_to_retry_queue
from models.soloq_match import SoloQMatch
from tracking.soloq.accounts_io import load_tracked_accounts
from tracking.soloq.active_game_cache import (
    get_active_game_cache,
    get_active_game_cache_by_name,
)
from ui.active_match_embed import create_match_embed
from utils.game_clock import desde_cache
from utils.i18n import idioma_de, tr
from utils.logger import get_logger

log = get_logger("core.match")


def _buscar_jugador(nombre: str):
    """Jugador seguido cuyo nick coincide, ignorando espacios y mayúsculas.

    Se recarga el fichero en cada llamada a propósito: la tarea diaria lo
    reescribe y antes esto se leía una sola vez al importar el módulo.
    """
    objetivo = (nombre or "").lower().replace(" ", "")
    if not objetivo:
        return None
    for jugador in load_tracked_accounts():
        if jugador.name.lower().replace(" ", "") == objetivo:
            return jugador
    return None


def _mapa_de_rangos(match: SoloQMatch) -> dict:
    """`{puuid: rango}` para los participantes que tengan uno conocido."""
    mapa = {}
    for part in match.participants:
        puuid = getattr(part, "puuid", None)
        if not puuid:
            continue
        rank = getattr(part, "rank", None) or get_cached_rank(part)
        if rank and rank.get("tier") and rank.get("lp") is not None:
            mapa[puuid] = rank
    return mapa


async def _partida_de_cuenta(cuenta, semaforo: asyncio.Semaphore):
    """Devuelve `(cuenta, partida, estado)` de una sola cuenta."""
    if not cuenta.puuid:
        return cuenta, None, 404
    async with semaforo:
        try:
            # En SU servidor: sin `platform` el cliente pregunta a euw1 y una
            # cuenta de KR/NA1/BR1 da 404, así que `!match` contestaba
            # "no está en partida" con el jugador jugando.
            partida, estado = await get_active_game(
                cuenta.puuid, platform=getattr(cuenta, "platform", None)
            )
        except Exception as exc:
            log.debug("Fallo consultando %s: %s", cuenta.puuid[:12], exc)
            return cuenta, None, 0
    return cuenta, partida, estado


async def _cuerpo_match(res: Respuesta, nombre: str) -> None:
    """Cuerpo compartido por `!match` y `/match`."""
    _ = tr(res.guild_id)
    idioma = idioma_de(res.guild_id)

    if not nombre:
        await res.error(_("match.falta_nombre"))
        return

    jugador = _buscar_jugador(nombre)
    if not jugador:
        await res.error(_("match.no_encontrado", nombre=nombre))
        return

    await res.esperando(_("match.buscando", nombre=jugador.name))

    # Todas las cuentas a la vez: antes se recorrían en serie con hasta 8
    # reintentos y `sleep(2)` cada una.
    semaforo = asyncio.Semaphore(config.TRACKER_CONCURRENCY)
    resultados = await asyncio.gather(
        *[_partida_de_cuenta(c, semaforo) for c in jugador.accounts],
        return_exceptions=True,
    )

    limitado = False
    for resultado in resultados:
        if isinstance(resultado, Exception):
            log.debug("Cuenta con excepción: %s", resultado)
            continue
        cuenta, partida, estado = resultado
        if estado == 429:
            limitado = True
        if not partida:
            continue

        try:
            match = SoloQMatch.from_riot_game_data(partida)
            await match.load_ranks()
        except Exception:
            log.exception("Error procesando la partida activa de %s", jugador.name)
            await res.error(_("match.fallo_embed"))
            return

        puuid_to_player = {a.puuid: jugador for a in jugador.accounts if a.puuid}
        embed, files = await create_match_embed(
            match, puuid_to_player, _mapa_de_rangos(match), idioma=idioma
        )
        cuenta_txt = (
            f"{cuenta.riot_id.get('game_name','?')}#{cuenta.riot_id.get('tag_line','?')}"
        )
        embed.title = _("match.titulo", nombre=jugador.name, cuenta=cuenta_txt)
        await res.send(embed=embed, files=files)
        return

    # Ninguna cuenta dio partida. Si hubo rate limit, se intenta con la caché.
    if limitado:
        await _responder_desde_cache(res, jugador)
        return

    await res.error(_("match.sin_partida", nombre=jugador.name))


async def _responder_desde_cache(res: Respuesta, jugador) -> None:
    """Respuesta de respaldo cuando Riot limita: la última partida cacheada."""
    _ = tr(res.guild_id)
    idioma = idioma_de(res.guild_id)

    entrada = None
    for cuenta in jugador.accounts:
        if cuenta.puuid:
            entrada = get_active_game_cache(cuenta.puuid)
            if entrada:
                break
    if not entrada:
        entrada = get_active_game_cache_by_name(jugador.name)
        if entrada:
            log.debug("Recuperado desde caché por nombre: %s", jugador.name)

    if not entrada:
        await res.error(_("match.sin_cache"))
        return

    try:
        match = SoloQMatch.from_riot_game_data(entrada["active_game"])
    except Exception:
        log.exception("Error leyendo la partida cacheada de %s", jugador.name)
        await res.error(_("match.cache_ilegible"))
        return

    for part in match.participants:
        if getattr(part, "puuid", None) and getattr(part, "rank", None):
            save_rank_data(part)

    # Mismo reloj que `/live` y el embed: antes se sumaba a mano `game_length`
    # (el reloj del espectador) al tiempo en caché, sin contar el delay.
    reloj = desde_cache(entrada)
    match.game_length = reloj.visible

    puuid_to_player = {a.puuid: jugador for a in jugador.accounts if a.puuid}
    embed, files = await create_match_embed(
        match, puuid_to_player, _mapa_de_rangos(match), idioma=idioma
    )
    embed.add_field(
        name=_("match.campo_cache"),
        value=_("match.valor_cache", tiempo=reloj.texto_embed(idioma)),
        inline=False,
    )
    embed.title = _("match.titulo_cache", nombre=jugador.name)
    await res.send(embed=embed, files=files)

    for cuenta in jugador.accounts:
        if cuenta.puuid:
            add_to_retry_queue(cuenta.puuid, getattr(cuenta, "platform", None))
            break


def register_match_command(bot: commands.Bot):
    dual_texto(
        bot,
        "match",
        "cmd.match.desc",
        _cuerpo_match,
        arg_nombre="cmd.match.arg",
        arg_desc="cmd.match.arg_desc",
    )

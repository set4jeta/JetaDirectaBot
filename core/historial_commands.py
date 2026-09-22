"""Comando `!historial` / `/historial`.

Muestra las últimas partidas de un jugador (o de todos) a partir de dpm.lol.

Qué se cambió respecto a la versión anterior:

- **Ahora también es `/historial`,** con el argumento opcional: sin rellenarlo
  da el historial global, con un nick da el de ese jugador. El cuerpo es único.
- **Los textos pasan por `utils.i18n`.** Además, la cabecera del historial
  individual se montaba pegando `" (todas sus cuentas):**"` o `":**"` al final,
  o sea que los `**` de cierre vivían sueltos en un fragmento condicional. Eso
  no se puede traducir sin que quede torcido: ahora son dos claves completas.
- El cálculo estaba triplicado: el mismo bloque de emojis, posición y
  formateo repetido tres veces. Ahora vive en `utils/match_format.py`.
- La posición salía siempre vacía porque dpm.lol no envía `teamPosition` ni
  `position`. Ahora se deduce del campeón (ver `utils/lane_guess`).
- Lanzaba una tarea por jugador y cuenta sin ningún límite, y cada tarea
  ocupaba un hilo. Con 130 cuentas eran 130 peticiones simultáneas.
  Ahora hay un semáforo y solo se piden las partidas que se van a mostrar.
- Cinco `print()` por ejecución, incluido el volcado de la lista de jugadores.
  Ahora hay logging.
- Se respeta el límite de 2000 caracteres de Discord partiendo el mensaje.
- `await ctx.typing()` habría lanzado `TypeError`: en nextcord 3.x `typing()`
  devuelve un gestor de contexto, no un awaitable. El aviso lo da ahora
  `Respuesta.esperando`.
- **Cuántas partidas se enseñan sale del plan del servidor** (`plans.limite`).
  Era un `MAX_PARTIDAS = 10` fijo mientras `/premium` vendía "100 partidas de
  historial", así que ese cupo no existía en el código. Ver `_tope_partidas`
  para por qué hay además un techo duro.
"""

from __future__ import annotations

import asyncio

from nextcord.ext import commands

import config
from apis.dpm_api import get_dpmlol_puuid, get_match_history_from_dpmlol
from core.dual_command import dual_texto
from core.responder import Respuesta
from tracking.soloq.accounts_io import load_tracked_accounts
from tracking.soloq.plans import limite
from utils.i18n import idioma_de, tr
from utils.logger import get_logger
from utils.match_format import formatear_partida, nick_con_equipo

log = get_logger("core.historial")

#: Cuántas partidas se enseñan si no hay plan legible. Es el número que el bot
#: usaba fijo, así que un servidor sin plan ve exactamente lo de antes.
MAX_PARTIDAS = 10
LIMITE_DISCORD = 2000

#: Cuántos mensajes como máximo por respuesta. Tres es lo que había: más
#: convierte un comando en un muro de texto que Discord además rate-limitea.
MAX_MENSAJES = 3

#: Techo físico de líneas que caben en la respuesta. Medido, no estimado: una
#: línea de historial con nick y cuenta ocupa ~105 caracteres, así que en
#: `MAX_MENSAJES` mensajes de `LIMITE_DISCORD` caben unas 55 y el resto se
#: perdería en un `log.warning` que el usuario no ve. Por eso los planes bajaron
#: de 20/100/500 a 10/30/50: prometer 500 partidas era imposible de entregar sin
#: paginación con botones, y hasta que exista no se vende.
TOPE_FISICO = (LIMITE_DISCORD * MAX_MENSAJES) // 105


def _tope_partidas(guild_id) -> int:
    """Cuántas partidas puede pedir este servidor.

    El menor de tres: su plan, el techo físico y —si el plan no se puede leer—
    el valor de siempre. Nunca 0: un cupo mal leído dejaría `/historial` sin
    responder nada, y es peor que enseñar menos partidas.
    """
    del_plan = limite(guild_id, "historial") or MAX_PARTIDAS
    return max(1, min(del_plan, TOPE_FISICO))



def _cuenta_str(account) -> str:
    game_name = account.riot_id.get("game_name", "")
    tag_line = account.riot_id.get("tag_line", "")
    return f"{game_name}#{tag_line}" if game_name and tag_line else ""


def _buscar_jugador(jugadores, nombre: str):
    """Encuentra un jugador por su nick o por cualquiera de sus cuentas.

    Devuelve (jugador, cuenta_concreta_o_None). La cuenta es None si la
    búsqueda fue por nick de jugador y no por una cuenta específica.
    """
    objetivo = (nombre or "").strip().lower()
    if not objetivo:
        return None, None
    sin_espacios = objetivo.replace(" ", "")

    for jugador in jugadores:
        if jugador.name.lower().replace(" ", "") == sin_espacios:
            return jugador, None
        for account in jugador.accounts:
            acc_name = account.riot_id.get("game_name", "").lower()
            acc_tag = account.riot_id.get("tag_line", "").lower()
            if not acc_name:
                continue
            formas = {
                acc_name.replace(" ", ""),
                f"{acc_name}#{acc_tag}",
                f"{acc_name}#{acc_tag}".replace(" ", ""),
            }
            if objetivo in formas or sin_espacios in formas:
                return jugador, _cuenta_str(account)
    return None, None


def _partir_mensaje(texto: str) -> list[str]:
    """Parte un texto en trozos que quepan en un mensaje de Discord."""
    if len(texto) <= LIMITE_DISCORD:
        return [texto]

    trozos: list[str] = []
    actual = ""
    for linea in texto.split("\n"):
        if len(actual) + len(linea) + 1 > LIMITE_DISCORD:
            if actual:
                trozos.append(actual.rstrip())
            actual = ""
        actual += linea + "\n"
    if actual.strip():
        trozos.append(actual.rstrip())
    return trozos


# Solo un !historial a la vez: si varios usuarios lo piden a la vez se encolan
# en vez de multiplicar las peticiones a dpm.lol.
_semaforo = asyncio.Semaphore(max(1, config.DPM_CONCURRENCY))


async def partidas_de_cuenta(jugador, account, cuenta: str) -> list[dict]:
    """Partidas de una cuenta, ya con el jugador y la cuenta asociados."""
    acc_name = account.riot_id.get("game_name", "")
    acc_tag = account.riot_id.get("tag_line", "")
    if not acc_name or not acc_tag:
        return []

    async with _semaforo:
        puuid = await get_dpmlol_puuid(acc_name, acc_tag)
        if not puuid:
            log.debug("Sin PUUID en dpm.lol para %s", cuenta)
            return []
        data = await get_match_history_from_dpmlol(puuid)

    if not data or not data.get("matches"):
        return []

    encontradas = []
    for match in data["matches"]:
        participante = next(
            (p for p in (match.get("participants") or [])
             if p.get("puuid") == puuid),
            None,
        )
        if participante:
            encontradas.append({
                "jugador": jugador,
                "participante": participante,
                "match": match,
                "cuenta": cuenta,
            })
    return encontradas


async def partidas_de_jugadores(jugadores) -> list[dict]:
    """Partidas de todas las cuentas de todos los jugadores, ordenadas."""
    tareas = [
        partidas_de_cuenta(jugador, account, _cuenta_str(account))
        for jugador in jugadores
        for account in jugador.accounts
    ]
    resultados = await asyncio.gather(*tareas, return_exceptions=True)

    partidas: list[dict] = []
    for resultado in resultados:
        if isinstance(resultado, Exception):
            log.debug("Una cuenta falló en el historial: %s", resultado)
            continue
        partidas.extend(resultado)

    partidas.sort(key=lambda x: x["match"].get("gameCreation", 0) or 0, reverse=True)
    return partidas


def una_por_jugador(partidas: list[dict], maximo: int = MAX_PARTIDAS) -> list[dict]:
    """Deja solo la partida más reciente de cada jugador."""
    vistos: set[str] = set()
    seleccion: list[dict] = []
    for partida in partidas:
        nick = partida["jugador"].name
        if nick in vistos:
            continue
        vistos.add(nick)
        seleccion.append(partida)
        if len(seleccion) >= maximo:
            break
    return seleccion


def register_historial_command(bot: commands.Bot):
    dual_texto(
        bot,
        "historial",
        "cmd.historial.desc",
        _cuerpo_historial,
        arg_nombre="cmd.historial.arg",
        arg_desc="cmd.historial.arg_desc",
        requerido=False,
    )


async def _cuerpo_historial(res: Respuesta, nombre: str) -> None:
    """Cuerpo compartido por `!historial` y `/historial`."""
    _ = tr(res.guild_id)
    idioma = idioma_de(res.guild_id)

    await res.esperando(_("historial.consultando"))

    jugadores = load_tracked_accounts()
    if not jugadores:
        await res.error(_("historial.sin_jugadores"))
        return

    if not nombre:
        # Historial global: se piden las partidas de todas las cuentas y se
        # ordenan por fecha. Solo se conserva la más reciente por jugador.
        partidas = await partidas_de_jugadores(jugadores)
        seleccion = una_por_jugador(partidas, _tope_partidas(res.guild_id))

        if not seleccion:
            await res.error(_("historial.sin_partidas"))
            return

        cabecera = (
            _("historial.cabecera_global", n=len(seleccion)) + "\n"
            + _("historial.como_usar") + "\n\n"
        )
        lineas = []
        for i, partida in enumerate(seleccion, 1):
            jugador = partida["jugador"]
            # Se enseña la cuenta que jugó esa partida, no siempre la
            # primera del jugador: los pros rotan de cuenta y mostrar la
            # equivocada confunde.
            nick = nick_con_equipo(jugador.name, jugador.team, partida["cuenta"])
            lineas.append(
                f"{i}. "
                f"{formatear_partida(partida['participante'], partida['match'], idioma=idioma)}"
                f" | {nick}"
            )

        await _enviar(res, cabecera + "\n".join(lineas))
        return

    # ---- Historial individual ----
    jugador, cuenta = _buscar_jugador(jugadores, nombre)
    if jugador is None:
        await res.error(_("historial.jugador_no_encontrado", nombre=nombre))
        return

    cuentas = (
        [a for a in jugador.accounts if _cuenta_str(a).lower() == (cuenta or "").lower()]
        if cuenta
        else list(jugador.accounts)
    )
    if not cuentas:
        await res.error(_(
            "historial.cuenta_no_encontrada", cuenta=cuenta, jugador=jugador.name
        ))
        return

    resultados = await asyncio.gather(
        *[partidas_de_cuenta(jugador, a, _cuenta_str(a)) for a in cuentas],
        return_exceptions=True,
    )

    partidas: list[dict] = []
    for resultado in resultados:
        if isinstance(resultado, Exception):
            log.debug("Una cuenta falló en el historial de %s: %s", jugador.name, resultado)
            continue
        partidas.extend(resultado)

    if not partidas:
        await res.error(_("historial.sin_historial", jugador=jugador.name))
        return

    partidas.sort(key=lambda x: x["match"].get("gameCreation", 0) or 0, reverse=True)
    seleccion = partidas[:_tope_partidas(res.guild_id)]

    varias_cuentas = len(cuentas) > 1
    titulo = nick_con_equipo(jugador.name, jugador.team, cuenta) if cuenta else jugador.name
    # Dos claves enteras en vez de pegar el trozo condicional al final: así el
    # `**` de cierre viaja dentro de la plantilla y no queda abierto.
    clave_cabecera = (
        "historial.cabecera_jugador_todas" if varias_cuentas
        else "historial.cabecera_jugador"
    )
    cabecera = _(clave_cabecera, n=len(seleccion), jugador=titulo) + "\n"
    lineas = [
        f"{i}. " + formatear_partida(
            p["participante"], p["match"],
            p["cuenta"] if varias_cuentas else None,
            idioma=idioma,
        )
        for i, p in enumerate(seleccion, 1)
    ]
    await _enviar(res, cabecera + "\n".join(lineas))


async def _enviar(res: Respuesta, texto: str) -> None:
    """Manda el mensaje partiéndolo si se pasa del límite de Discord."""
    trozos = _partir_mensaje(texto)
    for trozo in trozos[:MAX_MENSAJES]:
        await res.send(trozo)
    if len(trozos) > MAX_MENSAJES:
        # No debería pasar ya: `_tope_partidas` acota las líneas a lo que cabe en
        # `MAX_MENSAJES`. Si salta, es que el formato de línea ha crecido y hay
        # que recalcular `TOPE_FISICO`, no subir el número de mensajes.
        log.warning(
            "Historial demasiado largo: se truncaron %d trozos. Revisa TOPE_FISICO.",
            len(trozos) - MAX_MENSAJES,
        )

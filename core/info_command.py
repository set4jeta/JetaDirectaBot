"""Comando `!info` / `/info`: ficha de un jugador o de una cuenta.

Qué se cambió
-------------
0. **Ahora también es `/info jugador:Elyoya`.**
1. **Los cinco `print()` pasan a logging.** Volcaban el nombre buscado y el
   resultado a stdout en cada uso, que es parte del ruido que ensuciaba la
   consola.
2. **El `except Exception` genérico dejaba de decir qué había fallado.** Ahora
   se registra la traza completa con `log.exception` y al usuario se le dice qué
   pasó, no solo "ocurrió un error".
3. **`nombre` ya no es obligatorio a nivel de firma.** Antes `!info` a secas
   provocaba un `MissingRequiredArgument` que nextcord convertía en un error
   silencioso en consola y ninguna respuesta en Discord. Ahora responde con la
   ayuda del comando.
4. **Los textos pasan por `utils.i18n`,** los del comando y los de la ficha
   (`ui/player_info_embed.py`), que recibe el idioma. Los nombres de campeón, de
   equipo y de liga siguen tal cual: son nombres propios.
"""

from __future__ import annotations

from nextcord.ext import commands

from core.dual_command import dual_texto
from core.responder import Respuesta
from tracking.soloq.infoplayers_search import buscar_jugador_o_cuenta
from ui.player_info_embed import crear_embed_infoplayer
from utils.i18n import idioma_de, tr
from utils.logger import get_logger

log = get_logger("core.info")


async def _cuerpo_info(res: Respuesta, nombre: str) -> None:
    """Cuerpo compartido por `!info` y `/info`."""
    _ = tr(res.guild_id)
    idioma = idioma_de(res.guild_id)

    if not nombre:
        await res.error(_("info.falta_nombre"))
        return

    await res.esperando(_("info.buscando", nombre=nombre))

    log.debug("Buscando info en EU para: %r", nombre)
    res_busqueda = buscar_jugador_o_cuenta(nombre)
    if not res_busqueda:
        await res.error(_("info.no_encontrado", nombre=nombre))
        return

    jugador = res_busqueda["jugador"]
    cuentas = res_busqueda["cuentas"]
    campeones_recientes = res_busqueda.get("campeones_recientes", [])
    estadisticas_2_semanas = res_busqueda.get("estadisticas_2_semanas", {})

    log.debug("Encontrado: %s", jugador.get("nombre") or jugador.get("name"))
    try:
        embed, archivo_logo = crear_embed_infoplayer(
            jugador, cuentas, campeones_recientes, estadisticas_2_semanas,
            idioma=idioma,
        )
    except Exception:
        log.exception("Error generando el embed de %s", nombre)
        await res.error(_("info.fallo_embed"))
        return

    if not embed:
        await res.error(_("info.sin_datos", nombre=nombre))
        return

    if archivo_logo:
        await res.send(embed=embed, file=archivo_logo)
    else:
        await res.send(embed=embed)


def register_info_command(bot: commands.Bot):
    dual_texto(
        bot,
        "info",
        "cmd.info.desc",
        _cuerpo_info,
        arg_nombre="cmd.info.arg",
        arg_desc="cmd.info.arg_desc",
    )

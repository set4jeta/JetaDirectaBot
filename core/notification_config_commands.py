"""Comandos de configuración de notificaciones de SoloQ.

`/setchannel`, `/unsubscribe` y `/canales`, con sus formas `!` equivalentes.

Qué se cambió
-------------
0. **Ahora también son slash commands.**
1. **Ahora piden permiso de administrador.** El `!help` decía "(solo admin)"
   pero no había ninguna comprobación: cualquiera del servidor podía redirigir
   las notificaciones del bot a otro canal. En la forma slash se declara con
   `default_member_permissions`, que hace que Discord ni le muestre el comando a
   quien no puede usarlo; el cuerpo lo comprueba igual con `res.es_admin()`,
   porque en la forma de prefijo Discord no filtra nada.
2. **Se avisa si al bot le faltan permisos en el canal.** Antes se guardaba el
   canal igual y las notificaciones fallaban en silencio cada 30 segundos.
3. **`/setchannel` suma canales en vez de sustituir el anterior.** El cupo de
   canales del plan no existía en el código: `notify_config.json` guardaba uno
   por servidor, así que `/premium` vendía "3 canales" y el bot solo sabía
   mandar a uno. Ahora se añaden hasta el cupo del plan, y por eso hace falta
   `/canales` para ver y quitar los que hay: con un solo canal bastaba volver a
   ejecutar `/setchannel` en otro sitio, con varios hay que poder quitarlos.

Por qué `/unsubscribe` los quita todos
--------------------------------------
Es lo que hacía antes y lo que espera quien lo escribe: "no quiero más avisos".
Quitar solo el canal actual dejaría al servidor recibiendo avisos en los otros
después de haber pedido explícitamente que paren.
"""

from __future__ import annotations

import nextcord
from nextcord.ext import commands

from core.dual_command import PERMISO_ADMIN, dual
from core.responder import Respuesta
from tracking.soloq.channel_config import (
    agregar_canal,
    canales_de,
    canales_guardados,
    quitar_canal,
    quitar_todos,
)
from tracking.soloq.plans import limite
from utils.i18n import tr
from utils.logger import get_logger

log = get_logger("core.notif_config")


def _permisos_que_faltan(res: Respuesta, _) -> list[str]:
    """Permisos del bot que faltan en el canal actual, ya traducidos."""
    canal = res.canal
    if not isinstance(canal, nextcord.TextChannel) or res.guild is None:
        return []
    permisos = canal.permissions_for(res.guild.me)
    return [
        nombre
        for nombre, tiene in (
            (_("permisos.enviar_mensajes"), permisos.send_messages),
            (_("permisos.insertar_enlaces"), permisos.embed_links),
            (_("permisos.adjuntar_archivos"), permisos.attach_files),
        )
        if not tiene
    ]


async def _cuerpo_setchannel(res: Respuesta) -> None:
    _ = tr(res.guild_id)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(
            _("error.solo_admin")
            + ("\n" + _("setchannel.solo_admin_extra"))
        )
        return

    canal = res.canal
    resultado, tope = agregar_canal(res.guild_id, canal.id)

    mencion = (
        canal.mention
        if isinstance(canal, nextcord.TextChannel)
        else _("setchannel.este_canal")
    )

    if resultado == "repetido":
        await res.send(_("setchannel.ya_estaba", canal=mencion))
        return

    if resultado == "cupo":
        # El mensaje dice el cupo y cómo liberar hueco, no solo que no cabe: sin
        # `/canales quitar` el usuario se quedaría sin forma de arreglarlo.
        await res.error(_("setchannel.cupo", n=tope, canales=_lista(canales_de(res.guild_id))))
        return

    aviso = ""
    faltan = _permisos_que_faltan(res, _)
    if faltan:
        aviso = _(
            "setchannel.sin_permisos_canal",
            permisos=", ".join(f"**{p}**" for p in faltan),
        )

    usados = len(canales_de(res.guild_id))
    if tope > 1:
        aviso += "\n" + _("setchannel.cuenta", usados=usados, tope=tope)
    await res.send(_("setchannel.ok", canal=mencion, aviso=aviso))


async def _cuerpo_unsubscribe(res: Respuesta) -> None:
    _ = tr(res.guild_id)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(_("error.solo_admin"))
        return

    habia = quitar_todos(res.guild_id)
    if not habia:
        await res.send(_("unsubscribe.no_habia"))
        return
    await res.send(_("unsubscribe.ok"))


def _lista(canales: list[int]) -> str:
    """`[123, 456]` -> `"<#123>, <#456>"`. Discord resuelve la mención sola."""
    return ", ".join(f"<#{c}>" for c in canales) or "—"


async def _cuerpo_canales(res: Respuesta) -> None:
    """Qué canales tiene el servidor, y quita el actual si se pide."""
    _ = tr(res.guild_id)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return

    activos = canales_de(res.guild_id)
    guardados = canales_guardados(res.guild_id)
    tope = limite(res.guild_id, "canales")

    lineas = [
        f"**{_('canales.titulo')}**",
        _("canales.activos", canales=_lista(activos), n=len(activos), tope=tope),
    ]

    # Solo se mencionan los inactivos si existen: es el caso de un servidor que
    # bajó de plan, y decirlo evita que parezca que se le han borrado.
    inactivos = [c for c in guardados if c not in activos]
    if inactivos:
        lineas.append(_("canales.inactivos", canales=_lista(inactivos)))

    lineas.append(_("canales.como_usar"))
    await res.send("\n".join(lineas))


async def _cuerpo_quitarcanal(res: Respuesta) -> None:
    _ = tr(res.guild_id)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(_("error.solo_admin"))
        return

    canal = res.canal
    mencion = (
        canal.mention
        if isinstance(canal, nextcord.TextChannel)
        else _("setchannel.este_canal")
    )
    if quitar_canal(res.guild_id, canal.id):
        await res.send(_("canales.quitado", canal=mencion))
    else:
        await res.send(_("canales.no_estaba", canal=mencion))


def register_notification_config_commands(bot: commands.Bot):
    dual(
        bot,
        "setchannel",
        "cmd.setchannel.desc",
        _cuerpo_setchannel,
        permiso=PERMISO_ADMIN,
    )
    dual(
        bot,
        "unsubscribe",
        "cmd.unsubscribe.desc",
        _cuerpo_unsubscribe,
        permiso=PERMISO_ADMIN,
    )
    dual(
        bot,
        "canales",
        "cmd.canales.desc",
        _cuerpo_canales,
    )
    dual(
        bot,
        "quitarcanal",
        "cmd.quitarcanal.desc",
        _cuerpo_quitarcanal,
        permiso=PERMISO_ADMIN,
    )

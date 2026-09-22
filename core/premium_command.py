"""`/premium` — qué cupos tiene el servidor y cómo subirlos.

Por qué este comando existe y por qué dice lo que dice
-----------------------------------------------------
Es el único sitio donde el bot habla de dinero, así que es donde se concentra
todo el riesgo de que el usuario entienda mal el producto. La política de Riot
exige un tier gratuito y que lo que se cobre sea transformativo; el interés del
proyecto exige que nadie desinstale el bot creyendo que hay que pagar para que
funcione. Las dos cosas apuntan al mismo texto: **primero se dice qué es gratis,
y solo después qué se puede comprar.**

Por eso el orden del embed no es negociable:

1. lo que es gratis y siempre lo será (el aviso de partida, que es la función
   principal);
2. el plan actual del servidor y su consumo real;
3. la tabla de planes;
4. cómo mejorar, y solo con los enlaces que existen de verdad.

Lo que este comando **no** hace
-------------------------------
No cobra. No hay pasarela, ni `entitlements`, ni verificación de pago. Mientras
no haya nada de eso, decirlo explícitamente (`premium.sin_pasarela`) es más
honesto que enseñar un botón de compra que no lleva a ninguna parte, y evita el
peor resultado posible: alguien que paga y no recibe nada.

Cuando se conecte Discord Premium Apps, el punto de entrada es
`tracking/soloq/plans.py:asignar_plan`, y este comando no tiene que cambiar.
"""

from __future__ import annotations

import nextcord
from nextcord.ext import commands

from core.dual_command import dual
from core.responder import Respuesta
from tracking.soloq.leagues import MAX_LIGAS_POR_SERVIDOR, ligas_de
from tracking.soloq.plans import ORDEN, PLANES, plan_de
from utils.branding import BOT_NOMBRE, enlaces, sellar_embed
from utils.i18n import idioma_de, tr
from utils.logger import get_logger

log = get_logger("core.premium")

COLOR = 0xF1C40F


def _nombre(plan, _) -> str:
    """Nombre del plan traducido, con el del catálogo de planes como respaldo.

    `plans.py` no importa i18n a propósito: es el módulo que consulta el tracker
    en caliente y no debe arrastrar el catálogo. Así que la traducción del
    nombre se resuelve aquí, y si algún día se añade un plan sin clave en el
    catálogo sale su nombre interno en vez de la clave cruda.
    """
    traducido = _(f"premium.plan_{plan.codigo}")
    return plan.nombre if traducido == f"premium.plan_{plan.codigo}" else traducido


def _linea_cupos(plan, _) -> str:
    """Los cuatro cupos de un plan, en una línea por cupo."""
    return "\n".join([
        f"· {_('premium.cupo_ligas', n=plan.ligas)}",
        f"· {_('premium.cupo_canales', n=plan.canales)}",
        f"· {_('premium.cupo_jugadores', n=plan.jugadores_propios)}",
        f"· {_('premium.cupo_historial', n=plan.historial)}",
    ])


def construir_embed(guild_id: int | None, ligas_usadas: int = 0) -> nextcord.Embed:
    """El embed de `/premium`. Aparte para poder comprobarlo sin Discord."""
    idioma = idioma_de(guild_id)

    def _(clave: str, **kw) -> str:
        from utils.i18n import t
        return t(clave, idioma, **kw)

    actual = plan_de(guild_id)

    embed = nextcord.Embed(
        title=_("premium.titulo", bot=BOT_NOMBRE),
        description=_("premium.intro"),
        color=COLOR,
    )

    embed.add_field(
        name=_("premium.tu_plan", plan=_nombre(actual, _)),
        value=_(
            "premium.uso",
            ligas=ligas_usadas,
            tope=min(actual.ligas, MAX_LIGAS_POR_SERVIDOR),
        ),
        inline=False,
    )

    for codigo in ORDEN:
        plan = PLANES[codigo]
        precio = (
            _("premium.gratis_etiqueta")
            if plan.gratis
            else _("premium.precio_mes", precio=f"{plan.precio:.2f}")
        )
        # El plan activo se marca para que no haya que comparar a ojo cuál es.
        marca = " ✅" if plan.codigo == actual.codigo else ""
        embed.add_field(
            name=f"{_nombre(plan, _)} — {precio}{marca}",
            value=_linea_cupos(plan, _),
            inline=True,
        )

    lineas = enlaces(idioma)
    embed.add_field(
        name=_("premium.como"),
        value="\n".join([_("premium.sin_pasarela"), ""] + lineas)
        if lineas
        else _("premium.sin_enlaces"),
        inline=False,
    )

    # Riot prohíbe expresamente apuestas y ventajas en juego. Decirlo aquí, en
    # el comando que habla de dinero, es donde importa.
    embed.add_field(name="\u200b", value=f"_{_('premium.legal')}_", inline=False)

    sellar_embed(embed, idioma)
    return embed


def construir_texto(guild_id: int | None, ligas_usadas: int = 0) -> str:
    """Misma información en texto plano, para cuando no se pueden usar embeds."""
    idioma = idioma_de(guild_id)

    def _(clave: str, **kw) -> str:
        from utils.i18n import t
        return t(clave, idioma, **kw)

    actual = plan_de(guild_id)
    partes = [
        f"**{_('premium.titulo', bot=BOT_NOMBRE)}**",
        _("premium.intro"),
        "",
        _("premium.tu_plan", plan=_nombre(actual, _)),
        _(
            "premium.uso",
            ligas=ligas_usadas,
            tope=min(actual.ligas, MAX_LIGAS_POR_SERVIDOR),
        ),
        "",
    ]
    for codigo in ORDEN:
        plan = PLANES[codigo]
        precio = (
            _("premium.gratis_etiqueta")
            if plan.gratis
            else _("premium.precio_mes", precio=f"{plan.precio:.2f}")
        )
        marca = " ✅" if plan.codigo == actual.codigo else ""
        partes.append(f"**{_nombre(plan, _)} — {precio}{marca}**")
        partes.append(_linea_cupos(plan, _))
        partes.append("")

    partes.append(f"**{_('premium.como')}**")
    lineas = enlaces(idioma)
    if lineas:
        partes.append(_("premium.sin_pasarela"))
        partes.extend(lineas)
    else:
        partes.append(_("premium.sin_enlaces"))
    partes.append(f"\n_{_('premium.legal')}_")
    return "\n".join(partes)


async def _cuerpo_premium(res: Respuesta) -> None:
    _ = tr(res.guild_id)
    # En DM no hay plan de servidor, pero el comando sigue siendo útil: se
    # enseña la tabla con el plan gratuito, que es lo que aplica.
    usadas = len(ligas_de(res.guild_id)) if res.guild_id else 0

    try:
        await res.send(embed=construir_embed(res.guild_id, usadas))
        return
    except nextcord.Forbidden:
        log.info("Sin permiso para embeds en %s; mando /premium en texto.", res.canal_id)
    except nextcord.HTTPException as exc:
        log.warning("Fallo mandando el embed de /premium: %s", exc)

    await res.enviar_partido(construir_texto(res.guild_id, usadas))


def register_premium_command(bot: commands.Bot) -> None:
    dual(
        bot,
        "premium",
        "cmd.premium.desc",
        _cuerpo_premium,
    )

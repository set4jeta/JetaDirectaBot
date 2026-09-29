"""Configuración de los canales de avisos: `/subscribe`, `/unsubscribe`, `/channels` y `/mute`.

Qué se cambió el 22-09-2026
---------------------------
Eran seis comandos (`setchannel`, `quitarcanal`, `canales`, `unsubscribe` y los
dos de esports) con nombres mezclados en los dos idiomas y tres de ellos
compuestos. El dueño lo rechazó: *«que se entienda su significado de una
palabra… si es esports es solo esports»*. Ahora son **cuatro, de una palabra**, y
lo que distinguía SoloQ de esports se expresa con la opción `type` de lista
cerrada:

| Antes | Ahora |
|---|---|
| `setchannel` | `/subscribe` (o `/subscribe type: esports`) |
| `quitarcanal` | `/unsubscribe` |
| `unsubscribe` | `/mute` |
| `canales` | `/channels` |
| `setlivechannel` | `/subscribe type: esports` |
| `removelivechannel` | `/unsubscribe type: esports` (o `/mute type: esports`) |

Seis funciones, cuatro nombres: la diferencia no era del comando, era de **qué**
avisos. Y de paso desaparece la asimetría que hacía falta explicar —SoloQ tenía
una lista de canales con cupo por plan y esports un canal único— sin cambiarla:
sigue siendo así, pero ahora se ve en el mismo sitio.

Por qué están aquí los de esports
---------------------------------
Vivían en `esports_extension/bot/commands.py` porque el tracker de esports es una
extensión. Pero configurar canales es **una** cosa, no dos, y tener la mitad en
cada sitio obligaba a mantener dos veces los mismos permisos, los mismos avisos y
dos nombres distintos para lo mismo. Aquí están los cuatro juntos; la extensión
se queda con lo suyo (`/esports` y `/schedule`).

Lo que no se cambió
-------------------
- `/subscribe` **suma** canales (hasta el cupo del plan) en vez de sustituir: con
  varios canales hay que poder verlos y quitarlos, y de ahí `/channels`.
- `/mute` apaga **todo** el servidor. Es lo que se espera al escribir "no quiero
  más avisos": quitar solo el canal actual dejaría a los demás recibiendo.
- Con `type: esports`, `/unsubscribe` quita el canal **si es el de esports**, y
  `/mute` lo apaga sin preguntar. Con un solo canal la diferencia es pequeña, pero
  es la que hace que el comando diga la verdad.
"""

from __future__ import annotations

import nextcord
from nextcord.ext import commands

from core.dual_command import PERMISO_ADMIN, slash, slash_opciones
from core.responder import Respuesta
from esports_extension.services.storage import (
    load_notification_channel,
    remove_notification_channel,
    save_notification_channel,
)
from tracking.soloq.channel_config import (
    agregar_canal,
    canales_de,
    canales_guardados,
    quitar_canal,
    quitar_todos,
)
from tracking.soloq.channel_targets import (
    ESPORTS,
    SOLOQ,
    TIPOS,
    limpiar,
    poner,
    todos,
)
from tracking.soloq.leagues import (
    establecer_ligas,
    ligas_de,
    ligas_guardadas,
    resolver,
)
from tracking.soloq.plans import limite
from tracking.soloq.roster_lookup import (
    equipo_rastreado,
    liga_principal_de_equipo,
    pro_rastreado,
)
from utils.i18n import tr
from utils.logger import get_logger

log = get_logger("core.notif_config")

#: Los dos tipos de aviso. Son las opciones del argumento `type`, y por eso son
#: cortas y en minúscula: son etiquetas, no prosa, y valen igual en los dos
#: idiomas (no se traducen).
SOLOQ = "soloq"
ESPORTS = "esports"
TIPOS = (SOLOQ, ESPORTS)


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


def _mencion(res: Respuesta, _) -> str:
    canal = res.canal
    return (
        canal.mention
        if isinstance(canal, nextcord.TextChannel)
        else _("setchannel.este_canal")
    )


def _aviso_permisos(res: Respuesta, _) -> str:
    faltan = _permisos_que_faltan(res, _)
    if not faltan:
        return ""
    return _("setchannel.sin_permisos_canal", permisos=", ".join(f"**{p}**" for p in faltan))


def _lista(canales: list[int]) -> str:
    """`[123, 456]` -> `"<#123>, <#456>"`. Discord resuelve la mención sola."""
    return ", ".join(f"<#{c}>" for c in canales) or "—"


# ---------------------------------------------------------------------- #
# /subscribe
# ---------------------------------------------------------------------- #

#: Cómo se llama cada tipo para leerlo. Los valores (`soloq`, `esports`) son
#: identificadores y en un mensaje se ven como una constante; estos son su nombre.
NOMBRE_TIPO = {SOLOQ: "SoloQ", ESPORTS: "Esports"}


def _resolver_objetivo(texto: str) -> tuple[str, str, str] | None:
    """Lo que escribió el usuario -> `(clave, etiqueta, liga)`.

    `clave` es lo que se guarda y con lo que compara el reparto; `etiqueta` es lo
    que se enseña; `liga` es a la que pertenece, para poder meterla en el barrido.

    El orden es el mismo que usa `/track` —cuenta, liga, pro, equipo— y por el
    mismo motivo: un Riot ID lleva `#` y ninguna liga lo tiene, y un código de liga
    no es el nick de nadie. `None` si no se reconoce nada.
    """
    texto = (texto or "").strip()
    if not texto:
        return None

    # Una cuenta suelta no pertenece a ninguna liga conocida, así que no hay nada
    # que meter en el barrido: se guarda y ya.
    if "#" in texto:
        return (texto, texto, "")

    liga = resolver(texto)
    if liga is not None:
        return (liga.codigo, liga.nombre, liga.codigo)

    jugador = pro_rastreado(texto)
    if jugador is not None:
        nombre = getattr(jugador, "name", texto) or texto
        return (nombre, nombre, (getattr(jugador, "league", "") or "").lower())

    equipo = equipo_rastreado(texto)
    if equipo is not None:
        # La liga del equipo se cuenta aparte: un equipo aparece en el roster en
        # su liga y en los eventos internacionales, y quedarse con la primera
        # coincidencia metía el MSI en el barrido en vez de la LCK.
        liga_equipo = liga_principal_de_equipo(equipo[0]) or (equipo[2] or "").lower()
        return (equipo[0], equipo[1], liga_equipo)

    return None


def _asegurar_liga(guild_id, liga: str) -> bool:
    """Mete la liga en el barrido del servidor si cabe. `False` si no cabe.

    Hace falta porque un aviso solo existe si la liga entra en el barrido: sin
    esto, `/subscribe soloq lck` dejaría un canal que no recibe nada **nunca** y
    sin ningún error, que es el peor fallo posible. Es lo que ya hace `/track`
    cuando sigues a alguien de una liga que no se estaba descargando.

    Se parte de `ligas_guardadas` y no de `ligas_de` a propósito: lo segundo es lo
    que está *en uso* con el cupo aplicado, así que un servidor que bajó de plan
    perdería sus elecciones guardadas al añadir una liga nueva.
    """
    if not liga:
        return True  # no se sabe de qué liga es (una cuenta suelta): nada que hacer
    guardadas = list(ligas_guardadas(guild_id))
    if liga in guardadas and liga in ligas_de(guild_id):
        return True
    en_uso = establecer_ligas(guild_id, guardadas + [liga])
    return liga in en_uso


async def _suscribir_esports(res: Respuesta, _, extra: list[str]) -> str | None:
    """Esports tiene **un** canal por servidor, no una lista con cupo."""
    try:
        save_notification_channel(res.guild_id, res.canal.id)
    except OSError:
        log.exception("No se pudo guardar el canal de esports.")
        return _("esports.canal_fallo_guardar")
    return _("esports.canal_ok", canal=_mencion(res, _), aviso=_aviso_permisos(res, _))


async def _suscribir_soloq(res: Respuesta, _) -> str | None:
    resultado, tope = agregar_canal(res.guild_id, res.canal.id)

    if resultado == "repetido":
        return _("setchannel.ya_estaba", canal=_mencion(res, _))

    if resultado == "cupo":
        # El mensaje dice el cupo y cómo liberar hueco, no solo que no cabe: sin
        # `/channels` el usuario se quedaría sin forma de arreglarlo.
        return _("setchannel.cupo", n=tope, canales=_lista(canales_de(res.guild_id))) + "\n\n" + _("apoyo.cupo_corto")

    aviso = _aviso_permisos(res, _)
    usados = len(canales_de(res.guild_id))
    if tope > 1:
        aviso += "\n" + _("setchannel.cuenta", usados=usados, tope=tope)
    return _("setchannel.ok", canal=_mencion(res, _), aviso=aviso)


async def _cuerpo_subscribe(res: Respuesta, valores: dict[str, str]) -> None:
    _ = tr(res.guild_id)
    tipo = valores.get("type", SOLOQ)
    texto = (valores.get("target") or "").strip()

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(
            _("error.solo_admin") + ("\n" + _("setchannel.solo_admin_extra"))
        )
        return

    # El objetivo, si lo hay, se resuelve **antes** de tocar nada: si no se
    # reconoce, el canal no se añade a medias.
    extra: list[str] = []
    if texto:
        resuelto = _resolver_objetivo(texto)
        if resuelto is None:
            await res.error(_("subscribe.objetivo_desconocido", valor=texto))
            return
        clave, etiqueta, liga = resuelto
        if not _asegurar_liga(res.guild_id, liga):
            await res.error(
                _("subscribe.sin_cupo", liga=liga.upper()) + "\n\n" + _("apoyo.cupo_corto")
            )
            return
        poner(res.guild_id, res.canal.id, tipo, clave)
        extra.append(_(
            "subscribe.objetivo_ok",
            valor=etiqueta,
            tipo=NOMBRE_TIPO.get(tipo, tipo),
        ))
    else:
        # Sin objetivo, el canal vuelve al reparto de siempre. Se dice, porque si
        # no, quien venía de un filtro no sabría que lo ha quitado.
        if limpiar(res.guild_id, res.canal.id):
            extra.append(_("subscribe.vuelve_a_todo"))

    if tipo == ESPORTS:
        mensaje = await _suscribir_esports(res, _, extra)
    else:
        mensaje = await _suscribir_soloq(res, _)

    if mensaje is None:
        await res.error(_("error.generico"))
        return
    await res.send("\n".join([mensaje] + extra))


# ---------------------------------------------------------------------- #
# /unsubscribe
# ---------------------------------------------------------------------- #

async def _cuerpo_unsubscribe(res: Respuesta, valores: dict[str, str]) -> None:
    _ = tr(res.guild_id)
    tipo = valores.get("type", SOLOQ)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(_("error.solo_admin"))
        return

    if tipo == ESPORTS:
        # Solo se quita si este canal es el de esports: decir "hecho" cuando no
        # era el suyo sería mentir, y el usuario se quedaría esperando.
        if load_notification_channel(res.guild_id) != res.canal.id:
            await res.send(_("esports.canal_no_estaba"))
            return
        remove_notification_channel(res.guild_id)
        limpiar(res.guild_id, res.canal.id)
        await res.send(_("esports.canal_desactivado"))
        return

    limpiar(res.guild_id, res.canal.id)
    if quitar_canal(res.guild_id, res.canal.id):
        await res.send(_("canales.quitado", canal=_mencion(res, _)))
    else:
        await res.send(_("canales.no_estaba", canal=_mencion(res, _)))


# ---------------------------------------------------------------------- #
# /mute
# ---------------------------------------------------------------------- #

async def _cuerpo_mute(res: Respuesta, valores: dict[str, str]) -> None:
    _ = tr(res.guild_id)
    tipo = valores.get("type", SOLOQ)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(_("error.solo_admin"))
        return

    if tipo == ESPORTS:
        if not load_notification_channel(res.guild_id):
            await res.send(_("esports.canal_ya_apagado"))
            return
        remove_notification_channel(res.guild_id)
        await res.send(_("esports.canal_desactivado"))
        return

    if not quitar_todos(res.guild_id):
        await res.send(_("unsubscribe.no_habia"))
        return
    await res.send(_("unsubscribe.ok"))


# ---------------------------------------------------------------------- #
# /channels
# ---------------------------------------------------------------------- #

def _objetivos_legibles(por_canal: dict, canales: list[int], _) -> list[str]:
    """Una línea por canal que tenga objetivos, con lo que pidió cada uno."""
    lineas = []
    for canal in canales:
        objetivos = por_canal.get(str(canal)) or {}
        if not objetivos:
            continue
        partes = [
            f"{NOMBRE_TIPO.get(tipo, tipo)}: {', '.join(valores)}"
            for tipo, valores in objetivos.items()
            if valores
        ]
        if partes:
            lineas.append(_("canales.objetivos", canal=f"<#{canal}>", valores=" · ".join(partes)))
    return lineas


async def _cuerpo_channels(res: Respuesta) -> None:
    """Qué canales tiene el servidor, de los dos tipos, y qué pidió cada uno."""
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

    # Qué pidió cada canal. Sin esto, un canal con objetivos parece uno normal y
    # no hay forma de saber por qué no le llega algo.
    lineas.extend(_objetivos_legibles(todos(res.guild_id), guardados, _))

    esports = load_notification_channel(res.guild_id)
    lineas.append(
        _("canales.esports", canal=_lista([esports]) if esports else _("canales.ninguno"))
    )

    lineas.append(_("canales.como_usar"))
    await res.send("\n".join(lineas))


def register_notification_config_commands(bot: commands.Bot) -> None:
    """Los cuatro comandos de canales. Los tres que cambian algo, solo admin."""
    tipo = (("cmd.subscribe.arg", "cmd.subscribe.arg_desc", TIPOS, SOLOQ),)
    # El objetivo es **texto libre**: puede ser una liga, un equipo, un pro o una
    # cuenta, así que no hay lista cerrada que valga. Vacío = el reparto de
    # siempre (todas las ligas del servidor).
    con_objetivo = tipo + (
        ("cmd.subscribe.objetivo", "cmd.subscribe.objetivo_desc", None, ""),
    )
    slash_opciones(
        bot, "cmd.subscribe.name", "cmd.subscribe.desc", _cuerpo_subscribe,
        opciones=con_objetivo, permiso=PERMISO_ADMIN,
    )
    slash_opciones(
        bot, "cmd.unsubscribe.name", "cmd.unsubscribe.desc", _cuerpo_unsubscribe,
        opciones=tipo, permiso=PERMISO_ADMIN,
    )
    slash_opciones(
        bot, "cmd.mute.name", "cmd.mute.desc", _cuerpo_mute,
        opciones=tipo, permiso=PERMISO_ADMIN,
    )
    # `/channels` no cambia nada: mirarlo no necesita permiso.
    slash(bot, "cmd.channels.name", "cmd.channels.desc", _cuerpo_channels)

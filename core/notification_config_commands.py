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
    agregar_canal_esports,
    canales_esports,
    quitar_canal_esports,
    quitar_todos_esports,
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
from utils.i18n import comando, tr
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


def _resolver_objetivo(texto: str) -> tuple[str, str, str, str | None] | None:
    """Lo que escribió el usuario -> `(clave, etiqueta, liga, clave_partidos)`.

    `clave` es lo que se guarda y con lo que compara el reparto de SoloQ;
    `etiqueta` es lo que se enseña; `liga` es a la que pertenece, para poder
    meterla en el barrido; `clave_partidos` es lo que hay que guardar en el eje de
    partidos oficiales, o `None` si eso no tiene partidos.

    La cuarta pieza no es un adorno. Un partido oficial lo determina su liga y sus
    dos equipos, no el nick de nadie: guardar `Faker` como objetivo de partidos no
    casaría **nunca** y el canal se quedaría esperando en silencio. De un jugador
    se guarda su equipo (`T1`), que es lo que trae el roster. De una cuenta suelta
    no hay nada que guardar: no se sabe de qué equipo es.

    El orden es el mismo que usa `/track` —cuenta, liga, pro, equipo— y por el
    mismo motivo: un Riot ID lleva `#` y ninguna liga lo tiene, y un código de liga
    no es el nick de nadie. `None` si no se reconoce nada.
    """
    texto = (texto or "").strip()
    if not texto:
        return None

    # Una cuenta suelta no pertenece a ninguna liga conocida, así que no hay nada
    # que meter en el barrido: se guarda y ya. Y tampoco juega partidos oficiales
    # con ese nombre.
    if "#" in texto:
        return (texto, texto, "", None)

    liga = resolver(texto)
    if liga is not None:
        return (liga.codigo, liga.nombre, liga.codigo, liga.codigo)

    jugador = pro_rastreado(texto)
    if jugador is not None:
        nombre = getattr(jugador, "name", texto) or texto
        equipo = (getattr(jugador, "team", "") or "").strip()
        return (nombre, nombre, (getattr(jugador, "league", "") or "").lower(),
                equipo or None)

    equipo = equipo_rastreado(texto)
    if equipo is not None:
        # La liga del equipo se cuenta aparte: un equipo aparece en el roster en
        # su liga y en los eventos internacionales, y quedarse con la primera
        # coincidencia metía el MSI en el barrido en vez de la LCK.
        liga_equipo = liga_principal_de_equipo(equipo[0]) or (equipo[2] or "").lower()
        return (equipo[0], equipo[1], liga_equipo, equipo[0])

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
    """Esports: varios canales por servidor, cada uno con sus objetivos.

    Antes era **un** canal por servidor, y eso hacía que `/subscribe esports lck`
    en un segundo canal se llevara los partidos del primero sin decirlo. Ahora se
    suman, igual que los de SoloQ, y el registro de «ya avisado» de esports está
    indexado por canal, así que el mismo partido llega a los dos.
    """
    try:
        nuevo = agregar_canal_esports(res.guild_id, res.canal.id)
    except OSError:
        log.exception("No se pudo guardar el canal de esports.")
        return _("esports.canal_fallo_guardar")
    if nuevo:
        return _("esports.canal_ok", canal=_mencion(res, _), aviso=_aviso_permisos(res, _))
    return _("esports.canal_ya_estaba", canal=_mencion(res, _))


async def _suscribir_soloq(res: Respuesta, _) -> str | None:
    resultado, tope = agregar_canal(res.guild_id, res.canal.id)

    if resultado == "repetido":
        return _("setchannel.ya_estaba", canal=_mencion(res, _))

    if resultado == "cupo":
        # El mensaje dice el cupo y cómo liberar hueco, no solo que no cabe: sin
        # `/channels` el usuario se quedaría sin forma de arreglarlo.
        #
        # **Sin el bloque de `apoyo.cupo_corto` detrás.** Se quitó el 19-10-2026:
        # el error ya decía qué hacer, y encima venía una justificación de por qué
        # existen los límites. Quien está intentando añadir un canal quiere el
        # comando, no una defensa. La explicación sigue en `/premium`, que es
        # donde alguien la busca.
        return _("setchannel.cupo", n=tope, canales=_lista(canales_de(res.guild_id)))

    aviso = _aviso_permisos(res, _)
    usados = len(canales_de(res.guild_id))
    if tope > 1:
        aviso += "\n" + _("setchannel.cuenta", usados=usados, tope=tope)
    return _("setchannel.ok", canal=_mencion(res, _), aviso=aviso)


def _partir_objetivo(crudo: str) -> tuple[str, str]:
    """Lo que escribió el usuario -> `(tipo, objetivo)`.

    `/subscribe worlds` -> `("", "worlds")` — **los dos** tipos de aviso
    `/subscribe soloq worlds` -> `("soloq", "worlds")`
    `/subscribe esports worlds` -> `("esports", "worlds")`
    `/subscribe esports` -> `("esports", "")`

    Por qué sin tipo van los dos
    ----------------------------
    Hasta el 05-11-2026 sin tipo iba **solo** SoloQ, y `/subscribe worlds` dejaba
    un canal que no recibía ni un partido de Worlds. El dueño lo probó en un
    servidor nuevo y lo dijo tal cual: *«se supone que era ambas cosas y para
    poder elegir»*. Para el usuario, seguir Worlds es una sola idea, y quien
    quiere solo una de las dos lo dice con la palabra delante — que es
    exactamente lo que ya hacía `/track`.

    Por qué hay **una** opción de texto libre y no dos (`type` cerrado +
    `target` libre), que era lo natural y era como estaba hasta el 02-11-2026:

    el dueño escribió `/subscribe worlds` en un servidor nuevo y no le llegó
    nada, nunca. El motivo no era el filtro ni Worlds: Discord mete el texto
    suelto en la **primera** opción, y la primera era `type`, que es una lista
    cerrada (`soloq`/`esports`). `worlds` no está en esa lista, así que Discord
    lo descartaba y mandaba `type=soloq` con el objetivo **vacío**. El canal
    quedaba suscrito «a todo lo del servidor», que en un servidor nuevo es la
    LEC por defecto, y de Worlds no llegaba nada. Sin ningún error: el comando
    contestaba «canal añadido».

    Con una sola opción, lo que se teclea entra tal cual y aquí se separa. Y las
    dos formas que documenta `/help` siguen valiendo, porque la primera palabra
    solo se interpreta como tipo si **es** un tipo.
    """
    crudo = (crudo or "").strip()
    if not crudo:
        return "", ""

    primera, _, resto = crudo.partition(" ")
    if primera.strip().casefold() in TIPOS:
        return primera.strip().casefold(), resto.strip()
    return "", crudo


async def _cuerpo_subscribe(res: Respuesta, valores: dict[str, str]) -> None:
    _ = tr(res.guild_id)
    if "type" in valores:
        # Firma vieja (dos opciones). Se sigue aceptando por si Discord todavía
        # manda el comando anterior mientras propaga el nuevo.
        tipo = valores.get("type") or SOLOQ
        texto = (valores.get("target") or "").strip()
    else:
        tipo, texto = _partir_objetivo(valores.get("target") or "")

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(
            _("error.solo_admin") + ("\n" + _("setchannel.solo_admin_extra"))
        )
        return

    # Sin objetivo no hay nada a lo que atar los partidos oficiales, así que
    # `/subscribe` a secas sigue siendo SoloQ con el reparto de siempre. Con
    # objetivo, y sin decir el tipo, van las dos cosas.
    if texto:
        tipos = (SOLOQ, ESPORTS) if not tipo else (tipo,)
    else:
        tipos = (tipo,) if tipo else (SOLOQ,)

    # El objetivo, si lo hay, se resuelve **antes** de tocar nada: si no se
    # reconoce, el canal no se añade a medias.
    extra: list[str] = []
    if texto:
        resuelto = _resolver_objetivo(texto)
        if resuelto is None:
            await res.error(_("subscribe.objetivo_desconocido", valor=texto))
            return
        clave, etiqueta, liga, clave_partidos = resuelto
        if not _asegurar_liga(res.guild_id, liga):
            await res.error(
                _("subscribe.sin_cupo", liga=liga.upper(),
                  cmd=comando("cmd.leagues.name"))
            )
            return

        puestos = []
        for cada in tipos:
            if cada == ESPORTS:
                if clave_partidos is None:
                    # Un Riot ID suelto no tiene partidos: se dice en vez de
                    # dejar un objetivo que no casaría nunca.
                    extra.append(_("subscribe.sin_partidos", valor=etiqueta))
                    continue
                poner(res.guild_id, res.canal.id, ESPORTS, clave_partidos)
            else:
                poner(res.guild_id, res.canal.id, SOLOQ, clave)
            puestos.append(cada)

        if puestos == [SOLOQ, ESPORTS]:
            extra.append(_("subscribe.objetivo_ambos", valor=etiqueta))
            extra.append(_("subscribe.como_elegir", valor=texto))
        elif puestos:
            extra.append(_(
                "subscribe.objetivo_ok",
                valor=etiqueta,
                tipo=NOMBRE_TIPO.get(puestos[0], puestos[0]),
            ))
        tipos = tuple(puestos) or (SOLOQ,)
    else:
        # Sin objetivo, el canal vuelve al reparto de siempre. Se dice, porque si
        # no, quien venía de un filtro no sabría que lo ha quitado.
        if limpiar(res.guild_id, res.canal.id):
            extra.append(_("subscribe.vuelve_a_todo"))

    mensajes = []
    for cada in tipos:
        if cada == ESPORTS:
            mensajes.append(await _suscribir_esports(res, _, extra))
        else:
            mensajes.append(await _suscribir_soloq(res, _))

    if not any(mensajes):
        await res.error(_("error.generico"))
        return
    await res.send("\n".join([m for m in mensajes if m] + extra))


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
        # Solo se quita si este canal es uno de los de esports: decir "hecho"
        # cuando no lo era sería mentir, y el usuario se quedaría esperando.
        if res.canal.id not in canales_esports(res.guild_id):
            await res.send(_("esports.canal_no_estaba"))
            return
        quitar_canal_esports(res.guild_id, res.canal.id)
        limpiar(res.guild_id, res.canal.id)
        await res.send(_("esports.canal_desactivado"))
        return

    # `/unsubscribe` es «este canal, fuera de todo». Desde el 05-11-2026 eso
    # incluye los partidos oficiales: si `/subscribe worlds` enciende las dos
    # cosas, dejar aquí los partidos encendidos haría que alguien que se dio de
    # baja siguiera recibiendo avisos y no entendiera por qué. Con
    # `type: esports` se apaga solo esa mitad, que es la forma de quedarse con
    # una.
    limpiar(res.guild_id, res.canal.id)
    quito_soloq = quitar_canal(res.guild_id, res.canal.id)
    quito_esports = quitar_canal_esports(res.guild_id, res.canal.id)
    if quito_soloq or quito_esports:
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
        if not quitar_todos_esports(res.guild_id):
            await res.send(_("esports.canal_ya_apagado"))
            return
        await res.send(_("esports.canal_desactivado"))
        return

    # Y los partidos, por el mismo motivo que en `/unsubscribe`: `/mute` apaga
    # **todo** el servidor, y dejar los partidos encendidos sería mentir en el
    # mensaje de confirmación.
    habia_partidos = quitar_todos_esports(res.guild_id)
    if not quitar_todos(res.guild_id) and not habia_partidos:
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

    esports = canales_esports(res.guild_id)
    lineas.append(
        _("canales.esports", canal=_lista(esports) if esports else _("canales.ninguno"))
    )

    lineas.append(_("canales.como_usar"))
    await res.send("\n".join(lineas))


def register_notification_config_commands(bot: commands.Bot) -> None:
    """Los cuatro comandos de canales. Los tres que cambian algo, solo admin."""
    tipo = (("cmd.subscribe.arg", "cmd.subscribe.arg_desc", TIPOS, SOLOQ),)
    # El objetivo es **texto libre** y es la **única** opción: puede ser una liga,
    # un equipo, un pro o una cuenta, y delante admite `soloq`/`esports`. Vacío =
    # el reparto de siempre (todas las ligas del servidor).
    #
    # Una sola opción a propósito: con dos, la primera era la lista cerrada del
    # tipo y Discord se comía el texto que no fuera `soloq`/`esports`. Ver
    # `_partir_objetivo`.
    con_objetivo = (
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

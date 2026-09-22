"""Elección de ligas por servidor (`/ligas`) e idioma (`/lang`).

Por qué existe `/ligas`
----------------------
El bot solo seguía la LEC porque los equipos estaban escritos a mano en el
código. Ahora la lista sale del leaderboard de cada liga, así que ampliarla es
cuestión de que el servidor elija.

Sobre el límite de ligas
------------------------
Cada liga son unos 50 jugadores con ~3 cuentas cada uno: ~170 cuentas por liga
que hay que consultar en cada pasada. Con `MAX_LIGAS_POR_SERVIDOR` ligas el
tracker se mantiene dentro del cupo de la API de Riot (500 peticiones/10 s) sin
que una pasada llegue a solaparse con la siguiente.

Es también el eje del modelo de negocio: el plan gratuito lleva una liga y los
de pago llegan hasta el máximo. El límite duro está en
`tracking/soloq/leagues.py`; si se quiere cobrar por ello, ahí es donde se
consulta el plan del servidor.

Sobre `/lang`
-------------
El mismo comando hace **dos cosas distintas según dónde se use**, y eso es
deliberado:

* En un servidor cambia el idioma del **servidor**, y sigue pidiendo permisos de
  administrador. Las notificaciones van a un canal que leen todos, así que el
  canal manda y no puede decidirlo cualquiera.
* En privado cambia el idioma de la **persona**. Ahí no hay servidor que mandar,
  y quien lo pide es el único que va a leer la respuesta, así que no hay permiso
  que comprobar.

La alternativa era un `/milang` aparte. Se descartó porque duplica el comando que
la gente ya conoce para hacer lo mismo, y porque en un DM `/lang` no puede hacer
otra cosa: si no cambiara el idioma personal, tendría que dar un error, y un
comando que existe en el selector solo para negarse es peor que uno que hace lo
razonable.

El orden de resolución completo está en `utils.i18n.idioma_efectivo`.
"""

from __future__ import annotations

from nextcord.ext import commands

from core.dual_command import PERMISO_ADMIN, dual_texto
from core.responder import Respuesta
from tracking.soloq.leagues import (
    LIGAS,
    MAX_LIGAS_POR_SERVIDOR,
    establecer_ligas,
    ligas_de,
    ligas_guardadas,
    resolver,
    tope_de_ligas,
)
from utils.i18n import (
    IDIOMAS,
    establecer_idioma,
    establecer_idioma_usuario,
    idioma_de,
    idioma_de_usuario,
    normalizar_idioma,
    tr,
    tr_usuario,
)
from utils.logger import get_logger

log = get_logger("core.league_commands")


def _lista_legible(codigos: list[str]) -> str:
    """`["lec", "lck"]` -> `"LEC (Europa), LCK (Corea)"`."""
    partes = []
    for codigo in codigos:
        liga = LIGAS.get(codigo)
        if liga is None:
            continue
        partes.append(f"**{liga.nombre}** ({liga.region})")
    return ", ".join(partes) or "—"


def _lista_codigos(codigos: list[str]) -> str:
    """La misma lista pero por código: `` `lec` LEC · `lck` LCK ``.

    Con 20 ligas la versión larga («**Nombre** (Región)», 19 entradas) se comía
    el mensaje entero y encima no enseñaba lo único que hay que teclear. Aquí
    interesa el código, porque es el argumento del comando.
    """
    partes = []
    for codigo in codigos:
        liga = LIGAS.get(codigo)
        if liga is None:
            continue
        partes.append(f"`{codigo}` {liga.nombre}")
    return " · ".join(partes) or "—"


async def _cuerpo_ligas(res: Respuesta, valor: str) -> None:
    _ = tr(res.guild_id)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return

    texto = (valor or "").strip()
    tope = tope_de_ligas(res.guild_id)

    # Sin argumentos: muestra el estado, no cambia nada.
    if not texto:
        actuales = ligas_de(res.guild_id)
        guardadas = ligas_guardadas(res.guild_id)
        disponibles = [c for c in LIGAS if c not in actuales]
        lineas = [
            f"**{_('ligas.titulo')}**",
            _("ligas.actuales", ligas=_lista_legible(actuales)),
        ]
        # Solo si el plan deja fuera algo que el servidor ya había elegido: si
        # no se dice, esas ligas parecen borradas.
        fuera = [c for c in guardadas if c not in actuales]
        if fuera:
            lineas.append(_("ligas.fuera_de_cupo", ligas=_lista_legible(fuera)))
        lineas += [
            "",
            _("ligas.disponibles", ligas=_lista_codigos(disponibles)),
            "",
            _("ligas.maximo", maximo=tope),
            _("ligas.como_usar"),
        ]
        await res.send("\n".join(lineas))
        return

    # Con argumentos: hay que ser admin, igual que `/setchannel`.
    if not res.es_admin():
        await res.error(_("error.solo_admin"))
        return

    if res.guild is None:
        await res.error(_("error.solo_en_servidor"))
        return

    pedidas = [p for p in texto.replace(",", " ").split() if p]
    validas = [p for p in pedidas if resolver(p) is not None]
    desconocidas = [p for p in pedidas if resolver(p) is None]

    if not validas:
        await res.error(_("ligas.no_reconocidas"))
        return

    guardadas = establecer_ligas(res.guild_id, validas)

    lineas = [_("ligas.actualizado", ligas=_lista_legible(guardadas))]
    if desconocidas:
        lineas.append(_("ligas.desconocidas", ligas=", ".join(desconocidas)))
    if len(validas) > len(guardadas):
        # Dos motivos distintos para recortar y el usuario necesita saber cuál:
        # si es el plan, `/premium` lo arregla; si es el límite físico, no.
        if tope < MAX_LIGAS_POR_SERVIDOR:
            lineas.append(_("ligas.truncado_plan", maximo=tope))
        else:
            lineas.append(_("ligas.truncado", maximo=tope))

    await res.send("\n".join(lineas))


async def _cuerpo_lang(res: Respuesta, valor: str) -> None:
    """`/lang`: idioma del servidor dentro de uno, idioma propio en privado.

    Ver el docstring del módulo. La respuesta va siempre en el idioma que quede
    en vigor, no en el anterior: comprobar que el cambio funcionó es la primera
    cosa que va a hacer quien acaba de pedirlo.
    """
    _ = res.traductor()
    opciones = ", ".join(f"`{c}` ({n})" for c, n in IDIOMAS.items())
    texto = (valor or "").strip()

    # ---- En privado: el idioma es de la persona -------------------------- #
    if res.es_privado:
        if res.autor_id is None:
            await res.error(_("lang.desconocido", opciones=opciones))
            return

        if not texto:
            elegido = idioma_de_usuario(res.autor_id)
            if elegido:
                linea = _("lang.mio_actual", idioma=IDIOMAS[elegido])
            else:
                # Sin idioma elegido se enseña el que se está usando de verdad
                # (el locale de su cliente, o español), no un "ninguno": lo que
                # el usuario quiere saber es en qué idioma le habla el bot.
                en_uso = _idioma_en_uso(res)
                linea = _("lang.mio_defecto", idioma=IDIOMAS.get(en_uso, en_uso))
            await res.send("\n".join([
                f"**{_('lang.titulo')}**",
                linea,
                _("lang.opciones", opciones=opciones),
            ]))
            return

        codigo = normalizar_idioma(texto)
        if codigo is None:
            await res.error(_("lang.desconocido", opciones=opciones))
            return

        establecer_idioma_usuario(res.autor_id, codigo)
        _nuevo = tr_usuario(res.autor_id, None, res.locale)
        await res.send(_nuevo("lang.mio_cambiado", idioma=IDIOMAS[codigo]))
        return

    # ---- En un servidor: el idioma es del servidor ----------------------- #
    if not texto:
        actual = idioma_de(res.guild_id)
        await res.send("\n".join([
            f"**{_('lang.titulo')}**",
            _("lang.actual", idioma=IDIOMAS.get(actual, actual)),
            _("lang.opciones", opciones=opciones),
        ]))
        return

    if not res.es_admin():
        await res.error(_("error.solo_admin"))
        return

    codigo = normalizar_idioma(texto)
    if codigo is None:
        await res.error(_("lang.desconocido", opciones=opciones))
        return

    establecer_idioma(res.guild_id, codigo)
    _nuevo = tr(res.guild_id)
    await res.send(_nuevo("lang.cambiado", idioma=IDIOMAS[codigo]))


def _idioma_en_uso(res: Respuesta) -> str:
    """En qué idioma le está hablando el bot a esta persona ahora mismo."""
    from utils.i18n import idioma_efectivo

    return idioma_efectivo(res.autor_id, res.guild_id, res.locale)


def register_league_commands(bot: commands.Bot) -> None:
    dual_texto(
        bot,
        "ligas",
        "cmd.ligas.desc",
        _cuerpo_ligas,
        arg_nombre="cmd.ligas.arg",
        arg_desc="cmd.ligas.arg_desc",
        requerido=False,
    )
    dual_texto(
        bot,
        "lang",
        "cmd.lang.desc",
        _cuerpo_lang,
        arg_nombre="cmd.lang.arg",
        arg_desc="cmd.lang.arg_desc",
        requerido=False,
    )

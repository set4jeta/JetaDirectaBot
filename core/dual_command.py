"""Registro de un mismo comando en las dos formas: `!comando` y `/comando`.

El problema
-----------
El usuario pidió pasar a slash commands manteniendo los mismos comandos
funcionando. La vía obvia —escribir cada comando dos veces— crea 13 parejas de
funciones que hay que mantener sincronizadas a mano; la primera que se olvide
hace que `/live` y `!live` respondan cosas distintas.

La solución
-----------
El cuerpo del comando se escribe **una sola vez** y recibe un
`core.responder.Respuesta`, que abstrae `Context` e `Interaction`. Aquí están
los envoltorios que lo registran en las dos formas.

Tres formas cubren todos los comandos del bot:

* `dual` — comandos sin argumentos (`live`, `help`, `setchannel`, `partida`...).
* `dual_texto` — comandos con un único argumento de texto (`team`, `match`,
  `info`, `historial`).
* registro manual — para `ranking` (con selector de liga), donde la forma slash
  necesita algo específico.

Detalle importante sobre los argumentos de prefijo
--------------------------------------------------
En `dual_texto` el parámetro de prefijo se declara `*, valor: str = ""`. El
asterisco hace que nextcord meta **todo el resto del mensaje** en ese argumento,
que es lo que ya hacían `!info` y `!match`: los nicks de pro llevan espacios
("G2 Caps"), y sin el asterisco `!info G2 Caps` habría llegado como `"G2"`.

Cómo se traducen los comandos en la lista de Discord
----------------------------------------------------
El tercer parámetro (`descripcion`) es ahora una **clave del catálogo**
(`"cmd.live.desc"`), no una cadena. De ahí salen dos cosas:

* `description` = el inglés, que es lo que Discord muestra a cualquiera cuyo
  cliente esté en un idioma que no traducimos (los otros 29).
* `description_localizations` = `{es-ES: ..., es-419: ...}`.

Ojo con la diferencia: esto lo elige Discord por el idioma del **cliente de cada
usuario**, mientras que las respuestas del bot van en el idioma del **servidor**
(`/lang`). Son dos cosas distintas y las dos hacían falta: sin esto, un usuario
inglés veía la lista de comandos en español aunque las respuestas ya estuvieran
traducidas.

Si la clave no existe en el catálogo se usa el texto tal cual. Así un comando
nuevo puede registrarse antes de tener traducción sin quedarse con la clave
cruda de descripción.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import nextcord
from nextcord import SlashOption
from nextcord.ext import commands

from core.responder import Respuesta
from utils.i18n import _CATALOGO, MAX_DESCRIPCION, MAX_NOMBRE, localizaciones, texto_base
from utils.logger import get_logger

log = get_logger("core.dual")

CuerpoSimple = Callable[[Respuesta], Awaitable[None]]
CuerpoTexto = Callable[[Respuesta, str], Awaitable[None]]


def textos_de(clave: str) -> tuple[str, dict[str, str]]:
    """`(descripción base, localizaciones)` a partir de una clave del catálogo.

    Una clave que no está en el catálogo se devuelve tal cual: así se puede
    registrar un comando nuevo antes de traducirlo sin que Discord acabe
    mostrando `cmd.loquesea.desc` en la lista.

    El recorte a 100 caracteres no es cosmético: Discord rechaza el registro
    **completo** con un 400 si una sola descripción se pasa, y el bot se queda
    sin ningún slash command. Se recorta y se avisa en el log en vez de dejar
    que reviente el despliegue entero.
    """
    if clave not in _CATALOGO:
        return _recortar(clave, clave), {}
    base = _recortar(texto_base(clave), clave)
    locales = {
        loc: _recortar(texto, f"{clave}[{loc}]")
        for loc, texto in localizaciones(clave).items()
    }
    return base, locales


def _recortar(texto: str, etiqueta: str) -> str:
    if len(texto) <= MAX_DESCRIPCION:
        return texto
    log.warning(
        "Descripción de %s con %d caracteres (máx %d): se recorta.",
        etiqueta, len(texto), MAX_DESCRIPCION,
    )
    return texto[: MAX_DESCRIPCION - 1] + "…"


def nombre_de(clave: str) -> tuple[str, dict[str, str]]:
    """Igual que `textos_de`, pero para el **nombre** de una opción.

    Los nombres tienen reglas más duras que las descripciones: Discord solo
    acepta `[a-z0-9_-]`, hasta 32 caracteres, sin espacios ni mayúsculas ni
    tildes. Un nombre inválido es otro 400 que tumba el registro entero, así que
    se normaliza aquí: "jugador" pasa, "Nick del pro" no pasaría y se convierte
    en `nick-del-pro`.
    """
    if clave not in _CATALOGO:
        return _saneado(clave), {}
    base = _saneado(texto_base(clave))
    locales = {loc: _saneado(txt) for loc, txt in localizaciones(clave).items()}
    # Un locale cuyo nombre saneado coincide con el base no aporta nada y solo
    # engorda el payload.
    return base, {loc: n for loc, n in locales.items() if n and n != base}


_TILDES = str.maketrans("áàäâãéèëêíìïîóòöôõúùüûñç", "aaaaaeeeeiiiiooooouuuunc")


def _saneado(texto: str) -> str:
    limpio = (texto or "").strip().lower().translate(_TILDES)
    limpio = "".join(c if (c.isalnum() or c in "_-") else "-" for c in limpio)
    limpio = "-".join(p for p in limpio.split("-") if p)  # sin guiones dobles
    return limpio[:MAX_NOMBRE] or "valor"


# ---------------------------------------------------------------------- #
# Dónde se puede usar cada comando
# ---------------------------------------------------------------------- #
#
# Qué añade esto
# --------------
# Hasta ahora el bot solo se podía instalar en un servidor, así que sus comandos
# solo existían dentro de servidores donde estuviera como miembro. Discord tiene
# desde 2024 una segunda vía, la **instalación por usuario**: alguien añade la
# app a su propia cuenta y sus comandos le siguen a cualquier sitio donde él
# esté, incluido el DM con el bot y servidores donde el bot no está.
#
# Se controla con dos campos del registro del comando:
#
# * `integration_types` — quién puede instalarlo: el servidor, la persona, o las
#   dos cosas.
# * `contexts` — dónde se puede invocar: dentro de un servidor, en el DM con el
#   bot, o en cualquier otro chat privado (grupos y DM con terceros).
#
# Los dos existen en el nextcord instalado (3.1.0, comprobado inspeccionando la
# firma de `slash_command` y los enums `IntegrationType` /
# `InteractionContextType`), así que esto no necesita actualizar la librería.
#
# La regla: quien pide permisos es de servidor
# --------------------------------------------
# `default_member_permissions` es un permiso **de servidor**. Un comando que lo
# lleva —`/setchannel`, `/unsubscribe`, `/quitarcanal` y los dos de esports— no
# tiene ningún sentido fuera de uno: configura un canal de un servidor y su
# cerrojo es un permiso que en un DM no existe. Así que el alcance se **deriva**
# de eso en vez de declararse comando por comando: con `permiso`, solo servidor;
# sin `permiso`, en todas partes.
#
# Derivarlo en vez de pedirlo tiene un motivo concreto: si fuera un parámetro
# suelto, el día que se añada un comando de administración nuevo habría que
# acordarse de ponerlo, y olvidarlo significa publicar un comando de
# configuración en el DM de cualquiera, donde `res.es_admin()` devuelve False y
# lo único que produce es un error confuso. Derivado no se puede olvidar.
#
# `alcance="servidor"` sigue existiendo para el caso raro de un comando sin
# permisos que aun así necesite servidor.

#: Instalable por servidor y por persona, invocable en cualquier sitio. Es el
#: caso normal: todos los comandos de consulta (`/live`, `/info`, `/match`,
#: `/historial`, `/team`, `/ranking`, `/help`...).
GLOBAL = "global"

#: Solo dentro de un servidor donde el bot esté instalado. Los de configuración.
SERVIDOR = "servidor"


def ambito_de(alcance: str) -> dict:
    """Kwargs de `slash_command` para un alcance. `{}` si la librería no puede.

    Se devuelven como dict y no como parámetros fijos por dos motivos. Uno, que
    el registro siga funcionando en una versión de nextcord que no conozca estos
    campos: sin ellos el comando queda como estaba (solo servidor), que es
    degradar y no romper — antes de esto el bot no arrancaría con la librería
    vieja. Y dos, que `/ranking` se registra a mano (su argumento es un
    desplegable de ligas, no texto libre) y necesita el mismo ámbito que los
    demás sin duplicar la lógica; de ahí que sea pública y no `_ambito`.
    """
    try:
        from nextcord import IntegrationType, InteractionContextType
    except ImportError:  # pragma: no cover - nextcord < 3.0
        log.warning(
            "Esta versión de nextcord no soporta instalación por usuario: "
            "los comandos quedan solo para servidores."
        )
        return {}

    if alcance == SERVIDOR:
        return {
            "integration_types": [IntegrationType.guild_install],
            "contexts": [InteractionContextType.guild],
        }
    return {
        "integration_types": [
            IntegrationType.guild_install,
            IntegrationType.user_install,
        ],
        "contexts": [
            InteractionContextType.guild,
            InteractionContextType.bot_dm,
            InteractionContextType.private_channel,
        ],
    }


def dual(
    bot: commands.Bot,
    nombre: str,
    descripcion: str,
    cuerpo: CuerpoSimple,
    *,
    permiso: nextcord.Permissions | None = None,
    alcance: str | None = None,
) -> None:
    """Registra `!nombre` y `/nombre` sin argumentos, con el mismo cuerpo.

    `descripcion` es una clave del catálogo (`"cmd.live.desc"`); de ahí salen la
    descripción base en inglés y las localizaciones que Discord muestra según el
    idioma del cliente de cada usuario.

    `permiso` añade `default_member_permissions` a la forma slash, que hace que
    Discord **ni le muestre el comando** a quien no lo tiene. Eso es interfaz,
    no seguridad, y no existe para los comandos de prefijo: el cuerpo tiene que
    comprobarlo igual con `res.es_admin()`.

    `alcance` decide dónde se puede usar (`GLOBAL` o `SERVIDOR`). Por defecto se
    deriva de `permiso`: un comando con permisos de servidor solo tiene sentido
    dentro de uno. Ver el bloque de arriba.
    """
    desc, locales = textos_de(descripcion)
    ambito = ambito_de(alcance or (SERVIDOR if permiso is not None else GLOBAL))

    @bot.command(name=nombre)
    async def _prefijo(ctx: commands.Context):  # noqa: ANN202
        await cuerpo(Respuesta(ctx))

    extra = {} if permiso is None else {"default_member_permissions": permiso}

    @bot.slash_command(
        name=nombre,
        description=desc,
        description_localizations=locales or None,
        **extra,
        **ambito,
    )
    async def _slash(interaction: nextcord.Interaction):  # noqa: ANN202
        await cuerpo(Respuesta(interaction))


#: Permiso que se exige para cambiar la configuración del servidor (canales de
#: notificación). Está aquí para que los cuatro comandos que lo usan —dos de
#: SoloQ, dos de esports— no declaren cada uno el suyo.
PERMISO_ADMIN = nextcord.Permissions(manage_guild=True)


def dual_texto(
    bot: commands.Bot,
    nombre: str,
    descripcion: str,
    cuerpo: CuerpoTexto,
    *,
    arg_nombre: str,
    arg_desc: str,
    requerido: bool = True,
    alcance: str | None = None,
) -> None:
    """Registra `!nombre <texto>` y `/nombre <arg>` con el mismo cuerpo.

    `descripcion`, `arg_nombre` y `arg_desc` son claves del catálogo. El nombre
    del argumento también se localiza: un usuario con el cliente en español ve
    `/match jugador:` y uno en inglés `/match player:` — mismo comando, y lo que
    llega al cuerpo es el valor, no el nombre, así que nada más cambia.

    `requerido=False` deja el argumento opcional en las dos formas: así
    `!historial` sin nada sigue dando el historial global y `/historial` puede
    invocarse sin rellenar el campo.

    `alcance` por defecto es `GLOBAL`: todos los comandos con argumento de texto
    son de consulta (`/info`, `/match`, `/historial`, `/team`, `/ligas`), y son
    justo los que el usuario pidió poder usar desde su propio chat.
    """
    desc, locales = textos_de(descripcion)
    arg, arg_locales = nombre_de(arg_nombre)
    ayuda, ayuda_locales = textos_de(arg_desc)
    ambito = ambito_de(alcance or GLOBAL)

    @bot.command(name=nombre)
    async def _prefijo(ctx: commands.Context, *, valor: str = ""):  # noqa: ANN202
        await cuerpo(Respuesta(ctx), valor.strip())

    @bot.slash_command(
        name=nombre,
        description=desc,
        description_localizations=locales or None,
        **ambito,
    )
    async def _slash(  # noqa: ANN202
        interaction: nextcord.Interaction,
        valor: str = SlashOption(
            name=arg,
            name_localizations=arg_locales or None,
            description=ayuda,
            description_localizations=ayuda_locales or None,
            required=requerido,
            **({} if requerido else {"default": ""}),
        ),
    ):
        await cuerpo(Respuesta(interaction), (valor or "").strip())


def dual_cog(
    cog: commands.Cog,
    bot: commands.Bot,
    nombre: str,
    descripcion: str,
    cuerpo: CuerpoSimple,
    *,
    permiso: nextcord.Permissions | None = None,
    alcance: str | None = None,
) -> None:
    """Igual que `dual`, pero para comandos que viven dentro de un Cog.

    Los comandos de esports están en `EsportsCommands`, cuyo estado (el
    `TrackerService`) es de la instancia. En vez de declarar el slash dentro de
    la clase —donde nextcord exige el parámetro `self` y el cog tiene que estar
    registrado antes— se registra aquí contra el bot pasando un cuerpo que ya
    lleva el `cog` capturado en la clausura.

    El parámetro `cog` no se usa: está en la firma para que en el sitio de la
    llamada quede claro a quién pertenece el comando, y para que si algún día
    hace falta enganchar algo del cog (un `cog_check`, por ejemplo) el punto de
    extensión ya exista.
    """
    dual(bot, nombre, descripcion, cuerpo, permiso=permiso, alcance=alcance)

"""Registro de los slash commands: `/comando`.

Qué cambió el 22-09-2026 (y por qué)
------------------------------------
Antes cada comando se registraba **dos veces**, como `/comando` y como
`!comando`, con un `alias` que además mantenía vivos los nombres antiguos. El
dueño lo cortó en seco: *«los `!` son los que hay que borrar… te dije rediseña
los comandos con slash»*. Tiene razón en el fondo: el slash es lo que se usa (lo
autocompleta Discord, tiene descripción y argumentos tipados) y el `!` era una
capa heredada que obligaba a mantener dos superficies y a decidir dos veces cada
nombre.

Así que ahora hay **una sola superficie**: slash. Nada de alias y nada de nombres
antiguos; un comando por función.

Los nombres, de **una palabra**
------------------------------
El dueño también fue explícito: *«que se entienda su significado de una palabra»*.
De ahí salen dos reglas que aplica `scripts/test_slash_locale.py`:

1. **Ningún nombre lleva guion ni guion bajo.** `esports-live` estaba mal: si es
   esports, es `esports`. Los nombres compuestos (`channel-add`, `alerts-off`)
   se han ido y lo que distinguía se expresa con una **opción de lista cerrada**
   (`type: soloq | esports`), que es donde Discord quiere esa información.
2. **El nombre base va en inglés** (`cmd.X.name`) porque es el que Discord enseña
   a los 30 locales que no traducimos, y el español viaja como
   `name_localizations` (`es-ES` y `es-419`).

Detalle de la API de Discord que hace que esto sea barato de cambiar —aunque el
usuario vea `/historial`, **la interacción llega siempre con el nombre base**:

    "When taking advantage of command localization, the interaction payload
     received by your client will still use default command, subcommand, and
     option names." (docs de Discord, Application Commands › Localization)

O sea que el enrutado no depende del nombre que se ve, y renombrar es solo
interfaz.

Las tres formas
---------------
* `slash` — comandos sin argumentos (`live`, `help`, `channels`...).
* `slash_texto` — un argumento de texto libre (`team`, `match`, `player`).
* `slash_opcion` — un argumento de lista cerrada (`subscribe`, `mute`: el
  `type` que decide entre SoloQ y esports).

`ranking` se registra a mano porque su argumento es un desplegable de las 20
ligas, no texto libre.

Ojo con la diferencia de idiomas: **la interfaz** (nombres y descripciones) la
localiza Discord según el idioma del *cliente de cada usuario*; **las respuestas**
van en el idioma del *servidor* (`/language`). Son dos cosas distintas.
"""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable

import nextcord
from nextcord import SlashOption
from nextcord.ext import commands

from core.responder import Respuesta
from utils.i18n import _CATALOGO, MAX_DESCRIPCION, MAX_NOMBRE, localizaciones, texto_base
from utils.logger import get_logger

log = get_logger("core.slash")

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
    """Igual que `textos_de`, pero para un **nombre**: el de un comando o una opción.

    Los nombres tienen reglas más duras que las descripciones: Discord solo
    acepta `[a-z0-9_-]`, hasta 32 caracteres, sin espacios ni mayúsculas ni
    tildes. Un nombre inválido es otro 400 que tumba el registro entero, así que
    se normaliza aquí: "jugador" pasa, "Nick del pro" no pasaría y se convierte
    en `nick-del-pro`.

    Se usa para las dos cosas —nombres de comando (`cmd.history.name`) y de
    opción (`cmd.history.arg`)— porque las reglas son las mismas y tener dos
    funciones idénticas era pedir que una se quedara sin arreglar.
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
# lleva —`/subscribe`, `/unsubscribe`, `/mute` y los dos de esports— no tiene
# ningún sentido fuera de uno: configura un canal de un servidor y su cerrojo es
# un permiso que en un DM no existe. Así que el alcance se **deriva** de eso en
# vez de declararse comando por comando: con `permiso`, solo servidor; sin
# `permiso`, en todas partes.
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
#: caso normal: todos los comandos de consulta (`/live`, `/player`, `/match`,
#: `/history`, `/team`, `/ranking`, `/help`...).
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


#: Permiso que se exige para cambiar la configuración del servidor (canales de
#: notificación). Está aquí para que los cuatro comandos que lo usan —dos de
#: SoloQ, dos de esports— no declaren cada uno el suyo.
PERMISO_ADMIN = nextcord.Permissions(manage_guild=True)


def _base(nombre: str, descripcion: str, permiso, alcance) -> tuple[str, str, dict]:
    """Lo que comparten las tres formas: nombre, descripción y ámbito.

    Sin localizaciones a propósito: el dueño pidió que la interfaz de comandos
    esté **solo en inglés** («que solo estén en inglés y se entiendan bien»), que
    es lo universal. El catálogo sigue guardando el español de cada cadena como
    documentación de qué significa, pero a Discord se le manda solo el inglés.
    """
    nombre_base, _locales = nombre_de(nombre)
    desc, _locales_desc = textos_de(descripcion)
    extra = {} if permiso is None else {"default_member_permissions": permiso}
    ambito = ambito_de(alcance or (SERVIDOR if permiso is not None else GLOBAL))
    return nombre_base, desc, {**extra, **ambito}


async def _frenar(interaction: nextcord.Interaction) -> bool:
    """Freno por usuario. Devuelve `True` si hay que cortar la respuesta.

    Va aquí, en los envoltorios de `slash`/`slash_texto`/`slash_opciones`, y no
    en cada comando: **todos los comandos pasan por estos tres sitios**, así que
    ponerlo en un sitio lo cubre todo y no hay forma de añadir un comando nuevo
    que se olvide de pasar por el freno.

    Corta **antes** de llamar al cuerpo del comando, que es el punto entero: si
    se frenara después, el gasto de cuota de Riot ya se habría hecho y no
    serviría de nada. Ver `utils/cooldown.py` para el porqué.

    Cuando frena, responde él y devuelve `True` para que el comando no siga. El
    mensaje dice cuántos segundos faltan: un «no» seco se lee como que el bot
    está roto.
    """
    from utils.cooldown import permitir

    espera = permitir(interaction.user.id)
    if espera <= 0:
        return False

    res = Respuesta(interaction)
    await res.error(res.traductor("freno.espera", segundos=max(1, round(espera))))
    return True


def slash(
    bot: commands.Bot,
    nombre: str,
    descripcion: str,
    cuerpo: CuerpoSimple,
    *,
    permiso: nextcord.Permissions | None = None,
    alcance: str | None = None,
) -> None:
    """Registra `/nombre`, sin argumentos.

    `nombre` y `descripcion` son claves del catálogo (`"cmd.live.name"`,
    `"cmd.live.desc"`).

    `permiso` añade `default_member_permissions`, que hace que Discord **ni le
    muestre el comando** a quien no lo tiene. Eso es interfaz, no seguridad: el
    cuerpo tiene que comprobarlo igual con `res.es_admin()`.

    `alcance` decide dónde se puede usar (`GLOBAL` o `SERVIDOR`). Por defecto se
    deriva de `permiso`: un comando con permisos de servidor solo tiene sentido
    dentro de uno. Ver el bloque de arriba.
    """
    nombre_base, desc, extra = _base(nombre, descripcion, permiso, alcance)

    @bot.slash_command(name=nombre_base, description=desc, **extra)
    async def _slash(interaction: nextcord.Interaction):  # noqa: ANN202
        if await _frenar(interaction):
            return
        await cuerpo(Respuesta(interaction))


def slash_texto(
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
    """Registra `/nombre <arg>`, con un argumento de texto libre.

    `nombre`, `descripcion`, `arg_nombre` y `arg_desc` son claves del catálogo.

    `requerido=False` deja el argumento opcional, que es lo que hace que
    `/history` sin nada siga dando el historial global.

    `alcance` por defecto es `GLOBAL`: todos los comandos con argumento de texto
    son de consulta (`/player`, `/match`, `/history`, `/team`, `/leagues`), y son
    justo los que el usuario pidió poder usar desde su propio chat.
    """
    nombre_base, desc, extra = _base(nombre, descripcion, None, alcance or GLOBAL)
    arg, _arg_locales = nombre_de(arg_nombre)
    ayuda, _ayuda_locales = textos_de(arg_desc)

    @bot.slash_command(name=nombre_base, description=desc, **extra)
    async def _slash(  # noqa: ANN202
        interaction: nextcord.Interaction,
        valor: str = SlashOption(
            name=arg,
            description=ayuda,
            required=requerido,
            **({} if requerido else {"default": ""}),
        ),
    ):
        if await _frenar(interaction):
            return
        await cuerpo(Respuesta(interaction), (valor or "").strip())


def slash_opciones(
    bot: commands.Bot,
    nombre: str,
    descripcion: str,
    cuerpo: Callable[[Respuesta, dict[str, str]], Awaitable[None]],
    *,
    opciones: tuple[tuple[str, str, tuple[str, ...], str | None], ...],
    permiso: nextcord.Permissions | None = None,
) -> None:
    """Registra `/nombre` con varias opciones de **lista cerrada**.

    Cada opción es `(clave_nombre, clave_descripcion, valores, por_defecto)`. Si
    `por_defecto` es `None` la opción es **obligatoria**; si no, es opcional y el
    cuerpo recibe ese valor cuando el usuario no la toca.

    `valores` puede ser tres cosas:

    * una **tupla** de valores (`("soloq", "esports")`), que sale como lista
      cerrada con la etiqueta igual al valor;
    * un **`dict`** `{etiqueta: valor}`, que es lo que permite que el desplegable
      enseñe `LEC · Europa` y mande `lec`;
    * **`None`**, que deja la opción como **texto libre**. Lo necesita
      `/subscribe`, donde el objetivo puede ser una liga, un equipo, un pro o una
      cuenta y no hay lista cerrada posible.

    Existe por dos motivos, y los dos son de diseño, no de comodidad:

    1. **Para no inventar nombres compuestos.** El dueño lo pidió así: «que se
       entienda su significado de una palabra… si es esports es solo esports, no
       esports-live». La diferencia entre dar avisos de SoloQ o de esports no es
       del comando, es de **qué** avisos, así que va en una opción
       (`/subscribe type: soloq|esports`) y el nombre se queda en una palabra.
    2. **Para filtrar sin gastar llamadas.** `/ranking lck mid 10` filtra la tabla
       que ya se ha pedido y que ya está en caché; `/live lck` filtra la caché de
       partidas que el barrido mantiene en memoria. Ninguna de las dos vuelve a
       llamar a nadie, y por eso se pueden ofrecer sin miedo al rate limit.

    Las listas cerradas (`choices`) son lo que hace que esto sea barato y seguro:
    Discord valida el valor antes de que llegue al bot, así que el cuerpo nunca
    tiene que defenderse de basura.

    El cuerpo recibe `{clave: valor}` con los nombres ya saneados. Las claves son
    los **nombres reales de la opción** (`league`, `role`, `top`), no los del
    catálogo, para que el cuerpo lea lo mismo que ve el usuario.
    """
    nombre_base, desc, extra = _base(nombre, descripcion, permiso, None)

    # Se resuelve cada opción una vez: nombre real, ayuda, lista para Discord y
    # valores válidos. `valores` admite tupla (la etiqueta es el valor) o dict
    # `{etiqueta: valor}`, que es lo que deja enseñar `LEC · Europa` y mandar `lec`.
    specs: list[tuple[str, str, object, tuple[str, ...], str | None]] = []
    for clave_nombre, clave_desc, valores, por_defecto in opciones:
        op, _loc = nombre_de(clave_nombre)
        ayuda, _ayuda_loc = textos_de(clave_desc)
        if valores is None:
            # Texto libre: sin `choices` y sin validar contra nada.
            specs.append((op, ayuda, None, None, por_defecto))
        elif isinstance(valores, dict):
            specs.append((op, ayuda, dict(valores), tuple(valores.values()), por_defecto))
        else:
            tupla = tuple(valores)
            specs.append((op, ayuda, list(tupla), tupla, por_defecto))

    async def _slash(interaction: nextcord.Interaction, **valores: str):  # noqa: ANN202
        if await _frenar(interaction):
            return
        elegidos: dict[str, str] = {}
        for i, (op, _ayuda, _discord, validos, por_defecto) in enumerate(specs):
            valor = (valores.get(f"valor_{i}") or "").strip()
            if valor and validos is not None and valor not in validos:
                # Discord valida las `choices`, así que esto no debería pasar; se
                # cae al valor por defecto en vez de propagar basura al cuerpo.
                log.warning("Opción fuera de la lista en /%s: %s=%r", nombre_base, op, valor)
                valor = ""
            elegidos[op] = valor or (por_defecto or "")
        await cuerpo(Respuesta(interaction), elegidos)

    # La firma se compone **antes** de registrar, no después: nextcord construye
    # el comando leyendo `inspect.signature(callback)`, e `inspect` respeta un
    # `__signature__` puesto a mano. Registrar primero y parchear la firma luego
    # dejaría el payload ya construido, sin las opciones.
    #
    # Los parámetros se llaman `valor_0`, `valor_1`… y **no** como la opción: el
    # nombre de una opción de Discord admite guiones (`channel-add`) y un guion no
    # es un nombre de parámetro válido en Python. El nombre de verdad va en
    # `SlashOption(name=...)`, que es lo que viaja a Discord.
    _slash.__signature__ = inspect.Signature(
        [inspect.Parameter("interaction", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        + [
            inspect.Parameter(
                f"valor_{i}",
                inspect.Parameter.KEYWORD_ONLY,
                default=SlashOption(
                    name=op,
                    description=ayuda,
                    # Sin `choices` cuando es texto libre: pasar `None` explícito
                    # es lo que nextcord espera para una opción de texto.
                    **({} if discord is None else {"choices": discord}),
                    required=por_defecto is None,
                    **({} if por_defecto is None else {"default": por_defecto}),
                ),
            )
            for i, (op, ayuda, discord, _validos, por_defecto) in enumerate(specs)
        ]
    )
    _slash.__name__ = f"slash_{nombre_base}"
    bot.slash_command(name=nombre_base, description=desc, **extra)(_slash)


def slash_opciones_cog(
    cog: commands.Cog,
    bot: commands.Bot,
    nombre: str,
    descripcion: str,
    cuerpo: Callable[[Respuesta, dict[str, str]], Awaitable[None]],
    *,
    opciones: tuple[tuple[str, str, object, str | None], ...],
    permiso: nextcord.Permissions | None = None,
) -> None:
    """Igual que `slash_opciones`, pero para comandos que viven dentro de un Cog.

    Existe por lo mismo que `slash_cog`: los comandos de esports necesitan el
    `TrackerService` de la instancia, y nextcord exige `self` en los comandos
    declarados dentro de una clase. El `cog` no se usa aquí; está en la firma
    para que en la llamada se vea a quién pertenece el comando.
    """
    slash_opciones(bot, nombre, descripcion, cuerpo, opciones=opciones, permiso=permiso)


def slash_cog(
    cog: commands.Cog,
    bot: commands.Bot,
    nombre: str,
    descripcion: str,
    cuerpo: CuerpoSimple,
    *,
    permiso: nextcord.Permissions | None = None,
    alcance: str | None = None,
) -> None:
    """Igual que `slash`, pero para comandos que viven dentro de un Cog.

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
    slash(bot, nombre, descripcion, cuerpo, permiso=permiso, alcance=alcance)

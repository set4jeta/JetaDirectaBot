"""`!help` / `/help` — la lista de comandos.

Por qué se reescribió
---------------------
Era el archivo más desactualizado del bot y el primero que lee alguien que
acaba de invitarlo:

1. **Anunciaba solo la forma `!`.** Tras la migración a slash, todos los
   comandos existen en las dos formas, y la que Discord autocompleta es `/`.
2. **No mencionaba el selector de liga de `/ranking`.** Decía "`!ranking` -
   Muestra la tabla de clasificación", sin decir que hay una liga por región.
3. **Se partía a lo bruto cada 1900 caracteres** (`help_text[i:i+max_len]`), lo
   que cortaba a mitad de línea y a veces a mitad de palabra.
4. **Mentía sobre los permisos**: ponía "(solo admin)" cuando no había ninguna
   comprobación. Eso ya se arregló en `notification_config_commands.py`; aquí
   solo hacía falta que el texto siguiera siendo cierto.
5. **Solo existía en español.** Ahora hay versión inglesa y sale la del idioma
   que el servidor haya elegido con `/lang`.

Se manda como embed, que es lo que se espera de un bot moderno y además evita el
troceado. Si al bot le falta el permiso *Insertar enlaces* el embed no llega, así
que hay respaldo en texto plano: antes eso habría sido un `!help` que no
responde nada, el peor fallo posible en el comando de ayuda.

Por qué las secciones no están en `utils/i18n.py`
------------------------------------------------
El catálogo de i18n es para cadenas cortas que aparecen en muchos sitios. La
ayuda es un bloque largo con su propia estructura, y meterla ahí como 40 claves
sueltas haría ilegibles las dos cosas. Vive aquí, con la misma forma en los dos
idiomas.
"""

from __future__ import annotations

import nextcord
from nextcord.ext import commands

from apis.dpm_api import LIGAS
from core.dual_command import dual
from core.responder import Respuesta
from utils.branding import descargo_riot, enlaces
from utils.i18n import IDIOMA_POR_DEFECTO, idioma_de
from utils.logger import get_logger

log = get_logger("core.help")

COLOR = 0x1F8B4C

#: Códigos de liga que acepta `/ranking`, sacados del backend para que no haya
#: que tocar la ayuda cada vez que se añada una liga.
_CODIGOS_LIGA = ", ".join(f"`{c}`" for c in LIGAS)

Seccion = tuple[str, tuple[str, ...]]

_SECCIONES_ES: tuple[Seccion, ...] = (
    (
        "🎮 Partidas en vivo",
        (
            "**/live** — todos los jugadores trackeados que están en partida ahora mismo.",
            "**/match** `jugador` — la partida en vivo de un jugador concreto. Ej: `/match elk`",
            "**/info** `jugador` — datos del jugador: cuentas, elo y partida actual si la hay. Ej: `/info Elyoya`",
        ),
    ),
    (
        "📊 Datos y clasificación",
        (
            f"**/ranking** `liga` — tabla de SoloQ de una liga. Ligas: {_CODIGOS_LIGA}",
            "**/historial** — últimas partidas trackeadas de todos.",
            "**/historial** `jugador` — últimas partidas de un jugador o de una cuenta suya.",
            "**/team** `equipo` — jugadores de un equipo. Ej: `/team g2`, `/team fnc`",
        ),
    ),
    (
        "🏆 Esports (todas las ligas)",
        (
            "**/partida** — partidos profesionales en vivo o a punto de empezar.",
            "**/next** — horario de los próximos partidos.",
        ),
    ),
    (
        "🔔 Avisos para ti (chat privado)",
        (
            "**/seguir** `Elyoya` — te aviso por privado cuando ese pro entre en SoloQ.",
            "**/seguir** `lec` — todas las partidas de SoloQ de una liga entera.",
            "**/dejarseguir** `Elyoya` — quitar uno. `/dejarseguir todo` borra todo.",
            "**/misavisos** — a quién sigues y si puedo escribirte por privado.",
            "_Estos funcionan aunque el bot no esté en tu servidor: añádelo a tu "
            "cuenta y los tendrás en cualquier chat._",
        ),
    ),
    (
        "⚙️ Configuración · requiere *Gestionar servidor*",
        (
            "**/ligas** — ver las ligas que sigue el servidor. Con argumentos las cambia: `/ligas lec lck`",
            "**/lang** — idioma del bot en este servidor: `/lang en`",
            "**/setchannel** — **añadir** este canal a las notificaciones de SoloQ.",
            "**/canales** — ver los canales de avisos de SoloQ y cuántos caben.",
            "**/quitarcanal** — quitar solo este canal de las notificaciones.",
            "**/unsubscribe** — dejar de recibir notificaciones de SoloQ en todo el servidor.",
            "**/setlivechannel** — usar este canal para las notificaciones de esports.",
            "**/removelivechannel** — dejar de recibir notificaciones de esports.",
        ),
    ),
    (
        "🩺 Estado",
        (
            "**/health** — si las fuentes de datos van bien y cuándo se "
            "actualizaron por última vez. Úsalo si algo parece desfasado.",
            "**/premium** — cupos de este servidor y cómo apoyar el proyecto.",
        ),
    ),
)

_SECCIONES_EN: tuple[Seccion, ...] = (
    (
        "🎮 Live games",
        (
            "**/live** — every tracked player currently in a game.",
            "**/match** `player` — the live game of one player. E.g. `/match elk`",
            "**/info** `player` — player details: accounts, rank and current game if any. E.g. `/info Elyoya`",
        ),
    ),
    (
        "📊 Stats and standings",
        (
            f"**/ranking** `league` — SoloQ table for a league. Leagues: {_CODIGOS_LIGA}",
            "**/historial** — latest tracked games from everyone.",
            "**/historial** `player` — latest games of a player or one of their accounts.",
            "**/team** `team` — players on a team. E.g. `/team g2`, `/team fnc`",
        ),
    ),
    (
        "🏆 Esports (all leagues)",
        (
            "**/partida** — pro matches live or about to start.",
            "**/next** — schedule for upcoming matches.",
        ),
    ),
    (
        "🔔 Alerts for you (DMs)",
        (
            "**/seguir** `Elyoya` — I'll DM you when that pro starts a SoloQ game.",
            "**/seguir** `lec` — every SoloQ game from a whole league.",
            "**/dejarseguir** `Elyoya` — remove one. `/dejarseguir all` removes everything.",
            "**/misavisos** — who you follow and whether I can DM you.",
            "_These work even if the bot isn't on your server: add it to your "
            "account and you'll have them in any chat._",
        ),
    ),
    (
        "⚙️ Settings · requires *Manage Server*",
        (
            "**/ligas** — see the leagues this server tracks. With arguments it changes them: `/ligas lec lck`",
            "**/lang** — bot language on this server: `/lang es`",
            "**/setchannel** — **add** this channel to the SoloQ notifications.",
            "**/canales** — see the SoloQ alert channels and how many fit.",
            "**/quitarcanal** — remove just this channel from the notifications.",
            "**/unsubscribe** — stop receiving SoloQ notifications server-wide.",
            "**/setlivechannel** — use this channel for esports notifications.",
            "**/removelivechannel** — stop receiving esports notifications.",
        ),
    ),
    (
        "🩺 Status",
        (
            "**/health** — whether the data sources are healthy and when they "
            "last updated. Use it if something looks stale.",
            "**/premium** — this server's limits and how to support the project.",
        ),
    ),
)

_TEXTOS = {
    "es": {
        "titulo": "📘 Comandos de JetaDirectaBot",
        "descripcion": "Seguimiento de SoloQ y partidos profesionales de League of Legends.",
        "notas_titulo": "ℹ️ Notas",
        "notas": (
            "Los comandos antiguos con `!` siguen funcionando igual (`!live`, `!ranking`...), "
            "pero `/` te los autocompleta.\n"
            "⏰ Las horas se muestran en tu zona horaria local automáticamente.\n"
            "⚠️ Si ves un aviso de *rate limit*, Riot está limitando las peticiones y el bot "
            "responde con datos de respaldo; se actualizan en pocos segundos."
        ),
        "enlaces_titulo": "🔗 Enlaces",
        "legal_titulo": "📄 Aviso legal",
        "secciones": _SECCIONES_ES,
    },
    "en": {
        "titulo": "📘 JetaDirectaBot commands",
        "descripcion": "SoloQ and pro match tracking for League of Legends.",
        "notas_titulo": "ℹ️ Notes",
        "notas": (
            "The old `!` commands still work the same (`!live`, `!ranking`...), "
            "but `/` autocompletes them for you.\n"
            "⏰ Times are shown in your local timezone automatically.\n"
            "⚠️ If you see a *rate limit* warning, Riot is throttling requests and the bot "
            "falls back to cached data; it refreshes within seconds."
        ),
        "enlaces_titulo": "🔗 Links",
        "legal_titulo": "📄 Legal notice",
        "secciones": _SECCIONES_EN,
    },
}


def construir_embed(idioma: str = IDIOMA_POR_DEFECTO) -> nextcord.Embed:
    """El embed de ayuda. Función aparte para poder comprobarla sin Discord."""
    textos = _TEXTOS.get(idioma) or _TEXTOS[IDIOMA_POR_DEFECTO]
    embed = nextcord.Embed(
        title=textos["titulo"],
        description=textos["descripcion"],
        color=COLOR,
    )
    for titulo, lineas in textos["secciones"]:
        embed.add_field(name=titulo, value="\n".join(lineas), inline=False)
    embed.add_field(name=textos["notas_titulo"], value=textos["notas"], inline=False)

    # Los enlaces solo salen si están configurados (`enlaces()` filtra los
    # vacíos): un campo "Web: " sin URL queda peor que no tenerlo.
    lineas_enlaces = enlaces(idioma)
    if lineas_enlaces:
        embed.add_field(
            name=textos["enlaces_titulo"],
            value="\n".join(lineas_enlaces),
            inline=False,
        )

    # El descargo obligatorio de Riot va aquí, completo. `/help` es el sitio
    # "readily visible to players" que pide la política; el embed de partida
    # lleva solo la versión corta en el pie para no tapar el contenido.
    embed.add_field(
        name=textos["legal_titulo"],
        value=descargo_riot(idioma),
        inline=False,
    )
    return embed


def construir_texto(idioma: str = IDIOMA_POR_DEFECTO) -> str:
    """Misma ayuda en texto plano, para cuando el embed no se puede mandar."""
    textos = _TEXTOS.get(idioma) or _TEXTOS[IDIOMA_POR_DEFECTO]
    partes = [f"**{textos['titulo']}**"]
    for titulo, lineas in textos["secciones"]:
        partes.append(f"\n**{titulo}**")
        partes.extend(lineas)
    partes.append(f"\n{textos['notas']}")

    lineas_enlaces = enlaces(idioma)
    if lineas_enlaces:
        partes.append(f"\n**{textos['enlaces_titulo']}**")
        partes.extend(lineas_enlaces)

    # El respaldo en texto también lleva el descargo: si el embed no se puede
    # mandar, esto es *toda* la ayuda que ve el usuario, y la obligación legal
    # no depende de que el bot tenga permiso para insertar enlaces.
    partes.append(f"\n**{textos['legal_titulo']}**")
    partes.append(descargo_riot(idioma))
    return "\n".join(partes)


async def _cuerpo_help(res: Respuesta) -> None:
    idioma = idioma_de(res.guild_id)
    try:
        await res.send(embed=construir_embed(idioma))
        return
    except nextcord.Forbidden:
        # Falta "Insertar enlaces" en este canal. Sin este respaldo, el comando
        # de ayuda sería justo el que no contesta.
        log.info("Sin permiso para embeds en %s; mando la ayuda en texto.", res.canal_id)
    except nextcord.HTTPException as exc:
        log.warning("Fallo mandando el embed de ayuda: %s", exc)

    await res.enviar_partido(construir_texto(idioma))


def register_help_command(bot: commands.Bot) -> None:
    dual(bot, "help", "cmd.help.desc", _cuerpo_help)

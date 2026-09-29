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
from core.dual_command import slash
from core.responder import Respuesta
from utils.branding import COLOR_MARCA, enlaces
from utils.i18n import IDIOMA_POR_DEFECTO, idioma_de
from utils.logger import get_logger

log = get_logger("core.help")

#: El color del embed de `/help`: el oro de la marca (ver `branding.COLOR_MARCA`).
#: Estuvo en verde (0x1F8B4C) hasta el 22-09-2026, de cuando la web también era
#: verde; con el logotipo en oro, un `/help` verde es la pieza que más chirría
#: porque es la primera que ve quien instala el bot.
COLOR = COLOR_MARCA

#: Códigos de liga que acepta `/ranking`, sacados del backend para que no haya
#: que tocar la ayuda cada vez que se añada una liga.
_CODIGOS_LIGA = ", ".join(f"`{c}`" for c in LIGAS)

Seccion = tuple[str, tuple[str, ...]]

_SECCIONES_ES: tuple[Seccion, ...] = (
    (
        "🎮 Partidas de SoloQ en vivo",
        (
            "**/live** — todos los pros seguidos que están en partida ahora mismo. Con liga, solo esa: `/live lck`",
            "**/match** `jugador` — la partida en vivo de un pro, con los diez participantes. Ej: `/match elk`",
            "**/info** `jugador` — su ficha: equipo, elo y partida actual. Ej: `/info Elyoya`",
        ),
    ),
    (
        "📊 Datos y clasificación",
        (
            f"**/ranking** `liga` — tabla de SoloQ de una liga. Ligas: {_CODIGOS_LIGA}",
            "**/ranking** `liga` `rol` `limite` — filtros sobre esa tabla: `/ranking lck mid limit:10`",
            "**/history** — últimas partidas seguidas de todos.",
            "**/history** `liga`, `jugador` o `cuenta` — las de esa liga (`/history lec`), ese pro o esa cuenta (`/history Caps#EUW`).",
            "**/team** `equipo` — plantilla de un equipo. Ej: `/team g2`, `/team fnc`",
        ),
    ),
    (
        "🏆 Esports (partidos oficiales)",
        (
            "**/esports** — partidos profesionales en vivo o a punto de empezar. Con liga, solo esa: `/esports lec`",
            "**/schedule** — calendario de los próximos partidos.",
        ),
    ),
    (
        "🔔 Avisos para ti (chat privado)",
        (
            "**/track** `Elyoya` — te aviso por privado cuando ese pro entre en SoloQ.",
            "**/track** `lec` — todas las partidas de SoloQ de una liga entera.",
            "**/untrack** `Elyoya` — quitar uno. `/untrack all` borra todo.",
            "**/following** — a quién sigues y si puedo escribirte por privado.",
            "_Estos funcionan aunque el bot no esté en tu servidor: añádelo a tu "
            "cuenta y los tendrás en cualquier chat._",
        ),
    ),
    (
        "⚙️ Configuración · requiere *Gestionar servidor*",
        (
            "**/subscribe** — **añadir** este canal a los avisos. Con objetivo, **solo** eso: `/subscribe soloq lck`, `/subscribe esports lck`, `/subscribe soloq Elyoya`.",
            "**/channels** — ver los canales con avisos y cuántos caben.",
            "**/unsubscribe** — quitar solo este canal de los avisos.",
            "**/mute** — apagar los avisos en todo el servidor.",
            "**/leagues** `lec lck` — cambiar las ligas que sigue el servidor.",
            "**/language** `code:en` — idioma del bot aquí.",
        ),
    ),
    (
        "🩺 Estado",
        (
            "**/health** — si las fuentes de datos van bien y cuándo se "
            "actualizaron por última vez. Úsalo si algo parece desfasado.",
            "**/premium** — los cupos de este servidor, de dónde salen (la "
            "cuota de Riot) y cómo subirlos entre todos.",
        ),
    ),
)
_SECCIONES_EN: tuple[Seccion, ...] = (
    (
        "🎮 Live SoloQ games",
        (
            "**/live** — every tracked pro currently in a game. With a league, just that one: `/live lck`",
            "**/match** `player` — one pro's live game, with all ten participants. E.g. `/match elk`",
            "**/info** `player` — their profile: team, rank and current game. E.g. `/info Elyoya`",
        ),
    ),
    (
        "📊 Stats and standings",
        (
            f"**/ranking** `league` — SoloQ leaderboard for a league. Leagues: {_CODIGOS_LIGA}",
            "**/ranking** `league` `role` `limit` — filters on that table: `/ranking lck mid limit:10`",
            "**/history** — latest tracked games from everyone.",
            "**/history** `league`, `player` or `account` — those of a league (`/history lec`), a pro or one of their accounts (`/history Caps#EUW`).",
            "**/team** `team` — a team's roster. E.g. `/team g2`, `/team fnc`",
        ),
    ),
    (
        "🏆 Esports (official matches)",
        (
            "**/esports** — pro matches live or about to start. With a league, just that one: `/esports lec`",
            "**/schedule** — schedule of the upcoming matches.",
        ),
    ),
    (
        "🔔 Alerts for you (DMs)",
        (
            "**/track** `Elyoya` — I'll DM you when that pro starts a SoloQ game.",
            "**/track** `lec` — every SoloQ game from a whole league.",
            "**/untrack** `Elyoya` — remove one. `/untrack all` removes everything.",
            "**/following** — who you follow and whether I can DM you.",
            "_These work even if the bot isn't on your server: add it to your "
            "account and you'll have them in any chat._",
        ),
    ),
    (
        "⚙️ Settings · requires *Manage Server*",
        (
            "**/subscribe** — **add** this channel to the alerts. With a target, **only** that: `/subscribe soloq lck`, `/subscribe esports lck`, `/subscribe soloq Elyoya`.",
            "**/channels** — see the alert channels and how many fit.",
            "**/unsubscribe** — remove just this channel from the alerts.",
            "**/mute** — turn off the alerts for the whole server.",
            "**/leagues** `lec lck` — change the leagues this server tracks.",
            "**/language** `code:es` — bot language here.",
        ),
    ),
    (
        "🩺 Status",
        (
            "**/health** — whether the data sources are healthy and when they "
            "last updated. Use it if something looks stale.",
            "**/premium** — this server's limits, where they come from (Riot's "
            "quota) and how everyone can raise them.",
        ),
    ),
)
_TEXTOS = {
    "es": {
        "titulo": "📘 Comandos de LoLProTrackr",
        "descripcion": "Seguimiento de SoloQ y partidos profesionales de League of Legends.",
        "notas_titulo": "ℹ️ Notas",
        "notas": (
            "Los comandos están **en inglés** (`/player`, `/history`, `/esports`), "
            "que es lo que se entiende en cualquier servidor. Lo que cambia con "
            "`/language` es lo que te contesto yo, no sus nombres.\n"
            "⏰ Las horas se muestran en tu zona horaria local automáticamente.\n"
            "⚠️ Si ves un aviso de *rate limit*, Riot está limitando las peticiones y el bot "
            "responde con datos de respaldo; se actualizan en pocos segundos."
        ),
        "enlaces_titulo": "🔗 Enlaces",
        "secciones": _SECCIONES_ES,
    },
    "en": {
        "titulo": "📘 LoLProTrackr commands",
        "descripcion": "SoloQ and pro match tracking for League of Legends.",
        "notas_titulo": "ℹ️ Notes",
        "notas": (
            "Commands are in **English** (`/player`, `/history`, `/esports`), which "
            "works in any server. `/language` changes what I reply, not the command "
            "names.\n"
            "⏰ Times are shown in your local timezone automatically.\n"
            "⚠️ If you see a *rate limit* warning, Riot is throttling requests and the bot "
            "falls back to cached data; it refreshes within seconds."
        ),
        "enlaces_titulo": "🔗 Links",
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

    # El descargo obligatorio de Riot que había aquí se quitó el 22-09-2026 por
    # instrucción del dueño: leerlo le parecía que Riot rechazaba el bot. Ver la
    # nota de `utils/branding.py`.
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

    # El respaldo en texto plano llevaba aquí el descargo de Riot; se quitó
    # junto con el del embed (22-09-2026, instrucción del dueño).
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
    slash(bot, "cmd.help.name", "cmd.help.desc", _cuerpo_help)

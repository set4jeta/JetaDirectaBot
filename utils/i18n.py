"""Traducciones del bot (español e inglés).

Cómo se usa
-----------
    from utils.i18n import tr

    _ = tr(interaccion.guild_id)     # o tr(res.guild_id)
    await res.send(_("setchannel.ok", canal=canal.mention))

`tr()` devuelve una función ya atada al idioma de ese servidor, así que el
cuerpo del comando no va arrastrando el idioma por todas partes.

Reglas que importan
-------------------
1. **Una clave que no existe no puede romper un comando.** Si falta la clave o
   falta el idioma, se cae al español y, si tampoco está, se devuelve la propia
   clave. Prefiero que el usuario lea `setchannel.ok` a que el comando lance
   `KeyError` en un `except` que nadie mira.

2. **Español es el idioma de referencia.** Si una traducción al inglés se
   añade a medias, lo que falte sale en español, no vacío.

3. Nada de esto es thread-safety crítico: el JSON se lee en cada consulta de
   idioma porque se toca muy poco (arranque y `/lang`), y así un cambio hecho
   a mano en el fichero se ve sin reiniciar.
"""

from __future__ import annotations

import json
import os
from typing import Any

from utils.logger import get_logger

log = get_logger("utils.i18n")

_IDIOMAS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tracking", "soloq", "idiomas_config.json",
)

IDIOMA_POR_DEFECTO = "es"

#: Idiomas que se ofrecen. La clave es lo que se guarda y lo que acepta `/lang`.
IDIOMAS: dict[str, str] = {
    "es": "Español",
    "en": "English",
}

# ---------------------------------------------------------------------- #
# Localización de los comandos en la interfaz de Discord
# ---------------------------------------------------------------------- #
#
# Son DOS capas distintas y conviene no confundirlas:
#
# 1. **El cuerpo de la respuesta** va en el idioma del *servidor* (`/lang`),
#    porque un aviso de partida lo leen todos los del canal.
# 2. **El nombre y la descripción que Discord muestra en el selector de
#    comandos** los localiza Discord con el idioma del *cliente de cada
#    usuario*, y eso no lo decide el bot. Un inglés dentro de un servidor en
#    español ve `/leagues` en su lista aunque las respuestas salgan en español.
#
# Por eso el idioma base de los comandos es el inglés: Discord usa el campo
# `description` para cualquier locale que no esté en `description_localizations`,
# así que con el inglés de base quedan cubiertos de golpe los 30 idiomas que no
# se traducen. Antes la descripción base era española y un usuario alemán o
# coreano veía "Ver o elegir qué ligas sigue este servidor".
IDIOMA_BASE_DISCORD = "en"

#: A qué locales de Discord se manda cada idioma del bot.
#:
#: El español lleva dos: `es-ES` y `es-419` (Latinoamérica). Discord los trata
#: como locales separados, así que sin `es-419` un mexicano o un argentino —el
#: público de la LLA— recibiría la descripción en inglés.
LOCALES_DISCORD: dict[str, tuple[str, ...]] = {
    "es": ("es-ES", "es-419"),
}

#: Tope de Discord para la descripción de un comando o de una opción.
#: Pasarse **no** es un aviso: Discord rechaza el despliegue entero con un 400 y
#: el bot se queda sin ningún slash command. Lo comprueba
#: `scripts/test_slash_locale.py`.
MAX_DESCRIPCION = 100
MAX_NOMBRE = 32


def texto_base(clave: str) -> str:
    """La descripción que Discord usa como respaldo para todos los locales."""
    return t(clave, IDIOMA_BASE_DISCORD)


def localizaciones(clave: str) -> dict[str, str]:
    """`{locale_de_discord: texto}` de todos los idiomas que no son el base.

    Una clave que no existe devuelve `{}` en vez de propagar la clave cruda a
    Discord: es mejor que un comando salga solo en inglés que un comando que en
    español se llame `cmd.ligas.desc`.
    """
    salida: dict[str, str] = {}
    for idioma, locales in LOCALES_DISCORD.items():
        if idioma == IDIOMA_BASE_DISCORD:
            continue
        texto = t(clave, idioma)
        if not texto or texto == clave:
            continue
        for locale in locales:
            salida[locale] = texto
    return salida

# ---------------------------------------------------------------------- #
# Catálogo
# ---------------------------------------------------------------------- #

_CATALOGO: dict[str, dict[str, str]] = {
    # ---- Configuración de notificaciones ----
    "setchannel.ok": {
        "es": "✅ Canal de notificaciones de SoloQ establecido en {canal}{aviso}",
        "en": "✅ SoloQ notification channel set to {canal}{aviso}",
    },
    "setchannel.sin_permisos_canal": {
        "es": "\n⚠️ Al bot le faltan permisos aquí: {permisos}. Las notificaciones "
              "no se verán hasta que se los des.",
        "en": "\n⚠️ The bot is missing permissions here: {permisos}. "
              "Notifications won't show until you grant them.",
    },
    "setchannel.este_canal": {"es": "este canal", "en": "this channel"},
    "setchannel.ya_estaba": {
        "es": "ℹ️ {canal} ya recibía las notificaciones de SoloQ.",
        "en": "ℹ️ {canal} was already receiving SoloQ notifications.",
    },
    # El mensaje de cupo lleva la lista de canales que lo ocupan: sin ella el
    # admin no sabe cuál quitar y el error no tiene salida.
    "setchannel.cupo": {
        "es": "❌ Tu plan permite {n} canal(es) de avisos y ya los estás usando: "
              "{canales}.\nQuita uno con `/quitarcanal` en ese canal, o mira "
              "`/premium` para subir el cupo.",
        "en": "❌ Your plan allows {n} alert channel(s) and they're all in use: "
              "{canales}.\nRemove one with `/quitarcanal` in that channel, or "
              "check `/premium` to raise the limit.",
    },
    "setchannel.cuenta": {
        "es": "📻 Canales de avisos: {usados}/{tope}.",
        "en": "📻 Alert channels: {usados}/{tope}.",
    },
    "unsubscribe.ok": {
        "es": "✅ Notificaciones de SoloQ desactivadas para este servidor.",
        "en": "✅ SoloQ notifications disabled for this server.",
    },
    "unsubscribe.no_habia": {
        "es": "ℹ️ Este servidor no tenía ningún canal de notificaciones de SoloQ.",
        "en": "ℹ️ This server had no SoloQ notification channels.",
    },
    "setchannel.solo_admin_extra": {
        "es": "Necesitas el permiso **Gestionar servidor** para cambiar el canal "
              "de notificaciones.",
        "en": "You need the **Manage Server** permission to change the "
              "notification channel.",
    },
    "permisos.enviar_mensajes": {"es": "Enviar mensajes", "en": "Send Messages"},
    "permisos.insertar_enlaces": {"es": "Insertar enlaces", "en": "Embed Links"},
    "permisos.adjuntar_archivos": {"es": "Adjuntar archivos", "en": "Attach Files"},

    # ---- /canales ----
    "canales.titulo": {
        "es": "📻 Canales de notificación de SoloQ",
        "en": "📻 SoloQ notification channels",
    },
    "canales.activos": {
        "es": "**En uso ({n}/{tope}):** {canales}",
        "en": "**In use ({n}/{tope}):** {canales}",
    },
    "canales.inactivos": {
        "es": "**Guardados pero fuera de cupo:** {canales}\n"
              "_(no se borran: si subes de plan vuelven a funcionar)_",
        "en": "**Saved but over the limit:** {canales}\n"
              "_(not deleted: they work again if you upgrade)_",
    },
    "canales.como_usar": {
        "es": "Usa `/setchannel` en un canal para añadirlo y `/quitarcanal` para "
              "quitarlo. `/unsubscribe` los quita todos.",
        "en": "Use `/setchannel` in a channel to add it and `/quitarcanal` to "
              "remove it. `/unsubscribe` removes them all.",
    },
    "canales.quitado": {
        "es": "✅ {canal} ya no recibirá notificaciones de SoloQ.",
        "en": "✅ {canal} will no longer receive SoloQ notifications.",
    },
    "canales.no_estaba": {
        "es": "ℹ️ {canal} no estaba en la lista de notificaciones.",
        "en": "ℹ️ {canal} wasn't on the notification list.",
    },

    # ---- Errores comunes ----
    "error.solo_en_servidor": {
        "es": "❌ Este comando solo puede usarse en un servidor.",
        "en": "❌ This command can only be used inside a server.",
    },
    "error.solo_admin": {
        "es": "❌ Necesitas el permiso **Gestionar servidor**.",
        "en": "❌ You need the **Manage Server** permission.",
    },
    "error.generico": {
        "es": "❌ Algo ha ido mal: {detalle}",
        "en": "❌ Something went wrong: {detalle}",
    },

    # ---- /ligas ----
    "ligas.titulo": {"es": "🏆 Ligas en seguimiento", "en": "🏆 Tracked leagues"},
    "ligas.actuales": {
        "es": "**Ahora mismo sigues:** {ligas}",
        "en": "**Currently tracking:** {ligas}",
    },
    "ligas.disponibles": {
        "es": "**Disponibles:** {ligas}",
        "en": "**Available:** {ligas}",
    },
    "ligas.maximo": {
        "es": "Máximo {maximo} liga(s) por servidor.",
        "en": "Maximum {maximo} league(s) per server.",
    },
    "ligas.como_usar": {
        "es": "Usa `/ligas lck lcs` para cambiar la selección.",
        "en": "Use `/ligas lck lcs` to change your selection.",
    },
    "ligas.actualizado": {
        "es": "✅ Ahora sigues: {ligas}",
        "en": "✅ Now tracking: {ligas}",
    },
    "ligas.desconocidas": {
        "es": "⚠️ No conozco estas ligas: {ligas}",
        "en": "⚠️ Unknown leagues: {ligas}",
    },
    "ligas.truncado": {
        "es": "⚠️ El máximo son {maximo} ligas; se han guardado las {maximo} primeras.",
        "en": "⚠️ The limit is {maximo} leagues; only the first {maximo} were saved.",
    },
    # Recortar por plan y recortar por el límite físico se dicen distinto a
    # propósito: lo primero se arregla con `/premium`, lo segundo no se arregla.
    "ligas.truncado_plan": {
        "es": "⚠️ Tu plan permite {maximo} liga(s) a la vez, así que se usan las "
              "{maximo} primeras. Las demás quedan guardadas: mira `/premium`.",
        "en": "⚠️ Your plan allows {maximo} league(s) at once, so the first "
              "{maximo} are in use. The rest stay saved: see `/premium`.",
    },
    "ligas.fuera_de_cupo": {
        "es": "**Elegidas pero fuera de cupo:** {ligas}\n"
              "_(no se borran: si subes de plan vuelven a seguirse)_",
        "en": "**Selected but over the limit:** {ligas}\n"
              "_(not deleted: they resume if you upgrade)_",
    },
    "ligas.no_reconocidas": {
        "es": "❌ No reconozco ninguna de esas ligas. Prueba `/ligas` sin argumentos "
              "para ver la lista.",
        "en": "❌ I don't recognise any of those leagues. Try `/ligas` with no "
              "arguments to see the list.",
    },
    "ligas.nota_plataforma": {
        "es": "_(sin seguimiento en vivo: Riot no expone estos servidores)_",
        "en": "_(no live tracking: Riot does not expose these servers)_",
    },

    # ---- /ranking ----
    "ranking.liga_desconocida": {
        "es": "❌ Liga desconocida: `{liga}`.\nDisponibles: {disponibles}",
        "en": "❌ Unknown league: `{liga}`.\nAvailable: {disponibles}",
    },
    "ranking.calculando": {
        "es": "⏳ Calculando el ranking de {liga}...",
        "en": "⏳ Building the {liga} ranking...",
    },
    "ranking.sin_datos": {
        "es": "❌ No se pudo obtener el ranking de {liga}. La fuente no respondió; "
              "inténtalo en unos minutos.",
        "en": "❌ Couldn't fetch the {liga} ranking. The source didn't respond; "
              "try again in a few minutes.",
    },
    "ranking.titulo": {
        "es": "**📊 Ranking SoloQ · {liga}** · {total} jugadores",
        "en": "**📊 SoloQ ranking · {liga}** · {total} players",
    },
    "ranking.col_pos": {"es": "Pos", "en": "#"},
    "ranking.col_jugador": {"es": "Jugador", "en": "Player"},
    "ranking.col_equipo": {"es": "Equipo", "en": "Team"},
    "ranking.col_rol": {"es": "Rol", "en": "Role"},
    "ranking.col_rango": {"es": "Rango", "en": "Rank"},
    "ranking.col_lp": {"es": "LP", "en": "LP"},
    "ranking.col_winrate": {"es": "Winrate", "en": "Winrate"},
    "ranking.col_kda": {"es": "KDA", "en": "KDA"},
    "ranking.col_champs": {"es": "Champs", "en": "Champs"},

    # ---- /lang ----
    "lang.titulo": {"es": "🌐 Idioma", "en": "🌐 Language"},
    "lang.actual": {
        "es": "El idioma de este servidor es **{idioma}**.",
        "en": "This server's language is **{idioma}**.",
    },
    "lang.opciones": {
        "es": "Disponibles: {opciones}",
        "en": "Available: {opciones}",
    },
    "lang.cambiado": {
        "es": "✅ Idioma cambiado a **{idioma}**.",
        "en": "✅ Language switched to **{idioma}**.",
    },
    "lang.desconocido": {
        "es": "❌ No conozco ese idioma. Opciones: {opciones}",
        "en": "❌ Unknown language. Options: {opciones}",
    },
    # El mismo comando en privado habla del idioma de la persona, no del
    # servidor. Son claves aparte y no un `{quien}` interpolado porque "tu
    # idioma" y "el idioma de este servidor" no se construyen igual en los dos
    # idiomas y una plantilla con hueco produce frases raras en cuanto se añada
    # un tercero.
    "lang.mio_actual": {
        "es": "Tu idioma es **{idioma}**.",
        "en": "Your language is **{idioma}**.",
    },
    "lang.mio_defecto": {
        "es": "Todavía no has elegido idioma; te estoy hablando en **{idioma}**.",
        "en": "You haven't picked a language yet; I'm talking to you in **{idioma}**.",
    },
    "lang.mio_cambiado": {
        "es": "✅ Tu idioma es ahora **{idioma}**. Te hablaré así en privado y en cualquier servidor.",
        "en": "✅ Your language is now **{idioma}**. I'll use it in DMs and in any server.",
    },

    # ---- Embed de partida en vivo ----
    # Es la superficie que más se ve: se publica sola en el canal cada vez que
    # un pro entra en partida. Si esto queda en español, el bot "no está en
    # inglés" por muy traducido que esté el resto.
    "partida.titulo_uno": {
        "es": "{jugadores} está jugando! :loudspeaker:",
        "en": "{jugadores} is in game! :loudspeaker:",
    },
    "partida.titulo_varios": {
        "es": "{jugadores} están jugando! :loudspeaker:",
        "en": "{jugadores} are in game! :loudspeaker:",
    },
    "partida.y": {"es": "y", "en": "and"},
    "partida.sin_seguidos": {
        "es": "No hay jugadores del bot en esta partida.",
        "en": "No tracked players in this game.",
    },
    "partida.equipo": {"es": "**Equipo:** {equipo}", "en": "**Team:** {equipo}"},
    "partida.cola": {"es": "**Cola:** {cola}", "en": "**Queue:** {cola}"},
    "partida.modo": {"es": "**Modo:** {modo}", "en": "**Mode:** {modo}"},
    "partida.transcurrido": {
        "es": "**Tiempo transcurrido:** {tiempo}",
        "en": "**Elapsed:** {tiempo}",
    },
    "partida.hora_inicio": {
        "es": "**Hora de inicio:** {hora}",
        "en": "**Started at:** {hora}",
    },
    "partida.en_carga": {"es": "En carga", "en": "Loading screen"},
    "partida.desconocida": {"es": "Desconocida", "en": "Unknown"},
    "partida.desconocida_id": {
        "es": "Desconocida ({id})",
        "en": "Unknown ({id})",
    },
    "partida.desconocido": {"es": "Desconocido", "en": "Unknown"},
    "partida.col_campeon": {"es": "Campeón", "en": "Champion"},
    "partida.col_cuenta": {"es": "Cuenta", "en": "Account"},
    "partida.col_rango": {"es": "Rango 🏆", "en": "Rank 🏆"},
    "partida.sin_rango": {"es": "Sin clasificar", "en": "Unranked"},
    "partida.jugadores_seguidos": {
        "es": "Jugadores en la partida",
        "en": "Tracked players in this game",
    },
    "partida.lado_azul": {"es": "🔵 Equipo azul", "en": "🔵 Blue Team"},
    "partida.lado_rojo": {"es": "🔴 Equipo rojo", "en": "🔴 Red Team"},
    "partida.jugadores_n": {
        "es": "👥 Jugadores ({n})",
        "en": "👥 Players ({n})",
    },
    "partida.sin_jugadores": {"es": "Sin jugadores", "en": "No players"},
    "partida.espectar": {
        "es": "🔗 Espectar en directo",
        "en": "🔗 Spectate live",
    },
    "partida.espectar_bat": {
        "es": "Descarga y ejecuta el archivo **spectate_lol.bat** adjunto arriba "
              "para espectar la partida desde tu cliente. (Debes tener el cliente "
              "de LoL cerrado)",
        "en": "Download and run the **spectate_lol.bat** file attached above to "
              "watch the game from your own client. (The LoL client must be "
              "closed first.)",
    },
    "partida.espectar_espera": {
        "es": "⏳ **Disponible en {falta}** ({reloj}). El .bat ya está adjunto: "
              "ejecútalo cuando acabe la cuenta atrás, antes el cliente se "
              "queda esperando sin imagen.",
        "en": "⏳ **Available in {falta}** ({reloj}). The .bat is already "
              "attached: run it once the countdown ends — any earlier and the "
              "client just sits there with no picture.",
    },
    "partida.espectar_no": {
        "es": "No disponible para esta partida.",
        "en": "Not available for this game.",
    },
    "partida.info_titulo": {
        "es": "/info <nombre jugador>",
        "en": "/info <player name>",
    },
    "partida.info_valor": {
        "es": "Con este comando puedes ver información adicional de cualquier "
              "jugador de la partida cuyo nick sea visible.",
        "en": "Use this command for extra information about any player in the "
              "game whose name is visible.",
    },

    # ---- Reloj de partida (utils/game_clock.py) ----
    "reloj.desconocido": {
        "es": "⏱ tiempo desconocido",
        "en": "⏱ unknown time",
    },
    "reloj.en_partida": {
        "es": "⏱ {tiempo} en partida",
        "en": "⏱ {tiempo} into the game",
    },
    "reloj.cuenta_atras": {
        "es": "⏳ {reloj} · se podrá ver en {falta}",
        "en": "⏳ {reloj} · watchable in {falta}",
    },
    "reloj.embed_desconocido": {"es": "Desconocido", "en": "Unknown"},
    "reloj.embed_espectable": {
        "es": "{base} · ⏳ espectable en {falta}",
        "en": "{base} · ⏳ watchable in {falta}",
    },
    "reloj.aviso": {
        "es": "⏳ **Comienza dentro de {falta}** — el espectador va {delay} por "
              "detrás de la partida, así que hasta entonces el cliente no "
              "mostrará imagen.",
        "en": "⏳ **Starts in {falta}** — the spectator feed runs {delay} behind "
              "the live game, so until then the client shows no picture.",
    },
    "reloj.minutos": {"es": "{n} min", "en": "{n} min"},
    "reloj.segundos": {"es": "{n} s", "en": "{n} s"},

    # ---- /match ----
    "match.falta_nombre": {
        "es": "❌ Indica un nombre de jugador. Ejemplo: `/match jugador:elk`",
        "en": "❌ Give me a player name. Example: `/match player:elk`",
    },
    "match.no_encontrado": {
        "es": "❌ No se encontró ningún jugador seguido con el nombre '{nombre}'.\n"
              "*Usa `/live` para ver quién está en partida ahora mismo.*",
        "en": "❌ No tracked player found with the name '{nombre}'.\n"
              "*Use `/live` to see who is in game right now.*",
    },
    "match.buscando": {
        "es": "⏳ Buscando la partida de {nombre}...",
        "en": "⏳ Looking for {nombre}'s game...",
    },
    "match.fallo_embed": {
        "es": "⚠️ Se encontró la partida pero falló al montar el embed.",
        "en": "⚠️ Found the game but failed to build the embed.",
    },
    "match.titulo": {
        "es": "Partida de {nombre} ({cuenta}) 🎮",
        "en": "{nombre}'s game ({cuenta}) 🎮",
    },
    "match.sin_partida": {
        "es": "❌ {nombre} no está en ninguna partida activa en ninguna de sus cuentas.",
        "en": "❌ {nombre} is not in an active game on any of their accounts.",
    },
    "match.sin_cache": {
        "es": "⚠️ Riot está limitando las peticiones y no hay datos en caché. "
              "Prueba de nuevo en unos segundos.",
        "en": "⚠️ Riot is rate limiting us and there's nothing cached. "
              "Try again in a few seconds.",
    },
    "match.cache_ilegible": {
        "es": "⚠️ Los datos en caché no se pudieron leer.",
        "en": "⚠️ The cached data could not be read.",
    },
    "match.titulo_cache": {
        "es": "Partida de {nombre} 🎮 (datos en caché)",
        "en": "{nombre}'s game 🎮 (cached data)",
    },
    "match.campo_cache": {
        "es": "⏳ Tiempo estimado desde la notificación",
        "en": "⏳ Estimated time since the notification",
    },
    "match.valor_cache": {
        "es": "{tiempo} (estimado, por rate limit)",
        "en": "{tiempo} (estimated — rate limited)",
    },

    # ---- /live ----
    "live.buscando": {
        "es": "⏳ Buscando jugadores en partida...",
        "en": "⏳ Looking for players in game...",
    },
    "live.nadie": {
        "es": "No hay jugadores en partida en este momento.\n"
              "*(Puede haber partidas no detectadas aún. Usa `/match <jugador>` "
              "si tienes dudas.)*",
        "en": "No tracked players are in game right now.\n"
              "*(Some games may not be detected yet. Use `/match <player>` if "
              "in doubt.)*",
    },
    "live.titulo": {
        "es": "**Jugadores en partida ahora mismo:**",
        "en": "**Players in game right now:**",
    },
    "live.pie": {
        "es": "*(Usa `/match <jugador>` para más información)*",
        "en": "*(Use `/match <player>` for more detail)*",
    },
    "live.esperando": {
        "es": "⏳ *{n} partida(s) todavía dentro del delay del espectador "
              "({minutos} min): se podrán ver en el cliente cuando acabe la "
              "cuenta atrás.*",
        "en": "⏳ *{n} game(s) still inside the spectator delay ({minutos} min): "
              "they become watchable in the client once the countdown ends.*",
    },
    "live.aviso_retraso": {
        "es": "⚠️ *El estado puede llevar hasta {segundos}s de retraso; alguna "
              "partida puede haber terminado ya.*",
        "en": "⚠️ *This can be up to {segundos}s behind; some games may have "
              "already finished.*",
    },

    # ---- /team ----
    "team.falta_equipo": {
        "es": "❌ Indica un equipo. Ejemplo: `/team equipo:G2`",
        "en": "❌ Give me a team. Example: `/team team:G2`",
    },
    "team.equipos_con_jugadores": {
        "es": "Equipos con jugadores: {equipos}",
        "en": "Teams with players: {equipos}",
    },
    "team.consultando": {
        "es": "⏳ Consultando {equipo}...",
        "en": "⏳ Checking {equipo}...",
    },
    "team.sin_jugadores": {
        "es": "❌ No hay jugadores registrados para '{equipo}'.",
        "en": "❌ No players registered for '{equipo}'.",
    },
    "team.equipos_disponibles": {
        "es": "Equipos disponibles: {equipos}",
        "en": "Available teams: {equipos}",
    },
    "team.error_rango": {
        "es": "**{jugador}** - error consultando el rango",
        "en": "**{jugador}** - error fetching the rank",
    },
    "team.sin_cuentas": {
        "es": "**{jugador}** - sin cuentas registradas",
        "en": "**{jugador}** - no registered accounts",
    },
    "team.sin_cuenta": {"es": "(sin cuenta)", "en": "(no account)"},
    # Lleva el espacio y el punto medio delante porque se pega al final de la
    # línea del jugador, igual que antes de traducirlo.
    "team.mejor_de": {"es": " · mejor de {total}", "en": " · best of {total}"},
    "team.titulo": {
        "es": "**Jugadores de {equipo} ({nombre}):**",
        "en": "**{equipo} players ({nombre}):**",
    },
    # "jugador(es)" en vez de dos claves: el aviso solo aparece con un número
    # que puede ser 1 o más y la forma con paréntesis vale para los dos idiomas.
    "team.aviso_sin_datos": {
        "es": "⚠️ {n} jugador(es) sin datos de rango. Intenta más tarde para "
              "información completa.",
        "en": "⚠️ {n} player(s) with no rank data. Try again later for the full "
              "picture.",
    },
    # Lo devuelve `utils.rank_utils.formatear_rank`, que solo se ve en `/team`.
    "team.sin_datos": {"es": "Sin datos", "en": "No data"},

    # ---- /info ----
    "info.falta_nombre": {
        "es": "❌ Indica un jugador o una cuenta.\n"
              "Ejemplos: `/info jugador:Elyoya` · `/info jugador:Caps#EUW`",
        "en": "❌ Give me a player or an account.\n"
              "Examples: `/info player:Elyoya` · `/info player:Caps#EUW`",
    },
    "info.buscando": {
        "es": "⏳ Buscando información de {nombre}...",
        "en": "⏳ Looking up {nombre}...",
    },
    "info.no_encontrado": {
        "es": "❌ No se encontró información para '{nombre}'.\n"
              "*Solo hay ficha de los pros seguidos; prueba con el nick del jugador.*",
        "en": "❌ No information found for '{nombre}'.\n"
              "*Only tracked pros have a profile; try the player's nickname.*",
    },
    "info.fallo_embed": {
        "es": "❌ Se encontró el jugador pero falló al montar la ficha. "
              "Está anotado en el log del bot.",
        "en": "❌ Found the player but failed to build the profile. "
              "It's recorded in the bot log.",
    },
    "info.sin_datos": {
        "es": "❌ No hay datos suficientes para mostrar a '{nombre}'.",
        "en": "❌ Not enough data to show '{nombre}'.",
    },

    # ---- Ficha de jugador (ui/player_info_embed.py) ----
    "info.embed_descripcion": {
        "es": "Equipo: **{equipo}** | País: {pais}",
        "en": "Team: **{equipo}** | Country: {pais}",
    },
    "info.desconocido": {"es": "Desconocido", "en": "Unknown"},
    "info.desconocida": {"es": "Desconocida", "en": "Unknown"},
    "info.sin_equipo": {"es": "Sin equipo", "en": "No team"},
    "info.sin_liga": {"es": "Sin liga", "en": "Unranked"},
    "info.campo_nacimiento": {"es": "🎂 Nacimiento", "en": "🎂 Born"},
    "info.campo_edad": {"es": "👶 Edad", "en": "👶 Age"},
    "info.campo_contrato": {"es": "📄 Contrato", "en": "📄 Contract"},
    "info.campo_redes": {"es": "Redes Sociales", "en": "Social media"},
    "info.sin_redes": {
        "es": "🙅 Sin redes públicas conocidas.",
        "en": "🙅 No known public accounts.",
    },
    "info.campo_cuentas": {"es": "🎮 Cuentas SoloQ", "en": "🎮 SoloQ accounts"},
    "info.sin_cuentas": {
        "es": "Sin cuentas registradas.",
        "en": "No registered accounts.",
    },
    "info.cuenta_cabecera": {
        "es": "**{cuenta}** ({region}) — {liga}",
        "en": "**{cuenta}** ({region}) — {liga}",
    },
    "info.cuenta_balance": {
        "es": "Victorias: {victorias}W - Derrotas: {derrotas}L ({winrate})",
        "en": "Wins: {victorias}W - Losses: {derrotas}L ({winrate})",
    },
    "info.cuenta_ultima": {
        "es": "Última partida: {tiempo}",
        "en": "Last game: {tiempo}",
    },
    "info.campo_champs": {
        "es": "🔥 Campeones recientes",
        "en": "🔥 Recent champions",
    },
    "info.champ_linea": {
        "es": "**{campeon}** — {victorias}W-{derrotas}L ({winrate}) | "
              "KDA Promedio: {kda}",
        "en": "**{campeon}** — {victorias}W-{derrotas}L ({winrate}) | "
              "Average KDA: {kda}",
    },
    "info.campo_stats": {
        "es": "📊 Estadísticas últimas 2 semanas",
        "en": "📊 Last 2 weeks",
    },
    "info.stats_valor": {
        "es": "{victorias}W - {derrotas}L ({winrate})\nTiempo jugado: {tiempo}",
        "en": "{victorias}W - {derrotas}L ({winrate})\nTime played: {tiempo}",
    },
    # El tiempo relativo de la ficha **ya salía en inglés en español**: el código
    # lo construía a mano con `f"{n} day{'s' if n > 1 else ''} ago"`. Se deja tal
    # cual en `es` porque este cambio es un refactor y la salida en español no
    # debe moverse; cambiarlo es una decisión del dueño, no de la traducción.
    # Singular y plural van en claves distintas: el condicional dentro de la
    # f-string no sobrevive a una plantilla única.
    "info.hace_anio": {"es": "{n} year ago", "en": "{n} year ago"},
    "info.hace_anios": {"es": "{n} years ago", "en": "{n} years ago"},
    "info.hace_mes": {"es": "{n} month ago", "en": "{n} month ago"},
    "info.hace_meses": {"es": "{n} months ago", "en": "{n} months ago"},
    "info.hace_dia": {"es": "{n} day ago", "en": "{n} day ago"},
    "info.hace_dias": {"es": "{n} days ago", "en": "{n} days ago"},
    "info.hace_hora": {"es": "{n} hour ago", "en": "{n} hour ago"},
    "info.hace_horas": {"es": "{n} hours ago", "en": "{n} hours ago"},
    "info.hace_min": {"es": "{n} min ago", "en": "{n} min ago"},
    "info.ahora_mismo": {"es": "just now", "en": "just now"},

    # ---- /historial ----
    "historial.consultando": {
        "es": "⏳ Consultando el historial...",
        "en": "⏳ Fetching the match history...",
    },
    "historial.sin_jugadores": {
        "es": "No hay jugadores registrados.",
        "en": "No players registered.",
    },
    "historial.sin_partidas": {
        "es": "No se encontraron partidas recientes.",
        "en": "No recent games found.",
    },
    # La cabecera global iba en una sola f-string de dos líneas; se parte en dos
    # claves porque la segunda es una instrucción de uso y la primera un recuento.
    "historial.cabecera_global": {
        "es": "**Últimas {n} partidas (máximo 1 por jugador):**",
        "en": "**Latest {n} games (max 1 per player):**",
    },
    "historial.como_usar": {
        "es": "Para ver las de un jugador: `/historial jugador:<nick>` "
              "o `/historial jugador:<gameName#tag>`",
        "en": "For a single player: `/historial player:<nick>` "
              "or `/historial player:<gameName#tag>`",
    },
    "historial.jugador_no_encontrado": {
        "es": "No se encontró el jugador o cuenta '{nombre}'.",
        "en": "No player or account found for '{nombre}'.",
    },
    "historial.cuenta_no_encontrada": {
        "es": "No se encontró la cuenta '{cuenta}' para {jugador}.",
        "en": "No account '{cuenta}' found for {jugador}.",
    },
    "historial.sin_historial": {
        "es": "No se encontró historial para {jugador}.",
        "en": "No match history found for {jugador}.",
    },
    # Dos claves en vez de un fragmento condicional pegado: el original
    # concatenaba `" (todas sus cuentas):**"` o `":**"` al final del título, lo
    # que dejaba los `**` abiertos en mitad de una cadena y no se puede traducir
    # así sin que el inglés quede torcido.
    "historial.cabecera_jugador": {
        "es": "**Últimas {n} partidas de {jugador}:**",
        "en": "**Latest {n} games from {jugador}:**",
    },
    "historial.cabecera_jugador_todas": {
        "es": "**Últimas {n} partidas de {jugador} (todas sus cuentas):**",
        "en": "**Latest {n} games from {jugador} (all their accounts):**",
    },
    # Lo pone `utils.match_format.formatear_partida` al final de cada línea.
    "historial.cuenta_sufijo": {
        "es": " _(Cuenta: {cuenta})_",
        "en": " _(Account: {cuenta})_",
    },

    # ---- /health ----
    "health.comprobando": {"es": "⏳ Comprobando...", "en": "⏳ Checking..."},
    "health.titulo": {"es": "🩺 Estado del bot", "en": "🩺 Bot status"},
    "health.encendido": {
        "es": "Encendido desde hace **{tiempo}**.",
        "en": "Up for **{tiempo}**.",
    },
    "health.campo_fuentes": {"es": "Fuentes de datos", "en": "Data sources"},
    "health.campo_tareas": {"es": "Tareas automáticas", "en": "Background tasks"},
    "health.campo_atencion": {"es": "⚠️ Atención", "en": "⚠️ Heads up"},
    "health.averias": {
        "es": "Hay fuentes con fallos repetidos: {fuentes}.\nLos comandos siguen "
              "respondiendo, pero con los últimos datos guardados, que pueden no "
              "estar al día.",
        "en": "Some sources are failing repeatedly: {fuentes}.\nCommands still "
              "answer, but with the last saved data, which may be out of date.",
    },
    "health.pie": {
        "es": "⚪ sin comprobar · 🟢 al día · 🟡 con fallos · 🔴 caído",
        "en": "⚪ not checked · 🟢 up to date · 🟡 failing · 🔴 down",
    },
    "health.respaldo_titulo": {
        "es": "**Estado del bot** — encendido hace {tiempo}",
        "en": "**Bot status** — up for {tiempo}",
    },
    # Tiempo encendido. Tres formas porque el original cambiaba de unidad según
    # la magnitud, no porque el idioma lo pida.
    "health.uptime_dias": {"es": "{dias} d {horas} h", "en": "{dias} d {horas} h"},
    "health.uptime_horas": {
        "es": "{horas} h {minutos} min",
        "en": "{horas} h {minutos} min",
    },
    "health.uptime_minutos": {"es": "{minutos} min", "en": "{minutos} min"},
    # Resumen de seguimiento.
    "health.cuentas_ilegibles": {
        "es": "❓ no se pudo leer el fichero de cuentas",
        "en": "❓ couldn't read the accounts file",
    },
    "health.cero_jugadores": {
        "es": "🔴 **0 jugadores**: el bot no está vigilando a nadie",
        "en": "🔴 **0 players**: the bot isn't watching anyone",
    },
    "health.cero_cuentas": {
        "es": "🔴 **{jugadores} jugadores pero 0 cuentas**: no hay nada que "
              "consultar en Riot",
        "en": "🔴 **{jugadores} players but 0 accounts**: there's nothing to ask "
              "Riot about",
    },
    "health.resumen": {
        "es": "🟢 **{jugadores} jugadores** · {cuentas} cuentas · {equipos} equipos",
        "en": "🟢 **{jugadores} players** · {cuentas} accounts · {equipos} teams",
    },
    "health.sin_puuid": {
        "es": "⚠️ {n} cuenta(s) sin PUUID",
        "en": "⚠️ {n} account(s) with no PUUID",
    },
    "health.jugadores_sin_cuenta": {
        "es": "⚠️ {n} jugador(es) sin ninguna cuenta",
        "en": "⚠️ {n} player(s) with no accounts at all",
    },
    # Tareas de fondo: nombre, estado y cadencia.
    "health.tarea_linea": {
        "es": "{marca} {nombre} — {estado} · {cadencia}",
        "en": "{marca} {nombre} — {estado} · {cadencia}",
    },
    "health.tarea_partidas": {"es": "Partidas en curso", "en": "Live games"},
    "health.tarea_puuids": {"es": "Reparación de PUUIDs", "en": "PUUID repair"},
    "health.tarea_plantillas": {
        "es": "Plantillas y cuentas",
        "en": "Rosters and accounts",
    },
    "health.tarea_pickrates": {"es": "Pickrates", "en": "Pickrates"},
    "health.tarea_infoplayers": {"es": "Infoplayers", "en": "Infoplayers"},
    "health.tarea_historial": {
        "es": "Historial (precalentado)",
        "en": "Match history (warm-up)",
    },
    "health.tarea_rangos": {
        "es": "Rangos (precalentado)",
        "en": "Ranks (warm-up)",
    },
    "health.estado_activa": {"es": "activa", "en": "running"},
    "health.estado_parada_error": {
        "es": "parada por error",
        "en": "stopped by an error",
    },
    "health.estado_desactivada": {"es": "desactivada", "en": "disabled"},
    "health.estado_detenida": {"es": "**detenida**", "en": "**stopped**"},
    "health.cadencia_segundos": {"es": "cada {n}s", "en": "every {n}s"},
    "health.cadencia_horas": {"es": "cada {n} h", "en": "every {n} h"},
    "health.cadencia_dias": {"es": "cada {n} d", "en": "every {n} d"},
    "health.cadencia_desactivado": {"es": "desactivado", "en": "disabled"},

    # ---- Fuentes de datos (core/health.py) ----
    "salud.fuente_riot": {
        "es": "Riot API (partidas y Elo)",
        "en": "Riot API (games and rank)",
    },
    # La pasada del tracker no es una fuente externa, pero se enseña con ellas
    # porque el síntoma que produce es idéntico —avisos que llegan tarde— y el
    # sitio donde alguien va a mirarlo es el mismo.
    "salud.fuente_pasada": {
        "es": "Pasada de partidas (cada cuánto llega el aviso)",
        "en": "Game sweep (how fast alerts arrive)",
    },
    "salud.fuente_cuentas": {
        "es": "Plantillas y cuentas (dpm.lol)",
        "en": "Rosters and accounts (dpm.lol)",
    },
    "salud.fuente_leaderboard": {
        "es": "Rankings de liga (dpm.lol)",
        "en": "League rankings (dpm.lol)",
    },
    "salud.fuente_historial": {
        "es": "Historial de partidas (dpm.lol)",
        "en": "Match history (dpm.lol)",
    },
    "salud.fuente_pickrates": {
        "es": "Pickrates por línea (dpm.lol)",
        "en": "Pickrates by lane (dpm.lol)",
    },
    "salud.fuente_esports": {
        "es": "Calendario profesional (lolesports)",
        "en": "Pro schedule (lolesports)",
    },
    "salud.sin_comprobar": {
        "es": "⚪ **{nombre}** — sin comprobar todavía",
        "en": "⚪ **{nombre}** — not checked yet",
    },
    "salud.al_dia": {
        "es": "🟢 **{nombre}** — al día ({cuando})",
        "en": "🟢 **{nombre}** — up to date ({cuando})",
    },
    "salud.con_fallos": {
        "es": "{icono} **{nombre}** — {fallos} fallo(s) seguidos{detalle}. "
              "Último dato bueno: {cuando}",
        "en": "{icono} **{nombre}** — {fallos} failure(s) in a row{detalle}. "
              "Last good data: {cuando}",
    },
    "salud.hace_segundos": {"es": "hace {n}s", "en": "{n}s ago"},
    "salud.hace_minutos": {"es": "hace {n} min", "en": "{n} min ago"},
    "salud.hace_horas": {"es": "hace {n} h", "en": "{n} h ago"},
    "salud.hace_dias": {"es": "hace {n} d", "en": "{n} d ago"},
    "salud.nunca": {"es": "nunca", "en": "never"},

    # ---- Help ----
    "help.titulo": {"es": "📖 Comandos del bot", "en": "📖 Bot commands"},
    "help.soloq": {"es": "🎮 SoloQ", "en": "🎮 SoloQ"},
    "help.config": {"es": "⚙️ Configuración", "en": "⚙️ Settings"},
    "help.esports": {"es": "🏆 Esports", "en": "🏆 Esports"},
    "help.pie": {
        "es": "Los comandos funcionan con `/` y con `!`.",
        "en": "Commands work with both `/` and `!`.",
    },
    "help.descripcion": {
        "es": "Muestra esta ayuda",
        "en": "Shows this help",
    },

    # ---- /premium ----
    # Lo que se cobra son cupos, nunca el aviso de partida: la política de Riot
    # exige un tier gratis y que el contenido de pago sea transformativo, así
    # que el texto tiene que dejar clarísimo que lo principal es gratis. Si
    # alguien lee esto y cree que hay que pagar para recibir avisos, el bot no
    # se instala y no hay negocio.
    "premium.titulo": {
        "es": "💎 Planes de {bot}",
        "en": "💎 {bot} plans",
    },
    "premium.intro": {
        "es": "**Todo lo importante es gratis y lo seguirá siendo**: los avisos "
              "cuando un pro entra en partida, `/live`, `/match`, `/info`, "
              "`/ranking`, `/historial` y los partidos de esports.\n"
              "Los planes solo suben los **cupos**.",
        "en": "**Everything that matters is free and always will be**: alerts "
              "when a pro starts a game, `/live`, `/match`, `/info`, "
              "`/ranking`, `/historial` and esports matches.\n"
              "Plans only raise the **limits**.",
    },
    "premium.tu_plan": {
        "es": "**Tu plan:** {plan}",
        "en": "**Your plan:** {plan}",
    },
    "premium.gratis_etiqueta": {"es": "gratis", "en": "free"},
    # El nombre del plan también se traduce: "Gratis" dentro de una frase
    # inglesa ("Your plan: Gratis") delata que la traducción está a medias, y es
    # justo el comando donde peor sienta. "Pro" y "Elite" se repiten porque son
    # iguales en los dos idiomas, no porque falte traducirlos.
    "premium.plan_gratis": {"es": "Gratis", "en": "Free"},
    "premium.plan_pro": {"es": "Pro", "en": "Pro"},
    "premium.plan_elite": {"es": "Elite", "en": "Elite"},
    "premium.precio_mes": {"es": "{precio} €/mes", "en": "€{precio}/month"},
    "premium.cupo_ligas": {
        "es": "{n} liga(s) a la vez",
        "en": "{n} league(s) at once",
    },
    "premium.cupo_canales": {
        "es": "{n} canal(es) de avisos",
        "en": "{n} alert channel(s)",
    },
    "premium.cupo_jugadores": {
        "es": "{n} jugador(es) propios",
        "en": "{n} custom player(s)",
    },
    "premium.cupo_historial": {
        "es": "{n} partidas de historial",
        "en": "{n} games of history",
    },
    "premium.uso": {
        "es": "**En uso ahora:** {ligas} de {tope} ligas",
        "en": "**Currently using:** {ligas} of {tope} leagues",
    },
    "premium.como": {
        "es": "🔓 **Cómo mejorar el plan**",
        "en": "🔓 **How to upgrade**",
    },
    "premium.sin_pasarela": {
        "es": "Todavía no hay pago automático. Si quieres apoyar el proyecto "
              "usa el enlace de donación y se te activa a mano.",
        "en": "Automatic payments aren't live yet. If you want to support the "
              "project use the donation link and it gets enabled manually.",
    },
    "premium.sin_enlaces": {
        "es": "Aún no hay enlaces configurados. Pregunta a quien administra el bot.",
        "en": "No links configured yet. Ask whoever runs the bot.",
    },
    "premium.legal": {
        "es": "Este bot no vende ventajas dentro del juego ni acepta apuestas.",
        "en": "This bot doesn't sell in-game advantages and doesn't take bets.",
    },

    # ---- Esports: /partida, /next, /setlivechannel, /removelivechannel ----
    "esports.buscando": {
        "es": "⏳ Buscando partidas en vivo...",
        "en": "⏳ Looking for live matches...",
    },
    "esports.sin_partidas": {
        "es": "❌ No hay partidas en vivo en este momento.",
        "en": "❌ There are no live matches right now.",
    },
    "esports.consultando_calendario": {
        "es": "⏳ Consultando el calendario...",
        "en": "⏳ Checking the schedule...",
    },
    "esports.api_caida": {
        "es": "❌ Error al conectarse a la API de LoL Esports.",
        "en": "❌ Couldn't reach the LoL Esports API.",
    },
    "esports.sin_hora": {
        "es": "❌ No se pudo obtener la hora de referencia. Inténtalo de nuevo.",
        "en": "❌ Couldn't get the reference time. Try again.",
    },
    # La ventana sale como parámetro porque está en `VENTANA_HORAS`: si algún día
    # se amplía a 24 h, el texto no puede seguir diciendo 12.
    "esports.sin_proximos": {
        "es": "🎮 No hay partidos próximos en las próximas {horas} horas.",
        "en": "🎮 No matches coming up in the next {horas} hours.",
    },
    "esports.fallo_proximos": {
        "es": "❌ No se pudo preparar la información de los próximos partidos.",
        "en": "❌ Couldn't put together the info for the upcoming matches.",
    },
    "esports.canal_ok": {
        "es": "✅ Notificaciones de esports configuradas en {canal}{aviso}",
        "en": "✅ Esports notifications set up in {canal}{aviso}",
    },
    "esports.canal_solo_admin": {
        "es": "❌ Necesitas el permiso **Gestionar servidor** para cambiar el canal "
              "de notificaciones de esports.",
        "en": "❌ You need the **Manage Server** permission to change the esports "
              "notification channel.",
    },
    "esports.canal_fallo_guardar": {
        "es": "❌ Ocurrió un error al guardar el canal.",
        "en": "❌ Something went wrong saving the channel.",
    },
    "esports.canal_fallo_borrar": {
        "es": "❌ Ocurrió un error al desactivar las notificaciones.",
        "en": "❌ Something went wrong disabling the notifications.",
    },
    "esports.canal_desactivado": {
        "es": "✅ Notificaciones de esports desactivadas para este servidor.",
        "en": "✅ Esports notifications disabled for this server.",
    },

    # ---- Bienvenida al entrar en un servidor ----
    # Este es literalmente el primer mensaje que un servidor nuevo ve del bot, y
    # se manda **antes** de que nadie haya podido tocar `/lang`, así que el
    # idioma sale de `preferred_locale` del servidor, no de la configuración.
    "bienvenida.saludo": {
        "es": "¡Hola! Usa `/help` para ver todo lo que puedo hacer.\n"
              "Para recibir avisos cuando un pro entre en partida: "
              "`/setchannel` en el canal que quieras.\n"
              "Idioma: `/lang en` · Ligas: `/ligas`",
        "en": "Hi! Use `/help` to see everything I can do.\n"
              "To get alerts when a pro starts a game: `/setchannel` in "
              "whichever channel you want.\n"
              "Language: `/lang es` · Leagues: `/ligas`",
    },

    # ---- Aviso de partida (adjunto .bat) ----
    "aviso.fichero_espectar": {
        "es": "⬇️ **Archivo para espectar la partida:**",
        "en": "⬇️ **File to spectate the game:**",
    },

    # ---- Avisos personales por DM (/seguir, /dejarseguir, /misavisos) ----
    #
    # La mitad de estas cadenas existen por una limitación de Discord, no por
    # estética: un bot **no puede** escribir a alguien con quien no comparte
    # ningún servidor (error 50278), y quien solo se ha instalado la app en su
    # cuenta está exactamente en ese caso. Si el bot se limitara a decir
    # "suscrito ✅", esa persona esperaría para siempre un aviso que Discord no
    # nos deja entregar. Así que cada estado de entrega tiene su mensaje y su
    # salida concreta.
    "avisos.sin_usuario": {
        "es": "❌ No he podido identificar tu cuenta. Vuelve a intentarlo.",
        "en": "❌ I couldn't identify your account. Please try again.",
    },
    "avisos.idioma_fijado": {
        "es": "🌐 Te hablaré en **{idioma}**. Cámbialo cuando quieras con `/lang`.",
        "en": "🌐 I'll talk to you in **{idioma}**. Change it anytime with `/lang`.",
    },
    "avisos.dm_sin_probar": {
        "es": "📬 Aún no te he escrito nunca por privado. Comprueba con `/misavisos` "
              "que puedo hacerlo antes de que empiece una partida.",
        "en": "📬 I've never sent you a DM yet. Check with `/misavisos` that I can "
              "before a game starts.",
    },
    # 50007: los DM cerrados los abre el propio usuario, y el ajuste está por
    # servidor, así que hay que decirle dónde.
    "avisos.dm_cerrado": {
        "es": "⚠️ Tienes los mensajes privados cerrados, así que no puedo avisarte. "
              "Ábrelos en *Ajustes del servidor → Privacidad → Mensajes directos* "
              "y prueba otra vez con `/misavisos`.",
        "en": "⚠️ Your direct messages are closed, so I can't alert you. Enable them "
              "in *Server Settings → Privacy → Direct Messages* and try "
              "`/misavisos` again.",
    },
    # 50278: esto no lo arregla ningún ajuste. Hace falta un servidor en común.
    "avisos.dm_sin_guild": {
        "es": "⚠️ No compartimos ningún servidor, y Discord no me deja escribir a "
              "alguien en esa situación. Entra en un servidor donde esté el bot "
              "(o invítalo al tuyo) y vuelve a probar con `/misavisos`.",
        "en": "⚠️ We don't share any server, and Discord won't let me message "
              "someone in that situation. Join a server where the bot is (or "
              "invite it to yours) and try `/misavisos` again.",
    },
    "avisos.dm_sin_guild_enlace": {
        "es": "⚠️ No compartimos ningún servidor, y Discord no me deja escribir a "
              "alguien en esa situación. Entra aquí y ya podré avisarte: {url}",
        "en": "⚠️ We don't share any server, and Discord won't let me message "
              "someone in that situation. Join here and I'll be able to alert "
              "you: {url}",
    },

    # ---- /seguir ----
    "seguir.como_usar": {
        "es": "Usa `/seguir Elyoya` para un jugador, `/seguir lec` para una liga "
              "entera, y `/dejarseguir` para quitarlo. `/misavisos` te dice cómo "
              "lo tienes todo.",
        "en": "Use `/seguir Elyoya` for one player, `/seguir lec` for a whole "
              "league, and `/dejarseguir` to remove it. `/misavisos` shows how "
              "everything stands.",
    },
    "seguir.repetido": {
        "es": "ℹ️ Ya seguías a **{valor}**.",
        "en": "ℹ️ You were already following **{valor}**.",
    },
    "seguir.ok_jugador": {
        "es": "✅ Te avisaré por privado cuando **{jugador}** ({equipo} · {liga}) "
              "entre en partida de SoloQ.",
        "en": "✅ I'll DM you when **{jugador}** ({equipo} · {liga}) starts a "
              "SoloQ game.",
    },
    # Se guarda igual, pero prometer el aviso sería falso: si nadie rastrea a ese
    # jugador, no hay partida que detectar.
    "seguir.ok_jugador_sin_datos": {
        "es": "✅ Guardado: **{jugador}**.\n"
              "⚠️ Pero ahora mismo no estoy rastreando a nadie con ese nombre, así "
              "que todavía no te va a llegar ningún aviso.",
        "en": "✅ Saved: **{jugador}**.\n"
              "⚠️ But I'm not currently tracking anyone by that name, so no alerts "
              "will reach you yet.",
    },
    "seguir.sin_datos_salida": {
        "es": "Comprueba el nick con `/info {jugador}`, o sigue su liga con "
              "`/track <liga>` (por ejemplo `/track lck`) para que se descarguen "
              "sus cuentas y empiecen a llegar los avisos.",
        "en": "Check the nickname with `/info {jugador}`, or follow their league "
              "with `/track <league>` (for example `/track lck`) so their accounts "
              "get downloaded and the alerts start.",
    },
    "seguir.ok_liga": {
        "es": "✅ Te avisaré por privado de **todas** las partidas de SoloQ de "
              "**{liga}** (`{codigo}`).",
        "en": "✅ I'll DM you about **every** SoloQ game from **{liga}** "
              "(`{codigo}`).",
    },
    # Se dice solo cuando la liga no se estaba rastreando y se acaba de lanzar su
    # descarga. Sin este aviso, los primeros minutos de silencio parecen un
    # comando roto.
    "seguir.liga_descargando": {
        "es": "⏳ No tenía sus cuentas descargadas: las estoy trayendo ahora. "
              "Los primeros avisos pueden tardar unos minutos.",
        "en": "⏳ I didn't have its accounts downloaded — fetching them now. "
              "The first alerts may take a few minutes.",
    },
    # La liga existe y se puede elegir, pero la API de Riot no cubre sus
    # servidores: no habrá detección de partidas nunca.
    "seguir.liga_no_rastreable": {
        "es": "⚠️ De **{liga}** puedo darte rangos, pero no detectar partidas en "
              "vivo: la API de Riot no cubre sus servidores.",
        "en": "⚠️ For **{liga}** I can show ranks but not detect live games: "
              "Riot's API doesn't cover its servers.",
    },
    # Los rosters se refrescan una vez al día, así que una liga nueva no está
    # rastreada al instante. Decirlo evita que parezca que el comando no funcionó.
    "seguir.liga_pendiente": {
        "es": "ℹ️ Todavía no tengo las cuentas de **{liga}** descargadas. Se "
              "recogen en el refresco diario de plantillas; hasta entonces no "
              "saldrán avisos de esa liga.",
        "en": "ℹ️ I don't have **{liga}**'s accounts downloaded yet. They're "
              "collected in the daily roster refresh; until then no alerts will "
              "come from that league.",
    },
    "seguir.liga_mixta": {
        "es": "ℹ️ Los jugadores de **{liga}** juegan en varios servidores, así que "
              "la cobertura depende de cada cuenta.",
        "en": "ℹ️ **{liga}** players are spread across several servers, so "
              "coverage depends on each account.",
    },
    "seguir.cupo_jugadores": {
        "es": "❌ Tu plan permite seguir a {n} jugador(es) y ya los tienes.",
        "en": "❌ Your plan allows {n} player(s) and you're already using them all.",
    },
    "seguir.cupo_ligas": {
        "es": "❌ Tu plan permite seguir {n} liga(s) y ya las tienes.",
        "en": "❌ Your plan allows {n} league(s) and you're already using them all.",
    },
    "seguir.cupo_salida": {
        "es": "Estás en el plan **{plan}**. Quita algo con `/dejarseguir` o mira "
              "`/premium`.",
        "en": "You're on the **{plan}** plan. Remove something with `/dejarseguir` "
              "or check `/premium`.",
    },

    # ---- /dejarseguir ----
    "dejarseguir.falta_valor": {
        "es": "Dime qué quieres dejar de seguir: `/dejarseguir Elyoya`, "
              "`/dejarseguir lec`, o `/dejarseguir todo` para borrarlo todo.",
        "en": "Tell me what to stop following: `/dejarseguir Elyoya`, "
              "`/dejarseguir lec`, or `/dejarseguir all` to remove everything.",
    },
    "dejarseguir.ok": {
        "es": "✅ Ya no te avisaré de {valor}.",
        "en": "✅ I'll stop alerting you about {valor}.",
    },
    "dejarseguir.no_estaba": {
        "es": "ℹ️ No seguías **{valor}**. Mira `/misavisos` para ver qué tienes.",
        "en": "ℹ️ You weren't following **{valor}**. Check `/misavisos` to see "
              "what you have.",
    },
    "dejarseguir.todo": {
        "es": "✅ Borradas tus {n} suscripciones. No te llegará ningún aviso "
              "privado más.",
        "en": "✅ Removed your {n} subscriptions. No more DM alerts will reach you.",
    },
    "dejarseguir.nada_que_borrar": {
        "es": "ℹ️ No tenías ninguna suscripción personal.",
        "en": "ℹ️ You had no personal subscriptions.",
    },

    # ---- /misavisos ----
    "misavisos.titulo": {
        "es": "🔔 Tus avisos privados",
        "en": "🔔 Your DM alerts",
    },
    "misavisos.vacio": {
        "es": "No sigues a nadie todavía.",
        "en": "You're not following anyone yet.",
    },
    "misavisos.eje_jugadores": {
        "es": "👤 Jugadores (SoloQ)",
        "en": "👤 Players (SoloQ)",
    },
    "misavisos.eje_ligas": {
        "es": "🏆 Ligas enteras (SoloQ)",
        "en": "🏆 Whole leagues (SoloQ)",
    },
    "misavisos.eje_partidos_ligas": {
        "es": "📅 Partidos oficiales por liga",
        "en": "📅 Official matches by league",
    },
    "misavisos.eje_partidos_equipos": {
        "es": "📅 Partidos oficiales por equipo",
        "en": "📅 Official matches by team",
    },
    # Lo guardado que el plan no usa no se borra: si no se dijera, parecería que
    # ha desaparecido y el usuario lo volvería a añadir para nada.
    "misavisos.fuera_de_cupo": {
        "es": "   _guardado pero fuera de cupo: {valores}_",
        "en": "   _saved but over the limit: {valores}_",
    },
    "misavisos.plan": {"es": "💠 Plan: **{plan}**", "en": "💠 Plan: **{plan}**"},
    "misavisos.idioma": {"es": "🌐 Idioma: {idioma}", "en": "🌐 Language: {idioma}"},
    "misavisos.idioma_sin_elegir": {
        "es": "sin elegir (`/lang`)",
        "en": "not set (`/lang`)",
    },
    "misavisos.dm_ok": {
        "es": "📬 Entrega: **funciona**, puedo escribirte por privado.",
        "en": "📬 Delivery: **working**, I can DM you.",
    },
    "misavisos.dm_sin_probar": {
        "es": "📬 Entrega: **sin comprobar todavía**.",
        "en": "📬 Delivery: **not verified yet**.",
    },
    "misavisos.dm_cerrado": {
        "es": "📬 Entrega: **bloqueada** (tienes los privados cerrados).",
        "en": "📬 Delivery: **blocked** (your DMs are closed).",
    },
    "misavisos.dm_sin_guild": {
        "es": "📬 Entrega: **imposible** (no compartimos ningún servidor).",
        "en": "📬 Delivery: **impossible** (we don't share any server).",
    },
    # El DM de prueba de `/misavisos`. Tiene que explicarse solo: llega al chat
    # privado, fuera de contexto, y puede ser el primer mensaje que esa persona
    # recibe del bot.
    "misavisos.dm_prueba": {
        "es": "✅ Prueba de `/misavisos`: puedo escribirte por aquí, así que tus "
              "avisos de partida te llegarán a este chat.",
        "en": "✅ `/misavisos` test: I can message you here, so your game alerts "
              "will arrive in this chat.",
    },
    "misavisos.como_usar": {
        "es": "Añade con `/seguir <jugador o liga>` y quita con `/dejarseguir`.",
        "en": "Add with `/seguir <player or league>` and remove with "
              "`/dejarseguir`.",
    },

    # ---- Interfaz de Discord: descripciones de los comandos ----
    #
    # Estas cadenas no las escribe el bot en ningún mensaje: se le mandan a
    # Discord al registrar los comandos, y es Discord quien elige cuál mostrar
    # según el idioma del **cliente de cada usuario** (no según `/lang`).
    #
    # Dos reglas duras:
    # 1. Máximo 100 caracteres. Si una se pasa, Discord rechaza el registro
    #    entero con un 400 y el bot se queda **sin ningún** slash command.
    # 2. Los nombres de opción tienen que ir en minúsculas y sin espacios.
    # Las dos las comprueba `scripts/test_slash_locale.py`.
    "cmd.live.desc": {
        "es": "Jugadores profesionales que están en partida ahora mismo",
        "en": "Pro players who are in a game right now",
    },
    "cmd.match.desc": {
        "es": "Partida activa de un jugador profesional, con todos los participantes",
        "en": "A pro player's live game, with every participant",
    },
    "cmd.match.arg": {"es": "jugador", "en": "player"},
    "cmd.match.arg_desc": {
        "es": "Nick del pro (elk, Caps, Elyoya...)",
        "en": "Pro's nickname (elk, Caps, Elyoya...)",
    },
    "cmd.team.desc": {
        "es": "Jugadores de un equipo profesional con su mejor cuenta de SoloQ",
        "en": "A pro team's players with their best SoloQ account",
    },
    "cmd.team.arg": {"es": "equipo", "en": "team"},
    "cmd.team.arg_desc": {
        "es": "Tricode del equipo (G2, FNC, MKOI...)",
        "en": "Team tricode (G2, FNC, MKOI...)",
    },
    "cmd.info.desc": {
        "es": "Ficha de un jugador profesional o de una de sus cuentas",
        "en": "Profile of a pro player or one of their accounts",
    },
    "cmd.info.arg": {"es": "jugador", "en": "player"},
    "cmd.info.arg_desc": {
        "es": "Nick del pro (Elyoya) o cuenta (Caps#EUW)",
        "en": "Pro's nickname (Elyoya) or account (Caps#EUW)",
    },
    "cmd.historial.desc": {
        "es": "Últimas partidas de SoloQ de los pros seguidos",
        "en": "Latest SoloQ games of the pros being tracked",
    },
    "cmd.historial.arg": {"es": "jugador", "en": "player"},
    "cmd.historial.arg_desc": {
        "es": "Nick del pro o cuenta (vacío = historial global)",
        "en": "Pro's nickname or account (empty = global history)",
    },
    "cmd.ranking.desc": {
        "es": "Ranking de SoloQ de una liga profesional",
        "en": "SoloQ ranking of a pro league",
    },
    "cmd.ranking.arg": {"es": "liga", "en": "league"},
    "cmd.ranking.arg_desc": {
        "es": "Liga a consultar (por defecto LEC)",
        "en": "League to look up (LEC by default)",
    },
    "cmd.ligas.desc": {
        "es": "Ver o elegir qué ligas sigue este servidor (admin para cambiar)",
        "en": "View or pick which leagues this server tracks (admin to change)",
    },
    "cmd.ligas.arg": {"es": "ligas", "en": "leagues"},
    "cmd.ligas.arg_desc": {
        "es": "Códigos separados por espacios, p. ej. lec lck lcs",
        "en": "Space-separated codes, e.g. lec lck lcs",
    },
    "cmd.lang.desc": {
        "es": "Ver o cambiar el idioma del bot en este servidor (admin para cambiar)",
        "en": "View or change the bot's language on this server (admin to change)",
    },
    "cmd.lang.arg": {"es": "idioma", "en": "language"},
    "cmd.lang.arg_desc": {"es": "es o en", "en": "es or en"},
    "cmd.help.desc": {
        "es": "Lista de comandos del bot",
        "en": "Bot command list",
    },
    "cmd.health.desc": {
        "es": "Estado del bot y de sus fuentes de datos",
        "en": "Bot status and health of its data sources",
    },
    "cmd.premium.desc": {
        "es": "Planes, cupos y cómo apoyar el bot",
        "en": "Plans, limits and how to support the bot",
    },
    "cmd.setchannel.desc": {
        "es": "Añadir este canal a las notificaciones de SoloQ (admin)",
        "en": "Add this channel to the SoloQ alerts (admin)",
    },
    "cmd.quitarcanal.desc": {
        "es": "Quitar este canal de las notificaciones de SoloQ (admin)",
        "en": "Remove this channel from the SoloQ alerts (admin)",
    },
    "cmd.canales.desc": {
        "es": "Ver los canales de notificación de SoloQ de este servidor",
        "en": "See this server's SoloQ alert channels",
    },
    "cmd.unsubscribe.desc": {
        "es": "Dejar de recibir notificaciones de SoloQ en todo el servidor (admin)",
        "en": "Stop all SoloQ alerts on this server (admin)",
    },
    "cmd.partida.desc": {
        "es": "Partidos profesionales en vivo ahora mismo",
        "en": "Pro matches live right now",
    },
    "cmd.next.desc": {
        "es": "Horario de los próximos partidos profesionales",
        "en": "Schedule of the next pro matches",
    },
    "cmd.setlivechannel.desc": {
        "es": "Usar este canal para las notificaciones de esports (admin)",
        "en": "Use this channel for esports alerts (admin)",
    },
    "cmd.removelivechannel.desc": {
        "es": "Dejar de recibir notificaciones de esports (admin)",
        "en": "Stop receiving esports alerts (admin)",
    },
    # Los tres personales. Se pueden usar desde el chat privado con el bot, así
    # que la descripción tiene que decir que el aviso llega **a ti**: es lo único
    # que los distingue de `/setchannel`, que hace lo mismo para un canal.
    "cmd.seguir.desc": {
        "es": "Que te avise por privado cuando un pro o toda una liga juegue SoloQ",
        "en": "Get a DM when a pro or a whole league plays SoloQ",
    },
    "cmd.seguir.arg": {"es": "jugador_o_liga", "en": "player_or_league"},
    "cmd.seguir.arg_desc": {
        "es": "Nick del pro (Elyoya) o código de liga (lec, lck...)",
        "en": "Pro's nickname (Elyoya) or league code (lec, lck...)",
    },
    "cmd.dejarseguir.desc": {
        "es": "Dejar de recibir avisos privados de un jugador, de una liga o de todo",
        "en": "Stop DM alerts for a player, a league, or everything",
    },
    "cmd.dejarseguir.arg": {"es": "jugador_o_liga", "en": "player_or_league"},
    "cmd.dejarseguir.arg_desc": {
        "es": "Nick, código de liga, o `todo` para borrarlo todo",
        "en": "Nickname, league code, or `all` to remove everything",
    },
    "cmd.misavisos.desc": {
        "es": "Tus avisos privados: a quién sigues y si puedo escribirte",
        "en": "Your DM alerts: who you follow and whether I can message you",
    },
    # `/track` y `/untrack` son los **mismos** comandos que `/seguir` y
    # `/dejarseguir`, con el nombre que usa la gente que viene de otros bots (y
    # el que se busca en inglés). Apuntan a los mismos cuerpos, así que lo que se
    # guarda y de dónde se lee es exactamente lo mismo: dos puertas, un almacén.
    "cmd.track.desc": {
        "es": "Trackear a un pro o a una liga y que te avise por privado",
        "en": "Track a pro or a league and get a DM when they play",
    },
    "cmd.track.arg": {"es": "jugador_o_liga", "en": "player_or_league"},
    "cmd.track.arg_desc": {
        "es": "Nick del pro (Faker) o código de liga (lec, lck...)",
        "en": "Pro's nickname (Faker) or league code (lec, lck...)",
    },
    "cmd.untrack.desc": {
        "es": "Dejar de trackear a un jugador, a una liga o todo",
        "en": "Stop tracking a player, a league, or everything",
    },
    "cmd.untrack.arg": {"es": "jugador_o_liga", "en": "player_or_league"},
    "cmd.untrack.arg_desc": {
        "es": "Nick, código de liga, o `todo` para borrarlo todo",
        "en": "Nickname, league code, or `all` to remove everything",
    },
}


# ---------------------------------------------------------------------- #
# Traducción
# ---------------------------------------------------------------------- #

def t(clave: str, idioma: str | None = None, /, **kwargs: Any) -> str:
    """Traduce una clave. Nunca lanza: cae a español y luego a la clave.

    Los dos primeros parámetros son **posicionales obligatorios** (la `/`), y eso
    no es cosmético: `**kwargs` son los `{huecos}` de la plantilla, y sin la `/`
    un hueco que se llame igual que un parámetro choca con él. Pasaba de verdad:
    las cinco cadenas de `/lang` llevan `{idioma}`, así que
    `t("lang.actual", "es", idioma="Español")` levantaba
    `TypeError: t() got multiple values for argument 'idioma'` y el comando entero
    se caía en sus cuatro caminos. Con la `/`, `idioma=` solo puede ser un hueco.
    """
    entradas = _CATALOGO.get(clave)
    if not entradas:
        log.debug("Clave de traducción inexistente: %s", clave)
        return clave

    texto = entradas.get(idioma or "") or entradas.get(IDIOMA_POR_DEFECTO) or ""
    if not texto:
        return clave

    if kwargs:
        # Un `KeyError` por una plantilla mal escrita tampoco debe tumbar un
        # comando: si falta un dato se devuelve la plantilla sin rellenar.
        try:
            return texto.format(**kwargs)
        except (KeyError, IndexError, ValueError) as exc:
            log.warning("Plantilla %s mal formada (%s): %s", clave, exc, texto)
            return texto
    return texto


def tr(guild_id: int | str | None):
    """Devuelve `t` ya atada al idioma de un servidor.

    Se resuelve el idioma **al crearla**, no en cada llamada: un comando hace
    unas pocas llamadas y el idioma no va a cambiar a mitad de respuesta.
    """
    idioma = idioma_de(guild_id)

    def _t(clave: str, **kwargs: Any) -> str:
        return t(clave, idioma, **kwargs)

    return _t


# ---------------------------------------------------------------------- #
# Persistencia del idioma por servidor
# ---------------------------------------------------------------------- #

def _cargar() -> dict[str, Any]:
    if not os.path.exists(_IDIOMAS_PATH):
        return {}
    try:
        with open(_IDIOMAS_PATH, encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("idiomas_config.json ilegible (%s): se empieza vacío", exc)
        return {}


def _guardar(datos: dict[str, Any]) -> None:
    tmp = _IDIOMAS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _IDIOMAS_PATH)


def normalizar_idioma(texto: str) -> str | None:
    """`"  EN "` -> `"en"`. Acepta el nombre del idioma también."""
    limpio = (texto or "").strip().lower()
    if not limpio:
        return None
    if limpio in IDIOMAS:
        return limpio
    for codigo, nombre in IDIOMAS.items():
        if nombre.lower() == limpio:
            return codigo
    # "english", "ingles", "español", "spanish"
    return _ALIAS_IDIOMA.get(limpio)


_ALIAS_IDIOMA: dict[str, str] = {
    "english": "en", "ingles": "en", "inglés": "en", "eng": "en",
    "spanish": "es", "español": "es", "espanol": "es", "castellano": "es", "spa": "es",
}


def idioma_de(guild_id: int | str | None) -> str:
    """Idioma de un servidor. Si no eligió nunca, español."""
    if guild_id is None:
        return IDIOMA_POR_DEFECTO
    datos = _cargar()
    guardado = datos.get(str(guild_id), {}).get("idioma")
    return guardado if guardado in IDIOMAS else IDIOMA_POR_DEFECTO


def idioma_de_servidor(guild) -> str:
    """Idioma para un servidor que **todavía no ha elegido** ninguno.

    Existe por el mensaje de bienvenida: se manda al entrar, antes de que nadie
    haya podido ejecutar `/lang`, así que `idioma_de()` devolvería siempre
    español y un servidor inglés recibiría su primer mensaje del bot en un
    idioma que no habla. Ese primer mensaje es justo el que decide si el bot se
    queda o se echa.

    El orden es: lo que el servidor haya guardado con `/lang` (si ya lo hizo)
    > `preferred_locale` de Discord > español.

    `preferred_locale` es un `Locale` (`es-ES`, `en-US`, `de`...); solo interesa
    el prefijo, y si es un idioma que el bot no habla se cae al español, que es
    el comportamiento de antes.
    """
    guild_id = getattr(guild, "id", None)
    if guild_id is not None:
        datos = _cargar()
        guardado = datos.get(str(guild_id), {}).get("idioma")
        if guardado in IDIOMAS:
            return guardado

    locale = getattr(guild, "preferred_locale", None)
    codigo = str(getattr(locale, "value", locale) or "").lower()
    prefijo = codigo.split("-")[0]
    if prefijo in IDIOMAS:
        return prefijo
    return IDIOMA_POR_DEFECTO


def establecer_idioma(guild_id: int | str | None, idioma: str) -> str:
    """Guarda el idioma de un servidor. Devuelve el código que queda guardado."""
    codigo = normalizar_idioma(idioma) or IDIOMA_POR_DEFECTO
    datos = _cargar()
    datos.setdefault(str(guild_id), {})["idioma"] = codigo
    _guardar(datos)
    log.info("Idioma de %s -> %s", guild_id, codigo)
    return codigo


# ---------------------------------------------------------------------- #
# Idioma por persona
# ---------------------------------------------------------------------- #
#
# Por qué hace falta otro eje
# ---------------------------
# El idioma era del servidor porque el aviso de partida sale en un canal y lo
# leen todos. Eso sigue siendo verdad y no cambia. Pero un aviso que llega al
# chat privado de una persona lo lee **una** persona, y ahí el idioma del
# servidor no significa nada: en DM no hay servidor.
#
# El orden de resolución es este, y cada escalón está por un motivo:
#
#   1. lo que la persona eligió        — lo pidió explícitamente, manda siempre
#   2. lo que el servidor eligió       — respuesta pública en un canal ajeno
#   3. el locale del cliente de Discord — mejor conjetura antes de preguntar
#   4. español                          — lo que el bot hacía siempre
#
# El escalón 3 es el que hace que la primera respuesta que alguien ve del bot
# esté en su idioma sin haber configurado nada, que es el mismo motivo por el que
# ya existe `idioma_de_servidor` para el mensaje de bienvenida. Sin él, un
# usuario inglés recibiría en español justo el mensaje que le pregunta en qué
# idioma quiere las cosas.

def idioma_de_usuario(user_id: int | str | None) -> str | None:
    """Idioma que una persona eligió, o `None` si nunca eligió.

    Devuelve `None` en vez del idioma por defecto porque quien decide es
    `idioma_efectivo`: "no ha elegido" y "eligió español" llevan a resultados
    distintos, y colapsarlos aquí dejaría a un usuario inglés en español para
    siempre sin haber tocado nada.
    """
    if user_id is None:
        return None
    from tracking.soloq.user_config import idioma_guardado

    guardado = idioma_guardado(user_id)
    return guardado if guardado in IDIOMAS else None


def establecer_idioma_usuario(user_id: int | str, idioma: str) -> str:
    """Guarda el idioma de una persona. Devuelve el código que queda guardado."""
    from tracking.soloq.user_config import establecer_idioma as guardar

    codigo = normalizar_idioma(idioma) or IDIOMA_POR_DEFECTO
    guardar(user_id, codigo)
    return codigo


def idioma_de_locale(locale: Any) -> str | None:
    """Prefijo de idioma de un `Locale` de Discord, si lo hablamos.

    Llega como `Locale.es_ES`, `"en-US"`, `"de"`... y solo interesa el prefijo.
    Un idioma que el bot no habla devuelve `None` para que el llamante siga
    bajando escalones en vez de plantarse en inglés.
    """
    codigo = str(getattr(locale, "value", locale) or "").lower()
    prefijo = codigo.split("-")[0]
    return prefijo if prefijo in IDIOMAS else None


def idioma_efectivo(
    user_id: int | str | None = None,
    guild_id: int | str | None = None,
    locale: Any = None,
) -> str:
    """El idioma en el que hay que contestar. Ver el bloque de arriba.

    Nunca levanta y nunca devuelve vacío: se llama desde el camino de respuesta
    de cada comando y desde el reparto de avisos.
    """
    propio = idioma_de_usuario(user_id)
    if propio:
        return propio

    if guild_id is not None:
        guardado = _cargar().get(str(guild_id), {}).get("idioma")
        if guardado in IDIOMAS:
            return guardado

    return idioma_de_locale(locale) or IDIOMA_POR_DEFECTO


def tr_usuario(
    user_id: int | str | None,
    guild_id: int | str | None = None,
    locale: Any = None,
):
    """Como `tr`, pero resolviendo también el idioma de la persona.

    Es la que deben usar los comandos nuevos. `tr(guild_id)` se queda porque la
    usan los avisos de canal, donde no hay una persona a la que preguntar.
    """
    idioma = idioma_efectivo(user_id, guild_id, locale)

    def _t(clave: str, **kwargs: Any) -> str:
        return t(clave, idioma, **kwargs)

    return _t

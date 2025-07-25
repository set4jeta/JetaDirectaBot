# core/help_commands.py
import nextcord
from nextcord.ext import commands

def register_help_command(bot: commands.Bot):
    @bot.command(name="help")
    async def help_command(ctx: commands.Context):
        help_text = (
            "**📘 Comandos disponibles:**\n"
            "`!help` - Muestra este mensaje de ayuda\n"
            "`!setchannel` - Configura este canal para notificaciones automáticas partidas jugadores LEC+ (solo admin)\n"
            "`!unsubscribe` - Elimina el canal de notificaciones del servidor (solo admin)\n"
            "`!team <equipo>` - Muestra los nombres de jugadores en un equipo LEC (+KOI SL & LR)(ej: `!team g2`, `!team navi`)\n"
            "`!live` - Muestra informacion sobre los jugadores del actualmente en partida \n"
            "`!info <jugador>` - Muestra información acerca de jugadores Trackeados/SoloQ Europeo en partida (ej: `!info Elyoya` , `!info Biotic`)\n"
            "`!match <nombrejugador>` - Muestra la partida activa de un jugador si está en vivo (ej: `!match elk`)\n"
            "`!historial` - Muestra historial general de las últimas partidas trackeadas\n"
            "`!historial <jugador>` - Muestra las últimas partidas de un jugador (en total)\n"
            "`!historial <cuenta>` - Muestra las últimas partidas de la cuenta de un jugador\n"
            "`!ranking` - Muestra la tabla de clasificación actual de los jugadores trackeados\n"
            "\n"
            
            "**📘 Comandos Esports:**\n"
            "`!setlivechannel` - Configura este canal para notificaciones automáticas de partidas de esports (Todas las ligas)\n"
            "`!removelivechannel` - Elimina el canal de notificaciones de partidas de esports (Todas las ligas)\n"
            "`!partida` - Muestra partidas en vivo de esports (Todas las ligas) o próximas a comenzar\n"
            "`!next` - Muestra hora y fecha de próximas partidas de esports (Todas las ligas)\n"
            
            
            
            "**🎮 Comandos Jetacup (grupo `!jetacup`):**\n"
            "`!jetacup` - Muestra datos acerca de la Jetacup 2\n"
            "`!jetacup registro` - Inicia tu registro para la Jetacup 2 paso a paso\n"
            "`!jetacup cancelarregistro` - Cancela un registro en curso (antes de que se guarde)\n"
            "`!jetacup cancelarinscripcion` - Elimina tu inscripción si ya está guardada\n"
            "`!jetacup registrados` - Muestra tabla de los jugadores registrados\n"
            "\n"
            "⏰ Las horas de inicio y partidas se muestran automáticamente en tu zona horaria local gracias a Discord.\n"
            "⚠️ Si ves un mensaje de *rate limit* en las partidas, significa que Riot está limitando las peticiones.\n"
            "En ese caso, el bot usará datos de respaldo que suelen actualizarse en pocos segundos.\n"
        )
        
        await ctx.send(help_text)
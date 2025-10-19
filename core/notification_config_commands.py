# # core/notification_config_commands.py
import nextcord
from nextcord.ext import commands
from tracking.soloq.channel_config import save_channel_id, remove_channel_id


def register_notification_config_commands(bot: commands.Bot):
    @bot.command(name="setchannel")
    async def setchannel(ctx: commands.Context):
        """
        Registra el canal actual como receptor de notificaciones de partidas activas.
        """
        channel = ctx.channel
        guild_id = ctx.guild.id if ctx.guild else None
        if not guild_id:
            await ctx.send("❌ Este comando solo puede usarse en un servidor.")
            return

        
        
        
        save_channel_id(guild_id, channel.id)
        if isinstance(channel, nextcord.TextChannel):
            await ctx.send(f"✅ Canal de notificaciones establecido en {channel.mention}")
        else:
            await ctx.send("✅ Canal de notificaciones establecido.")

    @bot.command(name="unsubscribe")
    async def unsubscribe(ctx: commands.Context):
        """
        Desactiva las notificaciones de partidas activas para este servidor.
        """
        guild_id = ctx.guild.id if ctx.guild else None
        if not guild_id:
            await ctx.send("❌ Este comando solo puede usarse en un servidor.")
            return

        remove_channel_id(guild_id)
        await ctx.send("✅ Notificaciones desactivadas para este servidor.")

# core/commands.py

from core.register_team_commands import register_team_commands
from core.register_player_commands import register_match_command
from core.info_command import register_info_command
from core.live_command import register_live_command
from core.help_commands import register_help_command
from core.ranking_command import register_ranking_command
from core.notification_config_commands import register_notification_config_commands
from core.historial_commands import register_historial_command
from copa.registro import register_copa_commands


async def register_esports_commands(bot):
    from esports_extension.bot.commands import setup as esports_setup
    await esports_setup(bot)

async def register_commands(bot):
    register_team_commands(bot)
    register_match_command(bot)
    register_info_command(bot)
    register_live_command(bot)
    register_help_command(bot)  # <-- agrega esto
    register_notification_config_commands(bot)
    register_ranking_command(bot)
    register_historial_command(bot)
    register_copa_commands(bot)
    await register_esports_commands(bot)
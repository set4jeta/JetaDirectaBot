import nextcord
from nextcord.ext import commands
from config import DISCORD_TOKEN
from core.commands import register_commands
from core.background_tasks import start_background_tasks
import asyncio

intents = nextcord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    await bot.change_presence(activity=nextcord.Game(name="Escribe !help"))
    print(f"✅ Bot conectado como {bot.user}")

@bot.event
async def on_guild_join(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send("¡Hola! Usa `!help` para ver la lista de comandos del bot.")
            break

async def main():
    await register_commands(bot)           # <- ahora esto es async
    start_background_tasks(bot)           # <- sigue siendo sync
    await bot.start(DISCORD_TOKEN)        # type: ignore # <- asegurado que el token no es None

if __name__ == "__main__":
    asyncio.run(main())
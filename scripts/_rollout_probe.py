"""¿`get_application_commands(rollout=True)` ve los 15 antes de conectar?

El banner de arranque avisó "sin forma slash: help, historial, ..." mientras
nextcord todavía estaba registrando comandos. La causa: `on_ready` corre antes de
que acabe el registro, y `get_application_commands()` (sin rollout) solo devuelve
los que ya tienen id de Discord.

`Client.on_connect` llama a `add_all_application_commands()`, que mete los 15 en
`state._application_commands`. `get_application_commands(rollout=True)` lee de ahí
usando `is_global`, así que debería verlos todos en cuanto conecta, sin esperar el
registro. Aquí se comprueba sin tocar la red.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nextcord
from nextcord.ext import commands


async def main() -> None:
    intents = nextcord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    from core.commands import register_commands

    await register_commands(bot)

    prefijo = sorted({c.name for c in bot.commands})
    print(f"prefijo                          : {len(prefijo)}")

    print(f"pendientes (_to_add)             : {len(getattr(bot, '_application_commands_to_add', []) or [])}")
    print(f"get_application_commands()       : {len(bot.get_application_commands())}")
    print(f"get_application_commands(rollout): {len(bot.get_application_commands(rollout=True))}")

    # Esto es lo que hace nextcord en on_connect, antes de registrar nada.
    bot.add_all_application_commands()

    sin_rollout = bot.get_application_commands()
    con_rollout = bot.get_application_commands(rollout=True)
    print("\ntras add_all_application_commands() (lo que hace on_connect):")
    print(f"   get_application_commands()       : {len(sin_rollout)}")
    print(f"   get_application_commands(rollout): {len(con_rollout)}")

    slash = sorted(
        c.name
        for c in con_rollout
        if isinstance(c, nextcord.SlashApplicationCommand)
    )
    print(f"\nslash vistos ({len(slash)}): {', '.join(slash)}")
    faltan = sorted(set(prefijo) - set(slash))
    print("sin forma slash:", ", ".join(faltan) if faltan else "ninguno")


asyncio.run(main())

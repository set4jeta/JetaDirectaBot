"""Prueba: ¿el bot y el event loop que corre son el mismo?

Reproduce exactamente lo que hace main.py:
  1. importa un módulo que crea commands.Bot() a nivel de módulo (sin loop vivo)
  2. luego llama a asyncio.run(...)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nextcord
from nextcord.ext import commands

# --- Igual que core/bot_launcher.py: a nivel de módulo, sin loop corriendo ---
intents = nextcord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

print("A) bot creado en import time")
print("   id(bot.loop)            =", id(bot.loop))
print("   bot.loop.is_running()   =", bot.loop.is_running())
print("   id(bot._connection.loop)=", id(bot._connection.loop))


async def dentro():
    vivo = asyncio.get_running_loop()
    print("B) dentro de asyncio.run()")
    print("   id(loop vivo)           =", id(vivo))
    print("   id(bot.loop)            =", id(bot.loop))
    print("   ¿MISMO LOOP?            =", vivo is bot.loop)
    print("   id(bot._connection.loop)=", id(bot._connection.loop))
    print("   ¿state en el vivo?      =", vivo is bot._connection.loop)

    # Lo que hace KeepAliveHandler desde su hilo:
    #   asyncio.run_coroutine_threadsafe(coro, loop=ws.loop)  con ws.loop = client.loop
    import concurrent.futures

    async def latido():
        return "enviado"

    fut = asyncio.run_coroutine_threadsafe(latido(), loop=bot.loop)
    try:
        print("   latido a bot.loop       =", fut.result(3))
    except concurrent.futures.TimeoutError:
        print("   latido a bot.loop       = TIMEOUT (nunca se envía)")
    except Exception as exc:
        print("   latido a bot.loop       = ERROR", type(exc).__name__, exc)


asyncio.run(dentro())

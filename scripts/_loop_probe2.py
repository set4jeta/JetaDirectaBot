"""¿Qué se rompe de verdad por tener dos event loops?

`core/bot_launcher.py` crea `commands.Bot()` a nivel de módulo, sin loop vivo.
nextcord entonces hace `asyncio.new_event_loop()` y lo guarda en `bot.loop`.
Luego `main.py` hace `asyncio.run(...)`, que crea OTRO loop. `bot.loop` nunca se
reasigna.

Se comprueban las dos consecuencias:
  1. el latido del gateway (`run_coroutine_threadsafe` contra `bot.loop`)
  2. `bot.wait_for(...)`, que hace `self.loop.create_future()`
"""
import asyncio
import concurrent.futures
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nextcord
from nextcord.ext import commands

intents = nextcord.Intents.default()
intents.message_content = True


def nuevo_bot():
    return commands.Bot(command_prefix="!", intents=intents, help_command=None)


def alinear(bot, loop) -> None:
    """El arreglo: apuntar el bot y su estado al loop que de verdad corre."""
    bot.loop = loop
    if getattr(bot, "_connection", None) is not None:
        bot._connection.loop = loop


async def probar(bot, etiqueta: str) -> None:
    vivo = asyncio.get_running_loop()
    print(f"\n=== {etiqueta} ===")
    print("   bot.loop is loop vivo :", bot.loop is vivo)

    # 1) El latido: KeepAliveHandler hace esto desde un hilo aparte.
    async def latido():
        return "ok"

    fut = asyncio.run_coroutine_threadsafe(latido(), loop=bot.loop)
    try:
        print("   latido del gateway    :", fut.result(2))
    except concurrent.futures.TimeoutError:
        print("   latido del gateway    : TIMEOUT -> 'heartbeat blocked'")

    # 2) wait_for: crea el future en bot.loop y lo resuelve el dispatch, que
    #    corre en el loop vivo. Lo usa cualquier flujo conversacional del bot.
    async def esperar():
        return await bot.wait_for("message", timeout=2)

    tarea = asyncio.ensure_future(esperar())
    await asyncio.sleep(0.1)

    class MsgFalso:
        content = "hola"
        author = None
        channel = None

    bot.dispatch("message", MsgFalso())
    try:
        await asyncio.wait_for(asyncio.shield(tarea), timeout=2)
        print("   bot.wait_for          : responde")
    except (asyncio.TimeoutError, TimeoutError):
        print("   bot.wait_for          : SE QUEDA COLGADO")
    except Exception as exc:
        print("   bot.wait_for          :", type(exc).__name__, exc)
    finally:
        tarea.cancel()


async def main() -> None:
    roto = nuevo_bot()
    await probar(roto, "SIN ARREGLO (lo que corre ahora)")

    arreglado = nuevo_bot()
    alinear(arreglado, asyncio.get_running_loop())
    await probar(arreglado, "CON ARREGLO")


asyncio.run(main())

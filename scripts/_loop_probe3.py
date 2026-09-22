"""¿Qué se rompe por tener dos event loops? (versión válida)

`core/bot_launcher.py` crea `commands.Bot()` **a nivel de módulo**, cuando no hay
ningún loop corriendo. nextcord hace entonces `asyncio.new_event_loop()` y lo
guarda en `bot.loop`. Después `main.py` llama a `asyncio.run(...)`, que crea OTRO
loop, y `bot.loop` no se reasigna nunca.

Este script reproduce ese orden exacto: el bot se crea aquí, en el import, y solo
después se entra en `asyncio.run`.
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

# --- IMPORT TIME, igual que core/bot_launcher.py línea 39 ---
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
LOOP_HUERFANO = bot.loop
print("import time: bot.loop creado por nextcord, is_running =", bot.loop.is_running())


def _submit_desde_hilo(loop) -> str:
    """Lo que hace KeepAliveHandler: submit desde SU hilo, no desde el loop.

    Ojo: esto se ejecuta con `asyncio.to_thread`, para que el loop vivo siga
    libre. Si se bloqueara el loop con un `join()`, el caso "con arreglo"
    también daría timeout y la prueba no valdría para nada.
    """

    async def beat():
        return "enviado"

    fut = asyncio.run_coroutine_threadsafe(beat(), loop=loop)
    try:
        return fut.result(3)
    except concurrent.futures.TimeoutError:
        return "TIMEOUT -> 'heartbeat blocked for more than N seconds'"
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


async def comprobar(etiqueta: str) -> None:
    vivo = asyncio.get_running_loop()
    print(f"\n=== {etiqueta} ===")
    print("   bot.loop is loop vivo :", bot.loop is vivo)
    print("   latido del gateway    :", await asyncio.to_thread(_submit_desde_hilo, bot.loop))

    # wait_for hace self.loop.create_future(): si loop != vivo, el await falla.
    async def esperar():
        return await bot.wait_for("message", timeout=2)

    tarea = asyncio.ensure_future(esperar())
    await asyncio.sleep(0.05)
    try:
        await asyncio.wait_for(tarea, timeout=2)
        print("   bot.wait_for          : ok")
    except (asyncio.TimeoutError, TimeoutError):
        print("   bot.wait_for          : timeout (nadie despachó, normal)")
    except Exception as exc:
        print(f"   bot.wait_for          : {type(exc).__name__}: {exc}")


async def main() -> None:
    await comprobar("SIN ARREGLO (lo que corre ahora)")

    # El arreglo: apuntar bot y estado al loop que de verdad corre.
    vivo = asyncio.get_running_loop()
    bot.loop = vivo
    bot._connection.loop = vivo
    await comprobar("CON ARREGLO")


asyncio.run(main())
LOOP_HUERFANO.close()

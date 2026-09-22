"""Arranque y apagado del bot de Discord.

Por qué hace falta un cierre ordenado
-------------------------------------
Varias cosas del bot escriben **en diferido**: `core.rank_data.save_rank_data`
acumula rangos en memoria y solo toca el disco cada `RANK_FLUSH_INTERVAL`
(30 s), porque antes cada llamada reescribía los 316 KB del fichero entero.
Además hay dos sesiones `aiohttp` compartidas (Riot y dpm.lol) que conviene
cerrar en vez de dejar que las recoja el intérprete.

`stop_background_tasks()` existía desde hace tiempo pero **nadie la llamaba**:
`start_background_tasks(bot)` se invocaba aquí y no había contrapartida. Al
morir el proceso se perdía todo lo que no se hubiera volcado.

Y no basta con un `try/finally`: Render, Docker y systemd apagan mandando
**SIGTERM**, cuya acción por defecto es terminar el proceso *sin* desenrollar la
pila, así que el `finally` nunca se ejecuta. Hay que interceptar la señal.

Los dos event loops
-------------------
`commands.Bot()` se construye aquí, **a nivel de módulo**, porque los
decoradores `@bot.event` lo necesitan. En ese momento no hay ningún loop
corriendo, así que nextcord hace `asyncio.new_event_loop()` y lo guarda en
`bot.loop` (`nextcord/client.py:312-314`). Después `main.py` llama a
`asyncio.run(main())`, que crea **otro** loop, y `bot.loop` no se reasigna nunca.

Consecuencias medidas en una ejecución real de 20 minutos:

* `KeepAliveHandler` corre en un hilo aparte y manda el latido con
  `run_coroutine_threadsafe(coro, loop=ws.loop)`, donde `ws.loop` es
  `client.loop`. Es decir: a un loop que nadie ejecuta. La corrutina se queda en
  la cola para siempre, `f.result(10)` expira, y nextcord imprime
  `heartbeat blocked for more than N seconds` con el traceback del loop entero
  **cada 10 s, subiendo sin parar** (se llegó a 800 s). El contador no se
  reinicia porque es el mismo `while True` que nunca sale.
* `self._last_send` solo se actualiza si el envío termina, así que se queda con
  el valor del arranque y `ack()` calcula una latencia que crece sin límite:
  `websocket is 49.8s behind`, luego 99.4, 149.0... +49.6 cada vez.
* La conexión no se cae porque Discord pide latidos con el opcode 1 y esos sí se
  responden desde `received_message`, que corre en el loop de verdad. O sea: el
  bot funciona, pero su consola es ilegible y `bot.latency` es basura.
* `bot.wait_for()` hace `self.loop.create_future()`. Con dos loops eso revienta
  con `RuntimeError: got Future attached to a different loop`, reproducido en
  `scripts/test_event_loop.py`. Cualquier flujo conversacional del bot lo
  necesita, así que era un fallo real, no cosmético.

`_alinear_event_loop()` apunta el bot y su `ConnectionState` al loop que de
verdad corre, antes de conectar. Rebindear es seguro en Python 3.10+: `Lock`,
`Event` y compañía ya no capturan el loop al crearse.
"""

from __future__ import annotations

import asyncio
import signal

import nextcord
from nextcord.ext import commands

from config import DISCORD_TOKEN
from core import arranque
from core.background_tasks import start_background_tasks, stop_background_tasks
from core.commands import register_commands
from utils.i18n import idioma_de_servidor, t
from utils.logger import get_logger

log = get_logger("core.bot_launcher")

intents = nextcord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

#: El loop que nextcord se inventó al construir el bot (ver docstring). Se
#: guarda para poder cerrarlo y no dejar el aviso de recurso sin liberar.
_loop_huerfano: asyncio.AbstractEventLoop | None = bot.loop

# El apagado puede dispararse desde dos sitios a la vez: el manejador de señal y
# el `finally` de `main()`. Con un simple booleano el segundo volvía antes de
# tiempo y `asyncio.run` cancelaba el volcado a medias, que es justo lo que se
# quería evitar. Con un evento, el segundo en llegar **espera** al primero.
_apagando = False
_apagado_listo: asyncio.Event | None = None


@bot.event
async def on_ready():
    # La presencia decía "Escribe !help", que tras la migración a slash es la
    # forma antigua y la que Discord no autocompleta.
    await bot.change_presence(
        activity=nextcord.Activity(
            type=nextcord.ActivityType.watching, name="SoloQ de pros | /help"
        )
    )
    arranque.mostrar(bot)


@bot.event
async def on_guild_join(guild):
    # El idioma sale de `preferred_locale` del servidor, no de `/lang`: este
    # mensaje se manda antes de que nadie haya podido configurarlo.
    texto = t("bienvenida.saludo", idioma_de_servidor(guild))
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(texto)
            break


# ---------------------------------------------------------------------- #
# Event loop
# ---------------------------------------------------------------------- #

def _alinear_event_loop(destino: asyncio.AbstractEventLoop) -> bool:
    """Apunta el bot al loop que de verdad corre. True si hubo que cambiarlo.

    Ver el docstring del módulo: sin esto el latido del gateway se manda a un
    loop que nadie ejecuta y la consola se llena de `heartbeat blocked`.

    Se hace antes de `bot.start()`, así que no hay nada en vuelo que pueda
    quedarse atado al loop viejo.
    """
    if bot.loop is destino:
        return False

    bot.loop = destino
    # `ConnectionState` recibió el loop por parámetro y lo usa para
    # `create_future()` (chunking de miembros, `wait_for`).
    if getattr(bot, "_connection", None) is not None:
        bot._connection.loop = destino

    # El loop que nextcord creó de más: cerrarlo evita el
    # "unclosed event loop" de ResourceWarning al salir.
    global _loop_huerfano
    if _loop_huerfano is not None and _loop_huerfano is not destino:
        if not _loop_huerfano.is_running():
            _loop_huerfano.close()
        _loop_huerfano = None

    # asyncio.set_event_loop lo dejó apuntando al huérfano al construir el bot.
    asyncio.set_event_loop(destino)
    return True


# ---------------------------------------------------------------------- #
# Apagado
# ---------------------------------------------------------------------- #

async def _apagar(motivo: str) -> None:
    """Para las tareas, vuelca lo pendiente y cierra la conexión de Discord.

    Reentrante: si ya hay un apagado en curso, espera a que termine en vez de
    volver enseguida. Sin eso, el `finally` de `main()` devolvía el control y
    `asyncio.run` cancelaba el volcado de rangos por la mitad.
    """
    global _apagando, _apagado_listo

    if _apagado_listo is None:
        _apagado_listo = asyncio.Event()

    if _apagando:
        await _apagado_listo.wait()
        return
    _apagando = True

    log.info("Apagando (%s)...", motivo)
    try:
        await stop_background_tasks()
    except Exception:
        # Si algo falla aquí, cerrar Discord de todas formas: es preferible
        # perder un flush a quedarse colgado hasta el SIGKILL.
        log.exception("Error parando las tareas de fondo.")

    try:
        if not bot.is_closed():
            await bot.close()
    finally:
        _apagado_listo.set()



def _senales_soportadas() -> tuple:
    """Señales de apagado que existen en esta plataforma.

    `SIGBREAK` solo existe en Windows, y ahí es la única que otro proceso puede
    mandar de forma fiable (`SIGTERM` en Windows no se puede enviar: `os.kill`
    llama a `TerminateProcess`, que no ejecuta manejadores). En Linux —Render—
    la que llega es `SIGTERM`.
    """
    sigs = [signal.SIGTERM, signal.SIGINT]
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        sigs.append(sigbreak)
    return tuple(sigs)


def _instalar_senales(loop: asyncio.AbstractEventLoop) -> None:
    """Engancha las señales de apagado al cierre ordenado.

    `loop.add_signal_handler` es la forma correcta en POSIX —que es donde corre
    Render— pero no está implementada en Windows. Allí se cae a `signal.signal`,
    que se ejecuta en el hilo principal y necesita `call_soon_threadsafe` para
    volver al event loop.
    """
    for sig in _senales_soportadas():
        nombre = sig.name
        try:
            loop.add_signal_handler(
                sig, lambda s=nombre: asyncio.ensure_future(_apagar(s))
            )
            continue
        except (NotImplementedError, AttributeError, RuntimeError, ValueError):
            pass

        try:
            signal.signal(
                sig,
                lambda *_a, s=nombre: loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(_apagar(s))
                ),
            )
        except (OSError, ValueError):
            log.debug("No se pudo enganchar %s en esta plataforma.", nombre)


# ---------------------------------------------------------------------- #
# Arranque
# ---------------------------------------------------------------------- #

async def main():
    if not DISCORD_TOKEN:
        # `main.py` ya lo comprueba, pero este módulo también se arranca solo
        # con `python -m core.bot_launcher`.
        raise RuntimeError("La variable DISCORD_TOKEN no está definida en .env")

    loop = asyncio.get_running_loop()

    # Antes de cualquier otra cosa: el bot se construyó sin loop vivo y apunta a
    # uno que nadie ejecuta. Ver el docstring del módulo.
    if _alinear_event_loop(loop):
        log.debug("Bot realineado al event loop en ejecución.")

    _instalar_senales(loop)

    await register_commands(bot)
    start_background_tasks(bot)

    try:
        await bot.start(DISCORD_TOKEN)
    except asyncio.CancelledError:
        # `bot.close()` desde el handler de señal cancela `bot.start()`.
        pass
    finally:
        # Red de seguridad para las salidas que no vienen de una señal (token
        # inválido, desconexión irrecuperable, excepción en un evento).
        await _apagar("bot.start ha terminado")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Solo llega aquí si no se pudo enganchar SIGINT; el volcado ya lo ha
        # hecho el `finally` de `main()`.
        pass

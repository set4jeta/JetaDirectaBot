"""Logging centralizado del bot.

Antes este archivo estaba vacío y el proyecto usaba print() por todas partes
(más de 150 llamadas repartidas en 8 módulos). Este módulo da un punto único
para configurar el nivel por variable de entorno y silenciar el ruido de red.

Por qué se fuerza UTF-8 en la salida
------------------------------------
Los mensajes del bot llevan emoji (🟢 🔴 ⏱️ ✅). Si la consola no está en UTF-8
—el caso por defecto de `cmd.exe` en Windows, que usa cp1252— el handler de
logging **no puede escribir la línea** y suelta un `UnicodeEncodeError` con su
propia traza por pantalla, en vez del mensaje. Comprobado:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\U0001f7e2'

Y no es un fallo cosmético: cada línea con emoji se convierte en 12 líneas de
traza, que es justo lo contrario de "que la consola esté clara".
"""

import logging
import os
import sys

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-26s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_NOISY_LOGGERS = ("aiohttp", "urllib3", "asyncio", "PIL")

#: Mensajes concretos que no aportan nada y salen siempre. El de PyNaCl es el
#: primero que se ve al arrancar y avisa de que no habrá voz: este bot no usa
#: voz, así que es una advertencia sobre algo que nunca va a pasar.
_MENSAJES_IGNORADOS = ("PyNaCl is not installed",)


class _SinRuido(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        mensaje = str(record.msg)
        return not any(frag in mensaje for frag in _MENSAJES_IGNORADOS)


def _forzar_utf8() -> None:
    """Pone la salida estándar en UTF-8 si se puede.

    `errors="replace"` es la red de seguridad: si aun así hay un carácter que no
    entra, sale un "?" en vez de tumbar la línea entera.
    """
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            # Salida redirigida a algo que no admite reconfiguración.
            pass


def configure_logging(level: str | None = None) -> None:
    """Configura el logger raíz. Idempotente: seguro llamarla varias veces."""
    root = logging.getLogger()
    if root.handlers:
        return
    _forzar_utf8()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(_SinRuido())
    root.setLevel(level or LOG_LEVEL)
    root.addHandler(handler)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)

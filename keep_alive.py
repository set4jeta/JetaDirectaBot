# keep_alive.py
"""Servidor HTTP mínimo para que los PaaS que esperan un puerto abierto no
consideren el bot caído.

Dos detalles que importan:

* **El hilo es `daemon`.** Antes no lo era, y un hilo no-demonio impide que el
  intérprete termine: al cerrar el bot el proceso se quedaba colgado esperando a
  un servidor Flask que no acaba nunca, hasta que el gestor mandaba SIGKILL. Con
  `daemon=True` el hilo muere con el proceso.
* **Respeta `$PORT`.** Render (y Heroku, y Fly) inyectan el puerto que quieren
  que escuches; 8080 estaba fijo en el código.
"""

import os
from threading import Thread

from flask import Flask

app = Flask(__name__)

PORT = int(os.getenv("PORT", "8080"))


@app.route("/")
def home():
    return "Bot is alive!"


def run():
    # `use_reloader=False`: el reloader de Flask relanza el proceso entero, lo
    # que duplicaría el bot de Discord.
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)


def keep_alive() -> Thread:
    t = Thread(target=run, name="keep-alive", daemon=True)
    t.start()
    return t

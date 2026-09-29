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

from flask import Flask, jsonify, request

app = Flask(__name__)

PORT = int(os.getenv("PORT", "8080"))

#: Token para el endpoint de grabación. Vacío = sin comprobación, que es lo
#: cómodo para probar en local. En producción conviene ponerlo: el listado lleva
#: claves de espectador de partidas en curso, y con ellas cualquiera puede
#: meterse a mirar. No es un secreto grave —la API las da a quien tenga key—
#: pero tampoco hay razón para publicarlas en abierto.
TOKEN_GRABADOR = os.getenv("RECORDER_TOKEN", "")


@app.route("/")
def home():
    return "Bot is alive!"


@app.route("/live-games")
def live_games():
    """Las partidas que el bot tiene detectadas ahora mismo.

    Existe para el grabador: en vez de que pregunte a Riot por su cuenta y
    compita por la misma cuota —que es lo que pasó el 29-09-2026, con veinte
    minutos de `429`—, lee lo que el bot ya sabe. El grabador solo habla después
    con el servidor de espectadores, que es otra cuota distinta.

    Devuelve **solo** lo necesario para grabar: partida, servidor, clave, pros y
    cuándo se detectó. Nada de canales, servidores de Discord ni usuarios.
    """
    if TOKEN_GRABADOR and request.args.get("token") != TOKEN_GRABADOR:
        return jsonify({"error": "token"}), 403

    from tracking.soloq import partidas_en_vivo

    return jsonify(partidas_en_vivo.listado())


def run():
    # `use_reloader=False`: el reloader de Flask relanza el proceso entero, lo
    # que duplicaría el bot de Discord.
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)


def keep_alive() -> Thread:
    t = Thread(target=run, name="keep-alive", daemon=True)
    t.start()
    return t

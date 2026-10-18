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


@app.route("/health")
def health():
    """El estado del bot, para poder mirarlo **desde fuera** de Discord.

    Por qué existe
    --------------
    El consumo de ancho de banda ya se podía consultar con el comando `/health`
    dentro de Discord. El problema es el momento en el que hace falta: cuando
    Render suspende el servicio por pasarse de los 5 GB, **el bot ya no está
    conectado y no hay a quién preguntar**. Justo la pregunta que importa
    —«¿cuánto llevo gastado?»— era la única que no se podía hacer.

    Esto la contesta por HTTP, que sigue respondiendo mientras el proceso viva.

    Lo que devuelve es una **estimación** del propio bot (ver `utils/egress.py`),
    no la cifra del proveedor: sirve para ver la tendencia y cortar a tiempo, no
    para cuadrar la factura. El número bueno está en el panel de Render.

    No lleva nada privado: ni canales, ni servidores, ni usuarios.
    """
    from utils import egress

    datos = egress.estado()
    return jsonify({
        "vivo": True,
        "salida": {
            "mes": datos["mes"],
            "mb": round(datos["mb"], 1),
            "tope_mb": round(datos["tope_mb"], 1),
            "porcentaje": round(datos["porcentaje"], 1),
            "mensajes": datos["mensajes"],
            "adjuntos": datos["adjuntos"],
            "aviso": ("por encima del presupuesto: no se adjunta el .bat"
                      if datos["porcentaje"] >= 100 else
                      "se adjunta el .bat" if datos["porcentaje"] >= 80 else
                      "normal"),
        },
    })


def run():
    # `use_reloader=False`: el reloader de Flask relanza el proceso entero, lo
    # que duplicaría el bot de Discord.
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)


def keep_alive() -> Thread:
    t = Thread(target=run, name="keep-alive", daemon=True)
    t.start()
    return t

"""Las partidas en vivo que el bot ya ha detectado, para que las lea el grabador.

Por qué existe
--------------
El bot barre cada 30 s y **ya sabe** quién está en partida, en qué servidor y con
qué clave de espectador. Un grabador que preguntara lo mismo por su cuenta haría
dos cosas malas:

1. **Competiría por la cuota de la API.** Medido el 29-09-2026: un script aparte
   consultando 55 jugadores se pasó veinte minutos recibiendo `429`, porque la
   pasada del bot casi satura `spectator-v5` ella sola. Los dos comparten la misma
   key, así que se estorban.
2. **Duplicaría el trabajo.** El bot ya pagó esas peticiones.

Así que el bot **publica** lo que sabe y el grabador lo **lee**. El grabador solo
habla después con el servidor de espectadores, que es otro servidor y otra cuota,
y ahí no molesta a nadie.

Qué publica y qué no
--------------------
Solo lo imprescindible para grabar: identificador de la partida, servidor, clave
de espectador, los pros que hay dentro y cuándo se detectó. **Nada de canales, ni
servidores de Discord, ni usuarios**: esto sale del proceso y lo lee un programa
de fuera, así que la regla de privacidad del resto del proyecto vale igual aquí.

Por qué hay que publicar pronto
-------------------------------
El servidor de espectadores **solo sirve datos desde el momento en que te
conectas**. Comprobado: entrando a una partida que llevaba diez minutos se recibe
el chunk 1 y los de ese momento, y los intermedios no existen. Por eso una partida
completa exige empezar a grabar en los primeros segundos, y por eso esto publica
en cuanto se detecta y no al final.
"""

from __future__ import annotations

import time
from typing import Any

from utils.logger import get_logger

log = get_logger("tracking.partidas_en_vivo")

#: Cuánto se recuerda una partida sin que nadie la renueve. Una partida dura como
#: mucho una hora, así que a los 90 minutos lo que quede ahí ya no se puede
#: grabar y solo ocupa sitio.
CADUCA_S = 90 * 60

#: `game_id -> {game_id, plataforma, clave, pros, detectada, actualizada}`.
_partidas: dict[int, dict[str, Any]] = {}


def publicar(match, pros: list[str]) -> None:
    """Registra (o refresca) una partida detectada. Nunca levanta.

    Se llama desde el bucle de avisos, así que **no puede tumbar un aviso**: un
    fallo aquí no puede costar que alguien se quede sin su notificación. Es un
    dato auxiliar para un programa de fuera, no parte del producto.
    """
    try:
        datos = getattr(match, "datos_extra", None) or {}
        clave = (datos.get("observers") or {}).get("encryptionKey")
        if not clave:
            return

        game_id = match.game_id
        ahora = time.time()
        entrada = _partidas.get(game_id)

        if entrada is None:
            _partidas[game_id] = {
                "game_id": game_id,
                "plataforma": (match.platform or "").upper(),
                "clave": clave,
                "pros": list(pros),
                "detectada": ahora,
                "actualizada": ahora,
            }
            log.debug("Partida %s publicada para grabación (%s)", game_id, pros)
            return

        # Ya estaba: se refresca el latido y se suman los pros nuevos. Un partido
        # con tres pros se detecta tres veces (una por jugador), y las tres tienen
        # que quedar reflejadas: el número de pros es el criterio para decidir qué
        # grabar.
        entrada["actualizada"] = ahora
        for nombre in pros:
            if nombre not in entrada["pros"]:
                entrada["pros"].append(nombre)
    except Exception:
        log.debug("No se pudo publicar la partida para grabación", exc_info=True)


def listado() -> dict[str, Any]:
    """Lo que hay ahora mismo, ya sin lo caducado. Es lo que sirve el endpoint."""
    ahora = time.time()
    for game_id in [g for g, d in _partidas.items()
                    if ahora - d["actualizada"] > CADUCA_S]:
        del _partidas[game_id]

    return {
        "generado": ahora,
        "partidas": sorted(
            _partidas.values(), key=lambda p: (-len(p["pros"]), -p["detectada"])
        ),
    }


def cuantas() -> int:
    """Cuántas hay vivas. Para `/health` y el log."""
    return len(listado()["partidas"])


def vaciar() -> None:
    """Para las pruebas."""
    _partidas.clear()

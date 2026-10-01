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

Cómo sale del proceso: dos caminos, un solo dato
------------------------------------------------
Esto es la **única** fuente de lo que se publica. De aquí salen los dos transportes:

- **HTTP**, en `GET /live-games`, para cuando el bot está desplegado en Render y el
  grabador corre en otro sitio.
- **Un fichero**, `partidas_vivo.json` en la raíz del proyecto, para cuando el bot y
  el grabador están **en el mismo PC** — que es el caso normal. Así el grabador no
  necesita que haya un servidor escuchando en un puerto para enterarse de que hay
  una partida.

Los dos leen de `listado()`, así que no pueden discrepar. Añadir un tercer camino
que leyera la caché por su cuenta sería garantizar que un día digan cosas distintas.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from utils.logger import get_logger

log = get_logger("tracking.partidas_en_vivo")

#: Cuánto se recuerda una partida sin que nadie la renueve. Una partida dura como
#: mucho una hora, así que a los 90 minutos lo que quede ahí ya no se puede
#: grabar y solo ocupa sitio.
CADUCA_S = 90 * 60

#: Dónde se deja el fichero para el grabador del mismo PC. En la raíz del
#: proyecto, para que el grabador tenga una ruta fija.
FICHERO = Path(__file__).resolve().parents[2] / "partidas_vivo.json"

#: Cuánto se espera entre escrituras del fichero. La lista cambia una vez por
#: jugador detectado, y con 200 cuentas eso serían muchas escrituras por pasada
#: para un fichero que se lee cada minuto. Diez segundos sobran.
MINIMO_ENTRE_ESCRITURAS_S = 10.0

#: Si falla la primera escritura se deja de intentar: en Render el disco puede ser
#: de solo lectura y no tiene sentido llenar el log con el mismo error cada 30 s.
_degradado = False
_ultima_escritura = 0.0

#: `game_id -> {game_id, plataforma, clave, pros, detectada, actualizada}`.
_partidas: dict[int, dict[str, Any]] = {}


def _escribir_fichero() -> None:
    """Deja la lista en `partidas_vivo.json`, si toca. Nunca levanta.

    Va en `try/except` y con un `_degradado` que la apaga al primer fallo: esto es
    un extra para el grabador, no puede costar que alguien se quede sin su aviso.
    """
    global _degradado, _ultima_escritura
    if _degradado:
        return
    ahora = time.time()
    if ahora - _ultima_escritura < MINIMO_ENTRE_ESCRITURAS_S:
        return

    try:
        # Escritura atómica: primero un temporal y luego se renombra, para que el
        # grabador no lea nunca un fichero a medio escribir.
        temporal = FICHERO.with_suffix(".json.tmp")
        temporal.write_text(
            json.dumps(listado(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, FICHERO)
        _ultima_escritura = ahora
    except Exception:                                         # noqa: BLE001
        _degradado = True
        log.warning("No se pudo escribir partidas_vivo.json; se deja de intentar",
                    exc_info=True)


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

        # `gameLength` es el reloj del **servidor de espectadores**: va unos tres
        # minutos por detrás de la partida y arranca en negativo. Se guarda tal
        # cual, sin normalizar. El grabador lo usa para ordenar las candidatas y
        # mirar primero las que acaban de empezar, que son las únicas que se
        # pueden grabar enteras — y así no gasta peticiones preguntando por las 30.
        duracion = datos.get("gameLength")

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
                "game_length": duracion if isinstance(duracion, int) else None,
            }
            log.debug("Partida %s publicada para grabación (%s)", game_id, pros)
        else:
            # Ya estaba: se refresca el latido y se suman los pros nuevos. Un
            # partido con tres pros se detecta tres veces (una por jugador), y las
            # tres tienen que quedar reflejadas: el número de pros es el criterio
            # para decidir qué grabar.
            entrada["actualizada"] = ahora
            if isinstance(duracion, int):
                entrada["game_length"] = duracion
            for nombre in pros:
                if nombre not in entrada["pros"]:
                    entrada["pros"].append(nombre)

        _escribir_fichero()
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

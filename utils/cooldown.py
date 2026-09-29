"""Freno por usuario, para que uno no retrase los avisos de todos.

Por qué existe
--------------
El bot tiene un limitador de la API de Riot, pero es **global**: reparte la cuota
entre todo el que la pida, sin distinguir quién. Y no había ningún límite por
usuario en los comandos.

Consecuencia, medida el 29-09-2026: alguien que machaque `/info` en bucle no
puede pasarse de la cuota —el limitador lo impide— pero **compite con el tracker
en la misma cola**, y el tracker es lo que manda los avisos. Es decir: un solo
usuario insistente puede retrasar los avisos de todo el mundo. No tumba el bot,
lo degrada, que es más difícil de ver y de diagnosticar.

Qué NO es esto
--------------
No es una defensa contra un ataque. Los comandos llegan por el gateway de
Discord, así que quien abusa tiene que pasar antes por los límites de Discord.
Esto es para el caso normal y molesto: el que descubre el bot y prueba veinte
cosas seguidas, o el que deja un bucle abierto sin querer.

Cómo funciona
-------------
Un cubo de fichas por usuario. Cada comando gasta una; se reponen a razón de una
cada pocos segundos. Con la capacidad por defecto (10) alguien puede encadenar
diez comandos seguidos —que es mucho más de lo que hace nadie explorando el
bot— y a partir de ahí va a ~20 por minuto, que sigue siendo mucho más de lo que
consume una persona leyendo las respuestas.

El objetivo es que **un usuario normal no lo note nunca** y que un bucle no
llegue a molestar. Por eso la capacidad es alta y la reposición rápida: el freno
tiene que aparecer cuando alguien machaca, no cuando alguien prueba.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from utils.logger import get_logger

log = get_logger("utils.cooldown")


def _ajuste(nombre: str, por_defecto: float) -> float:
    try:
        return float(os.getenv(nombre, "") or por_defecto)
    except ValueError:
        return por_defecto


#: Comandos que se pueden encadenar de golpe antes de que aparezca el freno.
#: Es un **entero** porque cuenta comandos: con un flotante, `range(CAPACIDAD)`
#: en cualquier sitio que lo use revienta con un `TypeError` que no dice nada.
CAPACIDAD = int(_ajuste("COOLDOWN_CAPACIDAD", 10))

#: Segundos que tarda en reponerse una ficha. 3 s son ~20 comandos por minuto
#: sostenidos, que sigue siendo muy por encima de lo que hace una persona.
REPOSICION_S = _ajuste("COOLDOWN_REPOSICION_S", 3.0)

#: A partir de cuántos usuarios distintos se limpia la tabla. Es un freno contra
#: una fuga de memoria, no una decisión de producto: el diccionario guarda una
#: entrada por usuario que haya usado el bot desde el arranque.
LIMPIEZA_CADA = 500


@dataclass
class _Cubo:
    fichas: float
    ultimo: float = field(default_factory=time.monotonic)


#: `user_id -> cubo`. En memoria y a propósito: un freno temporal no tiene nada
#: que hacer en disco, y si el bot reinicia lo peor que pasa es que alguien pueda
#: volver a encadenar diez comandos.
_cubos: dict[int, _Cubo] = {}

#: Cuántos se han frenado desde el arranque, para `/health` y el log.
frenados = 0


def permitir(user_id: int) -> float:
    """Gasta una ficha del cubo de ese usuario.

    Devuelve `0.0` si puede pasar, o los **segundos que le faltan** para poder
    volver a intentarlo. Que devuelva el tiempo y no un booleano es lo que
    permite decirle «espera 4 segundos» en vez de un «no» seco, que es la
    diferencia entre entenderlo y pensar que el bot está roto.
    """
    global frenados

    ahora = time.monotonic()
    cubo = _cubos.get(user_id)

    if cubo is None:
        if len(_cubos) >= LIMPIEZA_CADA:
            _limpiar(ahora)
        _cubos[user_id] = _Cubo(fichas=CAPACIDAD - 1, ultimo=ahora)
        return 0.0

    # Reponer lo que corresponda por el tiempo transcurrido, sin pasar del tope.
    transcurrido = ahora - cubo.ultimo
    cubo.fichas = min(CAPACIDAD, cubo.fichas + transcurrido / REPOSICION_S)
    cubo.ultimo = ahora

    if cubo.fichas >= 1:
        cubo.fichas -= 1
        return 0.0

    # Se queda sin fichas: lo que falta para la siguiente.
    espera = (1 - cubo.fichas) * REPOSICION_S
    frenados += 1
    log.info("Freno por usuario: %s tendría que esperar %.1fs", user_id, espera)
    return espera


def _limpiar(ahora: float) -> None:
    """Saca de la tabla a quien ya habría repuesto el cubo entero.

    Sin esto, el diccionario crece con cada usuario que use el bot desde el
    arranque. Con la limpieza, su tamaño es proporcional a quien ha usado el bot
    **en los últimos minutos**, no desde que arrancó.
    """
    lleno = CAPACIDAD * REPOSICION_S
    viejos = [u for u, c in _cubos.items() if ahora - c.ultimo > lleno]
    for u in viejos:
        del _cubos[u]
    if viejos:
        log.debug("Freno: %d usuarios fuera de la tabla", len(viejos))


def reiniciar() -> None:
    """Vacía la tabla. Para las pruebas."""
    global frenados
    _cubos.clear()
    frenados = 0

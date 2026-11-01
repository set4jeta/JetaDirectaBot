# tracking/soloq/cadencia.py
"""Cada cuánto se barre, decidido por el presupuesto que queda, no por una cifra fija.

El problema que resuelve
------------------------
El plan gratuito de Render da **5 GB de tráfico al mes** y, al agotarlos, suspende
el servicio entero (pasó el 29-09-2026 y otra vez el 29-10). El gasto no son los
avisos —desde que las imágenes son URLs, los mensajes son ~1,4 MB al mes— sino
**el sondeo de la API de Riot**: cada pasada pregunta por todas las cuentas.

Hasta ahora eso se gobernaba con un número fijo en una variable de entorno. Y un
número fijo siempre está mal en algún momento del mes:

* si es rápido (240 s), el mes se agota antes de terminar y el bot queda
  suspendido con días por delante;
* si es lento (1 800 s), no se agota nunca pero se avisa con media hora de
  retraso **todos los días**, también los que sobraban.

Lo que hace falta no es un número: es **gastar el presupuesto a lo largo de todo
el mes**. Eso es lo que calcula este módulo. Al empezar el ciclo va rápido porque
hay margen; según se gasta, se estira; y el último día llega con el presupuesto
justo agotándose, no antes ni después.

Cómo
----
    coste_de_una_pasada  = cuentas_sondeadas × bytes_por_cuenta
    margen_por_hora      = (presupuesto − gastado) ÷ horas_que_quedan
    pasadas_por_hora     = margen_por_hora ÷ coste_de_una_pasada
    intervalo            = 3600 ÷ pasadas_por_hora

`bytes_por_cuenta` **no es una constante de fe**: se mide. Cada pasada anota
cuántos bytes gastó de verdad (`egress.volcar_sondeo`) y cuántas cuentas miró, y
de ahí sale una media móvil. Si mañana el censo crece o Riot cambia el tamaño de
la respuesta, la cadencia se entera sola.

Por qué esto es seguro y un número fijo no
------------------------------------------
Porque **se autocorrige**. Si una semana el bot gasta más de lo previsto (más
cuentas, más ligas seguidas), el margen por hora baja y el intervalo sube en la
siguiente vuelta. Un número fijo no se enteraba hasta que el proveedor cortaba.

Los topes existen para que la corrección no se vuelva absurda: por debajo de
`MINIMO` el producto se degrada (Riot no da más de sí y el barrido no cabe en su
propio intervalo) y por encima de `MAXIMO` un aviso llega tan tarde que ya no
sirve de nada. Si el presupuesto se agota antes de fin de mes, se va a
`AGOTADO`: se sigue barriendo muy despacio —el bot no se apaga— hasta que el mes
cambie y el contador vuelva a cero.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from utils import egress
from utils.logger import get_logger

log = get_logger("tracking.cadencia")

#: El suelo. Por debajo de dos minutos el barrido no cabe en su propio intervalo
#: (una pasada de 900 cuentas tarda decenas de segundos) y además Riot no da más
#: de sí para el número de peticiones que hace falta.
MINIMO = 120.0

#: El techo cuando hay presupuesto. Media hora es el límite de lo que se puede
#: llamar «aviso en vivo»: a partir de ahí el producto ya no es lo que se vende.
MAXIMO = 1800.0

#: Cuando el presupuesto del mes **ya no da para más**, se sigue barriendo a este
#: ritmo. No se apaga: apagarse es peor que ir despacio, porque el bot dejaría de
#: cumplir lo único que promete. El mes siguiente vuelve solo a la cadencia buena.
AGOTADO = 3600.0

#: Bytes por cuenta cuando aún no hay ninguna medición. Sale de los números
#: reales de octubre: ~1,07 MB por pasada con ~919 cuentas.
BYTES_POR_CUENTA_DEFECTO = 1160.0

#: Cuánto pesa una medición nueva frente a la media que ya había. 0,25 = la
#: media se mueve despacio, que es lo que se quiere: un pico puntual no debe
#: reescribir la cadencia del mes.
PESO_MEDICION = 0.25

#: Mínimo de cuentas para fiarse de una medición. Una pasada con 5 cuentas no
#: dice nada del coste real y sí ensuciaría la media.
CUENTAS_MINIMAS = 20

#: La media móvil y cuántas mediciones la han alimentado. A nivel de módulo
#: porque la cadencia es una sola para todo el proceso.
_bytes_por_cuenta: float | None = None
_mediciones = 0

#: Último intervalo decidido, para que `/health` y `SweepStats` lo puedan leer
#: sin recalcular (y sin depender de que la pasada acabe de terminar).
_ultimo: float = 0.0
_motivo: str = "sin calcular"


def _float_env(nombre: str, defecto: float) -> float:
    try:
        valor = float(os.getenv(nombre, "") or defecto)
    except (TypeError, ValueError):
        return defecto
    return valor if valor > 0 else defecto


def automatica() -> bool:
    """¿Se decide sola la cadencia?

    `CADENCIA_AUTOMATICA=0` vuelve al comportamiento viejo: el intervalo es
    `CHECK_GAMES_INTERVAL` y punto. Está por si algún día hay que clavar una
    cifra a mano para medir algo, no porque sea una opción razonable.
    """
    return (os.getenv("CADENCIA_AUTOMATICA", "1") or "1").strip().lower() not in (
        "0", "no", "false", "off",
    )


def bytes_por_cuenta() -> float:
    """Coste medido de sondear una cuenta, en bytes."""
    if _bytes_por_cuenta is None:
        return _float_env("SONDEO_BYTES_POR_CUENTA", BYTES_POR_CUENTA_DEFECTO)
    return _bytes_por_cuenta


def anotar_pasada(cuentas: int, bytes_gastados: int) -> None:
    """Aprende de una pasada real. La llama el barrido al terminar.

    Se ignora la pasada que no miró cuentas suficientes: con pocas cuentas el
    ruido (una respuesta más grande, un reintento) pesa más que la señal.
    """
    global _bytes_por_cuenta, _mediciones
    if cuentas < CUENTAS_MINIMAS or bytes_gastados <= 0:
        return
    muestra = bytes_gastados / cuentas
    if _bytes_por_cuenta is None:
        _bytes_por_cuenta = muestra
    else:
        _bytes_por_cuenta = (
            _bytes_por_cuenta * (1 - PESO_MEDICION) + muestra * PESO_MEDICION
        )
    _mediciones += 1


def _horas_restantes(ahora: datetime | None = None) -> float:
    """Horas hasta el cambio de mes en UTC, que es cuando Render reinicia el cubo.

    Se mide en UTC y no en hora local porque el contador del proveedor va en UTC;
    usar la local haría que el último día del mes se calculara con el reloj
    equivocado, que es justo el día en que la cifra importa.
    """
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    if ahora.month == 12:
        siguiente = datetime(ahora.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        siguiente = datetime(ahora.year, ahora.month + 1, 1, tzinfo=timezone.utc)
    return max(0.0, (siguiente - ahora).total_seconds() / 3600)


def intervalo(cuentas: int, duracion: float = 0.0) -> tuple[float, str]:
    """Los segundos que deben pasar hasta la próxima pasada, y por qué.

    Devuelve `(segundos, motivo)`. El motivo es para el log y `/health`: una
    cadencia que no se puede explicar es una cadencia que nadie se atreve a
    tocar.
    """
    global _ultimo, _motivo

    if not automatica():
        fijo = _float_env("CHECK_GAMES_INTERVAL", 240.0)
        _ultimo, _motivo = fijo, "fija (CADENCIA_AUTOMATICA=0)"
        return _ultimo, _motivo

    minimo = _float_env("CHECK_GAMES_INTERVAL_MIN", MINIMO)
    maximo = _float_env("CHECK_GAMES_INTERVAL_MAX", MAXIMO)

    if cuentas <= 0:
        # Sin cuentas no hay nada que sondear: da igual el intervalo, pero se
        # devuelve el mínimo para que el barrido vuelva pronto a comprobarlo
        # (un censo que se acaba de restaurar debe notarse en seguida).
        _ultimo, _motivo = minimo, "sin cuentas que sondear"
        return _ultimo, _motivo

    gastado = egress.total_bytes()
    presupuesto = egress.presupuesto_bytes()
    restante = presupuesto - gastado
    horas = _horas_restantes()

    if restante <= 0 or horas <= 0:
        _ultimo = _float_env("CHECK_GAMES_INTERVAL_AGOTADO", AGOTADO)
        _motivo = (
            f"presupuesto agotado ({gastado / 1048576:.0f} de "
            f"{presupuesto / 1048576:.0f} MB)"
        )
        return _ultimo, _motivo

    coste = max(1.0, cuentas * bytes_por_cuenta())
    margen_por_hora = restante / horas
    pasadas_por_hora = margen_por_hora / coste
    # Sin margen para una sola pasada por hora, el cálculo pediría un intervalo
    # enorme; el tope de arriba ya lo cubre, así que se acota aquí y se explica.
    if pasadas_por_hora <= 0:
        _ultimo = maximo
        _motivo = "el presupuesto no da ni para una pasada por hora"
        return _ultimo, _motivo

    calculado = 3600.0 / pasadas_por_hora
    motivo = (
        f"{restante / 1048576:.0f} MB para {horas:.0f} h · "
        f"{cuentas} cuentas × {bytes_por_cuenta():.0f} B = "
        f"{coste / 1048576:.2f} MB/pasada"
    )

    if calculado > maximo:
        _ultimo, _motivo = maximo, motivo + " · tope"
    elif calculado < minimo:
        _ultimo, _motivo = minimo, motivo + " · suelo"
    else:
        _ultimo, _motivo = calculado, motivo

    # Una pasada no puede empezar antes de que acabe la anterior: si el cálculo
    # pide 2 min y la pasada tarda 40 s, aún vale; si tardara más que el
    # intervalo, se perderían vueltas sin parar.
    if duracion > 0 and _ultimo < duracion * 1.15:
        _ultimo = duracion * 1.15
        _motivo += f" · limitado por la duración ({duracion:.0f}s)"

    return _ultimo, _motivo


def intervalo_actual() -> float:
    """El último intervalo decidido, sin recalcular.

    Lo lee `SweepStats.presupuesto` para poder decir «tardó 41 s de 900» sin
    volver a mirar el contador a mitad de la pasada.
    """
    return _ultimo if _ultimo > 0 else _float_env("CHECK_GAMES_INTERVAL", 240.0)


def motivo() -> str:
    return _motivo


def estado() -> dict[str, Any]:
    """Para `/health` y el log de arranque."""
    return {
        "automatica": automatica(),
        "intervalo": intervalo_actual(),
        "motivo": _motivo,
        "bytes_por_cuenta": bytes_por_cuenta(),
        "mediciones": _mediciones,
    }


def reiniciar() -> None:
    """Olvida la media aprendida. Para las pruebas."""
    global _bytes_por_cuenta, _mediciones, _ultimo, _motivo
    _bytes_por_cuenta = None
    _mediciones = 0
    _ultimo = 0.0
    _motivo = "sin calcular"

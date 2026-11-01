"""La cadencia del barrido se reparte el presupuesto del mes, no es un número fijo.

Qué vigila esta prueba
----------------------
El 01-11-2026 el bot llevaba dos días suspendido por cuota y la propuesta era
subir el intervalo de 240 s a 1 800 s. El problema de esa solución es que un
número fijo **siempre está mal en algún momento del mes**: 240 s agotaba los 5 GB
antes de terminar y 1 800 s hacía esperar media hora al aviso también los días
que sobraban.

`tracking/soloq/cadencia.py` lo calcula con lo que queda y lo que falta. Esto
comprueba que de verdad hace lo que dice:

1. Al principio del mes va rápido; cuanto más se ha gastado, más se estira.
2. Con el presupuesto agotado no se apaga: va a `AGOTADO`.
3. Los topes se respetan (ni 3 s ni tres horas).
4. Aprende el coste real de una cuenta de las pasadas medidas.
5. No se salta a sí misma: nunca programa una vuelta antes de que acabe la
   anterior.
6. `CADENCIA_AUTOMATICA=0` vuelve al número fijo, que es la salida de emergencia.

Uso:
    python scripts/test_cadencia.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# **Antes de importar `egress`.** Su ruta se evalúa al importar, y si no se
# desvía esta prueba escribe en el contador de verdad — el fichero que existe
# justo para no volver a quedarse sin ancho de banda sin enterarse.
os.environ.setdefault(
    "EGRESS_RUTA", os.path.join(tempfile.gettempdir(), "lolpro_cadencia_egress.json")
)

from tracking.soloq import cadencia  # noqa: E402
from utils import egress  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def _gastado(mb: float) -> None:
    """Deja el contador del mes con `mb` consumidos, todo de sondeo."""
    egress.reiniciar()
    egress.registrar_sondeo(int(mb * 1024 * 1024))
    egress.volcar_sondeo()


def _preparar(**entorno: str) -> None:
    """Reinicia la cadencia y el contador, con el entorno que pida la prueba."""
    for clave in (
        "CADENCIA_AUTOMATICA", "CHECK_GAMES_INTERVAL",
        "CHECK_GAMES_INTERVAL_MIN", "CHECK_GAMES_INTERVAL_MAX",
        "CHECK_GAMES_INTERVAL_AGOTADO", "SONDEO_BYTES_POR_CUENTA",
        "EGRESS_PRESUPUESTO_MB",
    ):
        os.environ.pop(clave, None)
    os.environ.update(entorno)
    cadencia.reiniciar()
    egress.reiniciar()


def prueba_el_reparto() -> None:
    print("\n=== el presupuesto se reparte por el mes ===")
    _preparar(EGRESS_PRESUPUESTO_MB="4800")

    _gastado(0)
    pronto, motivo = cadencia.intervalo(900)
    ok(pronto < cadencia.MAXIMO,
       "a principio de mes no se va al tope", f"{pronto:.0f}s")
    ok(pronto > cadencia.MINIMO,
       "ni se queda en el suelo con 900 cuentas", f"{pronto:.0f}s")
    ok("MB para" in motivo, "el motivo explica el cálculo", motivo[:60])

    # La misma cantidad de cuentas, con medio presupuesto gastado: tiene que ir
    # más despacio. Es la propiedad central: la cadencia se adapta a lo gastado.
    _gastado(2400)
    mitad, _ = cadencia.intervalo(900)
    ok(mitad > pronto,
       "con medio presupuesto gastado va más despacio",
       f"{pronto:.0f}s -> {mitad:.0f}s")

    # Y al final del mes con casi todo gastado, aún más.
    _gastado(4400)
    final, _ = cadencia.intervalo(900)
    ok(final > mitad, "y al final del mes todavía más",
       f"{mitad:.0f}s -> {final:.0f}s")
    ok(final <= cadencia.MAXIMO, "sin pasarse del tope", f"{final:.0f}s")

    # Más cuentas cuestan más: con el mismo presupuesto, hay que ir más lento.
    _gastado(0)
    pocas, _ = cadencia.intervalo(200)
    muchas, _ = cadencia.intervalo(2000)
    ok(muchas > pocas, "el doble de cuentas obliga a ir más despacio",
       f"200 -> {pocas:.0f}s, 2000 -> {muchas:.0f}s")


def prueba_agotado() -> None:
    print("\n=== el presupuesto agotado no apaga el bot ===")
    _preparar(EGRESS_PRESUPUESTO_MB="4800")
    _gastado(4900)

    segundos, motivo = cadencia.intervalo(900)
    ok(segundos == cadencia.AGOTADO,
       "con el presupuesto pasado se va al ritmo de supervivencia",
       f"{segundos:.0f}s")
    ok(segundos > cadencia.MAXIMO,
       "que es más lento que el tope normal: no se puede seguir al mismo ritmo")
    ok("agotado" in motivo.lower(), "y el motivo lo dice", motivo)

    # Sigue devolviendo algo barrible: apagarse sería peor que ir despacio.
    ok(segundos > 0, "pero sigue habiendo una vuelta programada")


def prueba_topes() -> None:
    print("\n=== los topes ===")
    _preparar(EGRESS_PRESUPUESTO_MB="4800")

    # Con muy pocas cuentas el cálculo pediría segundos; el suelo lo impide.
    _gastado(0)
    segundos, motivo = cadencia.intervalo(1)
    ok(segundos >= cadencia.MINIMO, "nunca por debajo del suelo",
       f"{segundos:.0f}s")
    ok("suelo" in motivo or segundos == cadencia.MINIMO, "y se explica")

    # Con un presupuesto ridículo el cálculo pediría horas; el techo lo corta.
    _preparar(EGRESS_PRESUPUESTO_MB="1")
    _gastado(0)
    segundos, motivo = cadencia.intervalo(5000)
    ok(segundos <= cadencia.MAXIMO, "nunca por encima del techo",
       f"{segundos:.0f}s")
    ok("tope" in motivo or segundos == cadencia.MAXIMO, "y se explica")

    # Sin cuentas no hay nada que sondear, pero hay que volver pronto: el censo
    # puede restaurarse en cualquier momento y no se quiere esperar media hora.
    _preparar(EGRESS_PRESUPUESTO_MB="4800")
    _gastado(0)
    segundos, motivo = cadencia.intervalo(0)
    ok(segundos == cadencia.MINIMO, "sin cuentas vuelve enseguida", f"{segundos:.0f}s")
    ok("sin cuentas" in motivo, "y lo dice", motivo)


def prueba_aprende() -> None:
    print("\n=== aprende lo que cuesta una cuenta ===")
    _preparar(EGRESS_PRESUPUESTO_MB="4800")
    _gastado(0)

    inicial = cadencia.bytes_por_cuenta()
    ok(inicial == cadencia.BYTES_POR_CUENTA_DEFECTO,
       "sin mediciones usa el valor de octubre", f"{inicial:.0f} B")

    # La primera medición **fija** la media (no hay nada con lo que mezclarla);
    # a partir de la segunda se mueve despacio, que es lo que se quiere: un pico
    # puntual no puede reescribir la cadencia del mes.
    cadencia.anotar_pasada(400, 2 * 1024 * 1024)
    primera = cadencia.bytes_por_cuenta()
    ok(primera > inicial, "la primera pasada fija la media", f"{primera:.0f} B")

    # Una segunda pasada diez veces más cara: la media sube, pero no se iguala.
    cadencia.anotar_pasada(400, 20 * 1024 * 1024)
    segunda = cadencia.bytes_por_cuenta()
    muestra = 20 * 1024 * 1024 / 400
    ok(segunda > primera, "una pasada cara sube la media",
       f"{primera:.0f} B -> {segunda:.0f} B")
    ok(segunda < muestra,
       "pero no la reescribe: es una media móvil, no el último dato",
       f"{segunda:.0f} B de {muestra:.0f} B")

    # Con pocas cuentas no se aprende: el ruido pesa más que la señal.
    antes = cadencia.bytes_por_cuenta()
    cadencia.anotar_pasada(3, 50 * 1024 * 1024)
    ok(cadencia.bytes_por_cuenta() == antes,
       "una pasada con 3 cuentas no enseña nada y se ignora")

    # Y el coste aprendido cambia la decisión: si cada cuenta cuesta más, hay que
    # ir más despacio para el mismo presupuesto.
    _gastado(0)
    cadencia.reiniciar()
    con_defecto, _ = cadencia.intervalo(500)
    cadencia.anotar_pasada(500, 10 * 1024 * 1024)
    con_medido, _ = cadencia.intervalo(500)
    ok(con_medido > con_defecto,
       "un coste real mayor estira el intervalo",
       f"{con_defecto:.0f}s -> {con_medido:.0f}s")


def prueba_duracion() -> None:
    print("\n=== no se salta a sí misma ===")
    _preparar(EGRESS_PRESUPUESTO_MB="4800")
    _gastado(0)

    # Una pasada de 400 s con un cálculo que pediría 120: se respeta la duración.
    segundos, motivo = cadencia.intervalo(10, duracion=400.0)
    ok(segundos >= 400 * 1.15,
       "el intervalo nunca es menor que la pasada que acaba de hacer",
       f"{segundos:.0f}s para una pasada de 400s")
    ok("duración" in motivo, "y el motivo lo dice", motivo)


def prueba_fija() -> None:
    print("\n=== la salida de emergencia ===")
    _preparar(CADENCIA_AUTOMATICA="0", CHECK_GAMES_INTERVAL="900")
    _gastado(0)

    segundos, motivo = cadencia.intervalo(900)
    ok(segundos == 900.0, "con la automática apagada manda la cifra fija",
       f"{segundos:.0f}s")
    ok("fija" in motivo, "y se dice que es fija", motivo)

    _preparar()
    ok(cadencia.automatica(), "por defecto la cadencia se decide sola")


def prueba_horas_restantes() -> None:
    print("\n=== las horas que quedan de mes ===")
    # Se mide en UTC porque el cubo del proveedor va en UTC. Un 15 de enero a las
    # 12:00 quedan 12 h y medio día, no «un mes».
    enero = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    horas = cadencia._horas_restantes(enero)
    ok(abs(horas - (16 * 24 + 12)) < 0.01,
       "del 15-01 12:00 al 01-02 00:00 UTC", f"{horas:.1f} h")

    diciembre = datetime(2026, 12, 31, 18, 0, tzinfo=timezone.utc)
    horas = cadencia._horas_restantes(diciembre)
    ok(abs(horas - 6) < 0.01,
       "en diciembre el mes siguiente es enero del año que viene",
       f"{horas:.1f} h")

    ultimo = datetime(2026, 3, 31, 23, 0, tzinfo=timezone.utc)
    ok(cadencia._horas_restantes(ultimo) <= 1.01,
       "la última hora del mes no da horas negativas",
       f"{cadencia._horas_restantes(ultimo):.2f} h")


def main() -> int:
    print("=" * 74)
    print("La cadencia del barrido se reparte el presupuesto del mes.")
    print("=" * 74)

    prueba_el_reparto()
    prueba_agotado()
    prueba_topes()
    prueba_aprende()
    prueba_duracion()
    prueba_fija()
    prueba_horas_restantes()

    # Se deja el entorno y el contador como estaban: esta prueba escribe en el
    # contador de verdad si no se limpia, y ese fichero existe justo para no
    # perder la cuenta del mes.
    _preparar()
    egress.reiniciar()

    print("\n" + "=" * 74)
    if fallos:
        print(f"fallos: {len(fallos)}")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("fallos: 0")
    print("La cadencia gasta el presupuesto a lo largo del mes, no de golpe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

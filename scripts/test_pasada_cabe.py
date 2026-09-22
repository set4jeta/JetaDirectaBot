"""Comprueba que el bot se da cuenta cuando la pasada no cabe en su intervalo.

Por qué existe
--------------
El tope de ligas por servidor (`MAX_LIGAS_POR_SERVIDOR`) no acota el coste real
de una pasada: el tracker recorre la **unión** de las ligas de todos los
servidores, así que 20 servidores con 4 ligas distintas cada uno cuestan las 20
ligas (~3154 cuentas, ~63 s medidos, contra un intervalo de 30 s).

Lo que pasaba entonces era degradación en silencio: la vuelta siguiente veía
`_running` en True, escribía una línea de log y se saltaba. Nadie contaba esas
vueltas y ninguna superficie del bot lo decía, así que el único síntoma visible
era que los avisos llegaban tarde.

Aquí se prueba lo que se añadió, sin red y sin Discord:

* `SweepStats.cabe` y `.uso` comparan la duración con el intervalo;
* una pasada que se pasa registra avería en `core.health`;
* una que raspa (>= 80 %) avisa pero **no** enciende el rojo, porque todavía
  funciona y un rojo por algo que funciona hace que se ignore el rojo de verdad;
* una pasada solapada cuenta la vuelta perdida y no reinicia el contador.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import health as salud  # noqa: E402
from tracking.soloq import active_game_checker as agc  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    if condicion:
        print(f"  OK    {etiqueta}{f' ({extra})' if extra else ''}")
    else:
        print(f"  FALLA {etiqueta}{f' ({extra})' if extra else ''}")
        fallos.append(etiqueta)


def _limpiar_salud() -> None:
    """Deja el registro de salud como recién arrancado."""
    salud._estados.pop("pasada", None)


def _avisar(stats: agc.SweepStats) -> None:
    """Llama al aviso sin construir un tracker.

    `_avisar_si_no_cabe` no usa `self` para nada: solo mira las estadísticas y
    escribe en el log y en `core.health`. Pasarle `None` evita cargar los
    ficheros de cuentas y abrir el cliente de Riot solo para esto.
    """
    agc.ActiveGameTracker._avisar_si_no_cabe(None, stats)


def prueba_cuentas() -> None:
    print("\n=== cabe / uso ===")
    holgada = agc.SweepStats(presupuesto=30.0, duracion=2.0)
    ok(holgada.cabe, "2 s en un intervalo de 30 cabe")
    ok(abs(holgada.uso - 2 / 30) < 1e-9, "y el uso es la fracción", f"{holgada.uso:.3f}")

    justa = agc.SweepStats(presupuesto=30.0, duracion=30.0)
    ok(justa.cabe, "exactamente el intervalo se considera que cabe")

    pasada = agc.SweepStats(presupuesto=30.0, duracion=41.0)
    ok(not pasada.cabe, "41 s en 30 no cabe")
    ok(pasada.uso > 1, "y el uso pasa de 1", f"{pasada.uso:.2f}")

    suelta = agc.SweepStats(duracion=99.0)
    ok(suelta.cabe, "sin presupuesto no se juzga (script o test suelto)")
    ok(suelta.uso == 0.0, "y el uso es 0, no una división por cero")


def prueba_registra_averia() -> None:
    print("\n=== una pasada que no cabe queda registrada ===")
    _limpiar_salud()
    _avisar(agc.SweepStats(presupuesto=30.0, duracion=41.0))
    estado = salud.estado_de("pasada")
    ok(estado.ok is False, "se marca como fallo")
    ok("41s" in estado.detalle and "30s" in estado.detalle,
       "el detalle dice cuánto tardó y cuánto tenía", estado.detalle)

    # Tres seguidas es lo que `core.health` considera avería de verdad.
    _avisar(agc.SweepStats(presupuesto=30.0, duracion=41.0))
    _avisar(agc.SweepStats(presupuesto=30.0, duracion=41.0))
    ok("pasada" in [c for c in salud._estados if salud._estados[c].fallos_seguidos >= 3],
       "tres seguidas cuentan como avería")
    ok(salud.nombre_fuente("pasada") in salud.hay_averias(),
       "y sale en /health con nombre legible", salud.nombre_fuente("pasada"))


def prueba_umbral_no_enciende_rojo() -> None:
    print("\n=== una pasada que raspa avisa pero no es avería ===")
    _limpiar_salud()
    # 24 s sobre 30 es el caso medido de 6 ligas: el 80 % exacto.
    _avisar(agc.SweepStats(presupuesto=30.0, duracion=24.0))
    estado = salud.estado_de("pasada")
    ok(estado.ok is True, "sigue contando como que funciona")
    ok("%" in estado.detalle, "pero el detalle dice a qué porcentaje va", estado.detalle)
    ok(not salud.hay_averias(), "y /health no la enseña como avería")

    _limpiar_salud()
    _avisar(agc.SweepStats(presupuesto=30.0, duracion=2.0))
    ok(salud.estado_de("pasada").ok is True, "una pasada holgada también registra ok")
    ok("%" not in salud.estado_de("pasada").detalle,
       "y su detalle es la duración, sin porcentaje",
       salud.estado_de("pasada").detalle)


def prueba_sin_presupuesto_no_registra() -> None:
    print("\n=== sin intervalo conocido no se inventa un veredicto ===")
    _limpiar_salud()
    _avisar(agc.SweepStats(duracion=500.0))
    ok(salud.estado_de("pasada").ok is None,
       "una pasada sin presupuesto no toca el registro de salud")


def prueba_vueltas_perdidas() -> None:
    print("\n=== vueltas perdidas por solapamiento ===")
    _limpiar_salud()
    agc._vueltas_perdidas = 0

    class TrackerFalso:
        """Solo lo que `run()` toca antes de rendirse por solapamiento."""

        _running = True

    stats = agc.ActiveGameTracker.run(TrackerFalso())
    # `run` es async: se ejecuta el corutina hasta el return sin event loop
    # completo porque el camino de solapamiento no espera nada.
    try:
        stats.send(None)
    except StopIteration as fin:
        resultado = fin.value
    else:  # pragma: no cover - si llega aquí, el camino ha dejado de ser directo
        resultado = None
        ok(False, "el camino de solapamiento no debería esperar nada")

    ok(resultado is not None and resultado.solapada,
       "la vuelta se marca como solapada")
    ok(resultado is not None and resultado.vueltas_perdidas == 1,
       "y se cuenta", str(getattr(resultado, "vueltas_perdidas", "?")))
    ok(resultado is not None and resultado.revisadas == 0,
       "no revisa ninguna cuenta cuando se salta")
    ok(salud.estado_de("pasada").ok is False,
       "una vuelta perdida es un fallo de la pasada")

    # La segunda no reinicia el contador: lo que importa es que suba.
    stats2 = agc.ActiveGameTracker.run(TrackerFalso())
    try:
        stats2.send(None)
    except StopIteration as fin:
        segundo = fin.value
    ok(segundo.vueltas_perdidas == 2, "el contador acumula entre vueltas",
       str(segundo.vueltas_perdidas))
    ok(agc._vueltas_perdidas == 2, "y el módulo lo recuerda para /health")


def prueba_clave_i18n() -> None:
    print("\n=== la fuente nueva se puede pintar en /health ===")
    from utils.i18n import t

    ok("pasada" in salud.FUENTES, "está en el catálogo de fuentes")
    for idioma in ("es", "en"):
        texto = t(salud.FUENTES["pasada"], idioma)
        ok(texto != salud.FUENTES["pasada"], f"[{idioma}] tiene traducción", texto)

    linea = salud.linea("pasada", salud.Estado(ok=False, detalle="41s sobre 30s",
                                               fallos_seguidos=3, ultimo_ok=None))
    ok("41s" in linea, "la línea de /health lleva el detalle", linea)


def main() -> None:
    prueba_cuentas()
    prueba_registra_averia()
    prueba_umbral_no_enciende_rojo()
    prueba_sin_presupuesto_no_registra()
    prueba_vueltas_perdidas()
    prueba_clave_i18n()

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()

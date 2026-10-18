"""Worlds se sigue solo mientras dura el mundial, y solo en el servidor donde se juega.

Por qué existe
--------------
El 18-10-2026 el dueño pidió seguir a los jugadores del mundial. Son 101
jugadores de 19 equipos, pero **no todos juegan en el mismo servidor**: cada uno
tiene cuentas en KR, EUW1, NA1 y BR1 a la vez (medido: 348 cuentas entre los
101). Y el mundial es en Estados Unidos, así que lo que hay que mirar son las de
**NA**.

Seguirlas todas multiplicaría por cuatro el sondeo, y el sondeo es exactamente
lo que agota los 5 GB de salida del plan gratuito de Render (ver `DESPLIEGUE.md`
§8). Por eso Worlds filtra a `na1`: son 86 cuentas de 64 jugadores.

Lo que vigila esta prueba
-------------------------
1. Que la liga existe, se llama como debe y **se enciende sola** en sus fechas.
2. Que **fuera de temporada no se sigue**: ni gasta peticiones ni aparece.
3. Que el filtro de plataforma se aplica **en los dos caminos** que escriben el
   fichero. El segundo —`refrescar_ligas`, el que usa el bot de verdad— es el
   que se olvidó la primera vez, y el síntoma era mudo: guardaba las 348 cuentas
   y el log decía que todo había ido bien.
4. Que el leaderboard de Worlds (224 entradas) no se confunde con el comodín de
   dpm.lol (1621), que es el fallo que habría dejado la liga vacía **sin error**.
5. Que la web sigue diciendo 20 ligas: un evento de un mes no es una liga.

Uso:
    python scripts/test_worlds.py
"""

from __future__ import annotations

import os
import sys
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracking.soloq import accounts_from_teams as aft  # noqa: E402
from tracking.soloq.leagues import LIGAS, LIGAS_WEB, Liga  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def _jugador(league: str, plataformas: list[str]):
    """Un jugador de mentira con las cuentas que se le digan."""
    return SimpleNamespace(
        league=league,
        accounts=[SimpleNamespace(platform=p) for p in plataformas],
    )


def prueba_la_liga() -> None:
    print("\n=== la liga ===")
    worlds = LIGAS.get("worlds")
    ok(worlds is not None, "existe la liga 'worlds'")
    if worlds is None:
        return
    ok(worlds.nombre == "Worlds", "se llama Worlds")
    ok(worlds.region_en == "International", "la región se traduce para la web")
    ok(worlds.solo_plataformas == ("na1",), "solo se guardan cuentas de NA",
       ", ".join(worlds.solo_plataformas))
    ok(worlds.autoactiva, "se activa sola, sin que nadie se suscriba")
    ok(worlds.rastreable, "se pueden detectar partidas en vivo")


def prueba_temporada() -> None:
    print("\n=== las fechas ===")
    worlds = LIGAS["worlds"]
    hoy = date.today()
    dentro = date(2026, 10, 15) <= hoy <= date(2026, 11, 14)
    ok(worlds.en_temporada == dentro,
       "en temporada solo entre el 15-10 y el 14-11-2026",
       f"hoy {hoy}")

    # Una liga con ventana pasada no está en temporada; sin ventana, siempre.
    pasado = Liga("prueba", "Prueba", "Internacional", "",
                  temporada=(date(2020, 1, 1), date(2020, 2, 1)))
    ok(not pasado.en_temporada, "una ventana pasada deja la liga apagada")
    sin_fechas = Liga("prueba2", "Prueba", "Internacional", "")
    ok(sin_fechas.en_temporada, "sin fechas, la liga está siempre encendida")


def prueba_activacion() -> None:
    print("\n=== se activa sola ===")
    from tracking.soloq.leagues import ligas_en_uso

    en_uso = ligas_en_uso()
    worlds = LIGAS["worlds"]
    if worlds.en_temporada:
        ok("worlds" in en_uso, "en temporada, el bot la sigue sin suscripción")
    else:
        ok("worlds" not in en_uso, "fuera de temporada, no se sigue")


def prueba_filtro() -> None:
    print("\n=== el filtro de plataforma ===")
    jugador = _jugador("worlds", ["NA1", "KR", "EUW1", "BR1"])
    quitadas = aft._filtrar_plataformas(jugador)
    ok(quitadas == 3, "de 4 cuentas se quedan las de NA", f"quitadas {quitadas}")
    ok([a.platform for a in jugador.accounts] == ["NA1"],
       "y la que queda es la de NA1")

    # Un jugador sin cuenta de NA: se queda sin cuentas y no se guarda.
    sin_na = _jugador("worlds", ["EUW1", "KR"])
    aft._filtrar_plataformas(sin_na)
    ok(sin_na.accounts == [], "sin cuenta de NA se queda sin cuentas (no se sigue)")

    # Una liga normal no filtra nada, y ese es el caso de las otras 20.
    normal = _jugador("lec", ["EUW1", "KR", "NA1"])
    ok(aft._filtrar_plataformas(normal) == 0, "una liga normal no descarta ninguna")
    ok(len(normal.accounts) == 3, "y conserva las tres")

    # El filtro tiene que estar en los DOS caminos. Se comprueba leyendo el
    # código: si alguien lo quita de `refrescar_ligas`, esta prueba lo dice.
    import inspect

    fuente = inspect.getsource(aft.refrescar_ligas)
    ok("_filtrar_plataformas" in fuente,
       "`refrescar_ligas` aplica el filtro (es el camino que usa el bot)")
    fuente_main = inspect.getsource(aft.main)
    ok("_filtrar_plataformas" in fuente_main, "y `main` también")


def prueba_umbral() -> None:
    print("\n=== el comodín de dpm.lol ===")
    from apis.dpm_api import _UMBRAL_COMODIN, _UMBRAL_COMODIN_POR_LIGA

    # Medido el 18-10-2026: worlds 224 entradas, el comodín 1621.
    umbral = _UMBRAL_COMODIN_POR_LIGA.get("worlds", _UMBRAL_COMODIN)
    ok(umbral > 224, "el umbral de Worlds deja pasar sus 224 entradas",
       f"umbral {umbral}")
    ok(umbral < 1621, "y sigue rechazando el comodín de 1621")


def prueba_web_y_comandos() -> None:
    print("\n=== la web y los comandos ===")
    ok("worlds" not in LIGAS_WEB, "Worlds no entra en la web")
    ok(len(LIGAS_WEB) == 20, "la web sigue con sus 20 ligas",
       f"{len(LIGAS_WEB)}")

    from apis.dpm_api import LIGAS_CHOICES

    ok("worlds" in LIGAS_CHOICES.values(),
       "/subscribe y /ranking pueden pedir worlds")

    from tracking.soloq.channel_targets import acepta_soloq

    ok(acepta_soloq(["*"], liga="worlds"),
       "un canal con «todas las ligas» recibe Worlds")
    ok(not acepta_soloq(["lec"], liga="worlds"),
       "uno suscrito solo a la LEC no (hay que pedir worlds o seguir al jugador)")
    ok(acepta_soloq(["Faker"], liga="worlds", jugador="Faker"),
       "pero seguir a un jugador sí lo trae")


def main() -> int:
    print("=" * 74)
    print("WORLDS: SOLO EN TEMPORADA, SOLO EN NA")
    print("=" * 74)

    prueba_la_liga()
    prueba_temporada()
    prueba_activacion()
    prueba_filtro()
    prueba_umbral()
    prueba_web_y_comandos()

    print("\n" + "=" * 74)
    if fallos:
        print(f"fallos: {len(fallos)}")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("fallos: 0")
    print("Worlds se enciende en sus fechas y solo sondea cuentas de NA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

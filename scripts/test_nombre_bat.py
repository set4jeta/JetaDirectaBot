"""El nombre del `.bat` de espectar: jugador, equipo, campeón y fecha.

Por qué existe
--------------
Hasta el 05-11-2026 el adjunto se llamaba siempre `spectate_lol.bat`. En la lista
de mensajes de Discord eso es un ejecutable sin dueño, y el dueño lo dijo así:
*«que se vea más pro, menos como si fuera un virus»*. En una carpeta de Descargas
con diez ficheros, además, no había forma de saber cuál era de qué partida.

Lo que se defiende aquí no es el formato, son las dos cosas que sí pueden doler:

1. **Que el nombre sea válido en Windows.** Se escribe en el disco de otra
   persona: una `/`, un `:` o un `"` y el fichero no se puede crear, o se crea en
   otro sitio. Un nick puede traer cualquier cosa.
2. **Que nunca quede vacío.** `File(filename=".bat")` es un error de Discord, y
   una partida sin jugador reconocido no puede dejar el aviso sin adjunto.

Uso:
    python scripts/test_nombre_bat.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from ui.active_match_embed import TOPE_NOMBRE_BAT, nombre_del_bat  # noqa: E402

fallos: list[str] = []

#: Un día fijo: el nombre lleva la fecha de la partida y con `now()` la prueba
#: cambiaría de resultado según el día en que se ejecute.
DIA = datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc)

#: Lo que Windows no admite en un nombre de fichero.
PROHIBIDOS = set('\\/:*?"<>|')


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def prueba_forma() -> None:
    print("\n=== las cuatro cosas que pidió el dueño ===")

    nombre = nombre_del_bat("Bin", "BLG", "Ahri", DIA)
    ok(nombre == "Bin (BLG) - Ahri - 2026-11-05.bat",
       "jugador, equipo, campeón y fecha", nombre)

    ok(nombre_del_bat("Bin", "", "Ahri", DIA) == "Bin - Ahri - 2026-11-05.bat",
       "sin equipo no quedan paréntesis vacíos")
    ok(nombre_del_bat("", "BLG", "Ahri", DIA) == "Ahri - 2026-11-05.bat",
       "sin jugador sigue valiendo")
    ok(nombre_del_bat("Bin", "BLG", "", DIA) == "Bin (BLG) - 2026-11-05.bat",
       "sin campeón sigue valiendo")
    ok(nombre_del_bat("", "", "", DIA) == "2026-11-05.bat",
       "sin nada, al menos la fecha")

    # Una partida con cinco pros del roster: se resume, no se enumeran.
    ok(nombre_del_bat("Bin", "BLG", "Ahri", DIA, otros=2)
       == "Bin +2 (BLG) - Ahri - 2026-11-05.bat",
       "los demás jugadores de la partida van como «+N»")
    ok(nombre_del_bat("Bin", "BLG", "Ahri", DIA, otros=0).count("+") == 0,
       "y con uno solo no aparece el «+»")


def prueba_valido_en_windows() -> None:
    print("\n=== un nombre que Windows pueda crear ===")

    casos = (
        ("Kai'Sa", "el apóstrofo de Kai'Sa se queda"),
        ("Cho'Gath", "el de Cho'Gath también"),
        ("Dr. Mundo", "el punto de Dr. Mundo no rompe nada"),
        ("Nunu & Willump", "el «&» se queda"),
    )
    for campeon, etiqueta in casos:
        nombre = nombre_del_bat("Bin", "BLG", campeon, DIA)
        ok(campeon in nombre, etiqueta, nombre)

    # Y lo que sí rompe: un nick con separadores de ruta no puede sacar el
    # fichero de su carpeta.
    sucio = nombre_del_bat('a/b\\c:d*e?f"g<h>i|j', "BLG", "Ahri", DIA)
    ok(not (PROHIBIDOS & set(sucio)),
       "ningún carácter prohibido sobrevive", sucio)
    ok(sucio.startswith("abcdefghij"), "y las letras sí", sucio)

    ok(not nombre_del_bat("Bin", "BLG", "Ahri.", DIA).endswith("..bat"),
       "no acaba en punto (Windows no lo admite)")
    ok(nombre_del_bat("   ", "  ", "   ", DIA).endswith(".bat"),
       "un nombre de solo espacios no deja un fichero sin nombre")
    ok(nombre_del_bat("", "", "", None).endswith(".bat"),
       "sin fecha tampoco revienta (usa la de hoy)")


def prueba_tope() -> None:
    print("\n=== un nombre largo no se desmadra ===")

    largo = nombre_del_bat("J" * 300, "B" * 100, "C" * 100, DIA)
    ok(len(largo) <= TOPE_NOMBRE_BAT + len(".bat"),
       "se corta al tope", str(len(largo)))
    ok(largo.endswith(".bat"), "y sigue siendo un .bat")


def prueba_lo_usa_el_aviso() -> None:
    print("\n=== el aviso usa este nombre, no el de antes ===")

    fuente = open(os.path.join(RAIZ, "ui", "active_match_embed.py"),
                  encoding="utf-8").read()
    ok('filename="spectate_lol.bat"' not in fuente,
       "ya no se llama siempre spectate_lol.bat")
    ok("nombre_del_bat(" in fuente, "el adjunto pasa por nombre_del_bat")
    ok('getattr(main_player, "champion_name"' in fuente,
       "el campeón sale de la partida, no de una lista fija")


def main() -> int:
    print("=" * 66)
    print("EL NOMBRE DEL .BAT DE ESPECTAR")
    print("=" * 66)

    prueba_forma()
    prueba_valido_en_windows()
    prueba_tope()
    prueba_lo_usa_el_aviso()

    print(f"\nfallos : {len(fallos)}")
    return 0 if not fallos else 1


if __name__ == "__main__":
    sys.exit(main())

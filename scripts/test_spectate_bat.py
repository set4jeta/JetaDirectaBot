"""Que el `.bat` de espectar abra la partida de verdad, y sin pedir permisos.

Por qué esta prueba existe
--------------------------
El `.bat` es la única forma que tiene el usuario de ver la partida, y **falla en
silencio**: si la ruta del cliente está mal, se abre una consola, no encuentra el
ejecutable y se cierra antes de que dé tiempo a leer nada. Así estuvo sin
funcionar en el PC del dueño, porque la ruta estaba fijada a `C:\\Riot Games\\...`
y su cliente está en `D:`.

Y paraba Vanguard, que obligaba a ejecutarlo **como administrador** para nada: el
30-09-2026 se abrieron partidas toda la noche con `vgtray.exe` corriendo y
funcionaron. Un `.bat` que pide administrador para algo innecesario es un `.bat`
que la mitad de la gente no llega a ejecutar.

Lo que se comprueba aquí es lo que se puede comprobar sin abrir el juego: que el
fichero lleve los datos correctos de la partida, que **no** toque Vanguard, y que
la ruta del cliente se detecte en vez de estar escrita a mano.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from utils.spectate_bat import generar_bat_spectate, ruta_del_cliente  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def prueba_datos_de_la_partida() -> None:
    print("\n=== el .bat lleva los datos de esta partida ===")

    ruta = generar_bat_spectate(
        server="spectator.na1.lol.pvp.net:8080",
        key="u1j8NjZWRpow2grAca5PbrYGiFEpIkn7",
        match_id=5651554245,
        region="NA1",
    )
    texto = Path(ruta).read_text(encoding="utf-8")

    ok("spectator.na1.lol.pvp.net:8080" in texto, "el servidor de espectadores")
    ok("u1j8NjZWRpow2grAca5PbrYGiFEpIkn7" in texto,
       "la clave de la partida, que cambia cada vez")
    ok("5651554245" in texto, "el identificador de la partida")
    ok("NA1" in texto, "y la región")
    ok("spectator %SERVER% %KEY% %MATCH_ID% %REGION%" in texto,
       "el comando de espectador se arma con esas cuatro cosas")


def prueba_sin_vanguard() -> None:
    print("\n=== no toca Vanguard, así que no pide administrador ===")

    ruta = generar_bat_spectate("spectator.na1.lol.pvp.net:8080", "clave==",
                               12345, "NA1")
    texto = Path(ruta).read_text(encoding="utf-8")

    for prohibido in ("net stop", "net start", "vgtray", "vgc", "vgk"):
        ok(prohibido not in texto,
           f"no aparece «{prohibido}»",
           "parar Vanguard es lo único que obligaba a ejecutar como administrador")

    # Y no puede colarse por otra vía: `sc` o `taskkill` tampoco.
    ok("taskkill" not in texto, "ni mata procesos")
    ok("sc " not in texto, "ni habla con servicios")


def prueba_ruta_detectada() -> None:
    print("\n=== la ruta del cliente se detecta, no se escribe a mano ===")

    detectada = ruta_del_cliente()
    ok(detectada is not None,
       "se encuentra la instalación del cliente en este PC",
       str(detectada))

    if detectada:
        ok(Path(detectada, "Game", "League of Legends.exe").is_file(),
           "y apunta a un ejecutable que existe de verdad")

    ruta = generar_bat_spectate("spectator.na1.lol.pvp.net:8080", "clave==",
                               12345, "NA1")
    texto = Path(ruta).read_text(encoding="utf-8")

    if detectada:
        ok(f'set "LOL_PATH={detectada}"' in texto,
           "el .bat lleva la ruta detectada", detectada)
        # La ruta vieja estaba fijada a C:. Si el cliente no está ahí, que no
        # aparezca: es el fallo que dejaba el .bat sin hacer nada.
        if not Path("C:\\Riot Games\\League of Legends\\Game\\League of Legends.exe").is_file():
            ok("C:\\Riot Games\\League of Legends" not in texto,
               "y no lleva la ruta por defecto escrita a mano")
    else:
        ok("LOL_PATH=" in texto and "pause" in texto,
           "sin ruta detectada, el .bat avisa y espera en vez de cerrarse solo")


def prueba_variable_de_entorno() -> None:
    print("\n=== se puede forzar la ruta sin tocar código ===")

    real = os.environ.get("LOL_PATH")
    try:
        # Una carpeta cualquiera que no tiene el ejecutable: no debe colarse.
        os.environ["LOL_PATH"] = str(RAIZ)
        ok(ruta_del_cliente() != str(RAIZ),
           "una ruta forzada que no tiene el cliente se ignora")

        detectada = ruta_del_cliente()
        if detectada:
            os.environ["LOL_PATH"] = detectada
            ok(ruta_del_cliente() == detectada,
               "y una que sí lo tiene se respeta", detectada)
    finally:
        if real is None:
            os.environ.pop("LOL_PATH", None)
        else:
            os.environ["LOL_PATH"] = real


def main() -> None:
    print("=" * 66)
    print("EL .BAT DE ESPECTAR")
    print("=" * 66)

    prueba_datos_de_la_partida()
    prueba_sin_vanguard()
    prueba_ruta_detectada()
    prueba_variable_de_entorno()

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()

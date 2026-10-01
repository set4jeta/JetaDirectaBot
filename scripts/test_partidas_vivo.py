"""Que lo que se publica para el grabador no se separe en dos versiones.

Por qué esta prueba existe
--------------------------
Lo que el bot publica tiene **dos transportes**: el endpoint `GET /live-games`,
para cuando está desplegado y el grabador corre en otro sitio, y el fichero
`partidas_vivo.json`, para cuando los dos están en el mismo PC.

El peligro no es que uno de los dos falle —eso se ve—, es que **digan cosas
distintas**. Si el fichero se construyera leyendo la caché de partidas activas por
su cuenta, un día el endpoint listaría una partida y el fichero no, o al revés, y
el grabador se quedaría sin grabar sin que nada avisara. Pasó el 30-09-2026 con un
módulo aparte que hacía exactamente eso, y se quitó.

Así que lo que se comprueba aquí, sobre todo, es que **los dos caminos lean del
mismo sitio**: el fichero tiene que ser `listado()`, ni más ni menos.

Uso:
    python scripts/test_partidas_vivo.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tracking.soloq import partidas_en_vivo as pv                 # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def partida(game_id: int, clave: str = "CLAVE==", duracion: int | None = -78,
            plataforma: str = "euw1") -> SimpleNamespace:
    """Un objeto con la forma del `match` que llega desde el checker."""
    extra: dict = {"observers": {"encryptionKey": clave}}
    if duracion is not None:
        extra["gameLength"] = duracion
    return SimpleNamespace(game_id=game_id, platform=plataforma, datos_extra=extra)


def limpiar() -> None:
    pv.vaciar()
    pv._ultima_escritura = 0
    pv._degradado = False
    if pv.FICHERO.exists():
        pv.FICHERO.unlink()


def prueba_publica_el_fichero() -> None:
    print("\n=== publicar una partida deja el fichero ===")
    limpiar()

    pv.publicar(partida(111), ["Vladi (FNC)"])

    ok(pv.FICHERO.exists(), f"se escribió {pv.FICHERO.name}")
    if not pv.FICHERO.exists():
        return
    datos = json.loads(pv.FICHERO.read_text(encoding="utf-8"))
    ok(len(datos.get("partidas", [])) == 1, "con una partida dentro")
    p = datos["partidas"][0]
    ok(p["game_id"] == 111, "y el identificador correcto", str(p["game_id"]))
    ok(p["plataforma"] == "EUW1", "el servidor en mayúsculas", p["plataforma"])
    ok(p["clave"] == "CLAVE==", "y la clave de espectador")
    ok(p["pros"] == ["Vladi (FNC)"], "con el pro que la jugaba", str(p["pros"]))
    ok("generado" in datos, "y la marca de tiempo del volcado")
    limpiar()


def prueba_el_fichero_es_listado() -> None:
    print("\n=== y el fichero es exactamente lo que sirve el endpoint ===")
    limpiar()

    pv.publicar(partida(222), ["Uno (AAA)"])
    pv._ultima_escritura = 0
    pv.publicar(partida(333, plataforma="na1"), ["Dos (BBB)"])
    # `listado()` y el fichero se piden seguidos, así que `generado` puede diferir
    # en milisegundos: se compara todo menos eso.
    del_fichero = json.loads(pv.FICHERO.read_text(encoding="utf-8"))
    del_endpoint = pv.listado()
    del_fichero.pop("generado", None)
    del_endpoint.pop("generado", None)

    ok(del_fichero == del_endpoint,
       "el fichero y `listado()` dicen lo mismo, palabra por palabra",
       f"{len(del_fichero.get('partidas', []))} partidas")
    limpiar()


def prueba_suma_los_pros() -> None:
    print("\n=== una partida con tres pros se detecta tres veces ===")
    limpiar()

    for nombre in ("Uno (AAA)", "Dos (BBB)", "Tres (CCC)"):
        pv.publicar(partida(444), [nombre])
        pv._ultima_escritura = 0

    entrada = pv.listado()["partidas"][0]
    ok(len(entrada["pros"]) == 3, "quedan los tres, no solo el último",
       str(entrada["pros"]))
    ok(entrada["pros"] == ["Uno (AAA)", "Dos (BBB)", "Tres (CCC)"],
       "y en el orden en que se detectaron")
    limpiar()


def prueba_sin_clave_no_se_publica() -> None:
    print("\n=== sin clave de espectador no se publica ===")
    limpiar()

    # Sin clave no se pueden descifrar los chunks: publicarla solo haría que el
    # grabador la eligiera y perdiera el tiempo.
    pv.publicar(partida(555, clave=""), ["Uno (AAA)"])
    ok(not pv.listado()["partidas"], "no aparece en la lista")
    ok(not pv.FICHERO.exists(), "ni se escribe el fichero")
    limpiar()


def prueba_game_length() -> None:
    print("\n=== se guarda el reloj del servidor de espectadores ===")
    limpiar()

    pv.publicar(partida(666, duracion=-78), ["Uno (AAA)"])
    entrada = pv.listado()["partidas"][0]
    ok(entrada.get("game_length") == -78,
       "`game_length` va tal cual, sin normalizar (arranca en negativo)",
       str(entrada.get("game_length")))
    ok(entrada["game_length"] < 0,
       "y el negativo se conserva: es lo que dice que acaba de empezar")

    # Y se refresca cuando el checker vuelve a verla, que es como se sabe que
    # sigue viva.
    pv.publicar(partida(666, duracion=600), ["Uno (AAA)"])
    pv._ultima_escritura = 0
    ok(pv.listado()["partidas"][0]["game_length"] == 600,
       "y se actualiza en la siguiente pasada")

    # Sin `gameLength` en el payload no puede inventarse un número.
    pv.vaciar()
    pv.publicar(partida(777, duracion=None), ["Dos (BBB)"])
    ok(pv.listado()["partidas"][0].get("game_length") is None,
       "sin dato no se inventa nada")
    limpiar()


def prueba_caducidad() -> None:
    print("\n=== una partida que nadie renueva caduca ===")
    limpiar()

    pv.publicar(partida(888), ["Uno (AAA)"])
    ok(len(pv.listado()["partidas"]) == 1, "está recién publicada")
    # Se envejece a mano: una partida dura como mucho una hora, así que a los 90
    # minutos lo que quede ahí ya no se puede grabar.
    pv._partidas[888]["actualizada"] = time.time() - pv.CADUCA_S - 10
    ok(not pv.listado()["partidas"], "y a los 90 minutos ya no está")
    limpiar()


def prueba_el_freno_de_escritura() -> None:
    print("\n=== no se reescribe el fichero en cada publicación ===")
    limpiar()

    pv.publicar(partida(999), ["Uno (AAA)"])
    primera = pv.FICHERO.stat().st_mtime_ns
    time.sleep(0.05)
    # Con el freno puesto, esta segunda publicación no debe tocar el disco.
    pv.publicar(partida(999), ["Dos (BBB)"])
    ok(pv.FICHERO.stat().st_mtime_ns == primera,
       "la segunda publicación no reescribe el fichero")

    pv._ultima_escritura = 0
    pv.publicar(partida(999), ["Dos (BBB)"])
    ok(pv.FICHERO.stat().st_mtime_ns != primera,
       "y pasados los 10 segundos sí lo reescribe")
    limpiar()


def prueba_nunca_levanta() -> None:
    print("\n=== publicar no puede tumbar un aviso ===")
    limpiar()

    # `publicar` se llama desde el bucle de avisos: si levantara, alguien se
    # quedaría sin su notificación por un dato auxiliar.
    try:
        pv.publicar(SimpleNamespace(game_id=1, platform=None), ["X (Y)"])
        pv.publicar(SimpleNamespace(game_id=2, platform="euw1", datos_extra=None),
                    ["X (Y)"])
        pv.publicar(None, ["X (Y)"])
        ok(True, "con un `match` roto tampoco levanta")
    except Exception as exc:                                  # noqa: BLE001
        ok(False, "con un `match` roto tampoco levanta", f"{type(exc).__name__}")

    # Y si el disco no deja escribir, se apaga sola en vez de fallar cada vez.
    original = pv.FICHERO
    pv.FICHERO = Path("Z:/no/existe/partidas_vivo.json")
    pv._ultima_escritura = 0
    pv._degradado = False
    pv.publicar(partida(1234), ["Uno (AAA)"])
    ok(pv._degradado, "si no se puede escribir, se marca degradada y no insiste")
    pv.FICHERO = original
    limpiar()


def main() -> int:
    prueba_publica_el_fichero()
    prueba_el_fichero_es_listado()
    prueba_suma_los_pros()
    prueba_sin_clave_no_se_publica()
    prueba_game_length()
    prueba_caducidad()
    prueba_el_freno_de_escritura()
    prueba_nunca_levanta()

    print(f"\nfallos : {len(fallos)}")
    for f in fallos:
        print(f"  - {f}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())

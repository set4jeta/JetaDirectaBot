"""Pruebas de `utils.safe_json` y del extractor de payload de dpm.lol.

No usa red: el HTML de dpm.lol se simula con la misma estructura real
(`self.__next_f.push([1,"..."])`) capturada de la página de G2.

Ejecutar:
    python scripts/test_safe_json.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apis.dpm_payload import (  # noqa: E402
    extraer_jugadores,
    mejor_rango_soloq,
    normalizar_lane,
    reconstruir_payload,
)
from utils.safe_json import guardar_json_atomico, guardar_lista_json  # noqa: E402

_fallos: list[str] = []
_ok = 0


def comprobar(condicion: bool, descripcion: str) -> None:
    global _ok
    if condicion:
        _ok += 1
        print(f"  ok   {descripcion}")
    else:
        _fallos.append(descripcion)
        print(f"  FALLO {descripcion}")


def _leer(ruta: str):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------- #
# safe_json
# ---------------------------------------------------------------------- #

def test_guardas(tmp: str) -> None:
    print("\nGuardas de escritura")
    ruta = os.path.join(tmp, "accounts.json")

    # Primera escritura: no hay nada previo, debe crear el fichero.
    comprobar(
        guardar_lista_json(ruta, [{"n": i} for i in range(10)], etiqueta="t") is True,
        "primera escritura con 10 elementos crea el fichero",
    )
    comprobar(len(_leer(ruta)) == 10, "el fichero tiene los 10 elementos")

    # El caso que motivó todo esto: la fuente devuelve [].
    comprobar(
        guardar_lista_json(ruta, [], etiqueta="t") is False,
        "una lista vacía se rechaza cuando ya había datos",
    )
    comprobar(len(_leer(ruta)) == 10, "los 10 elementos siguen intactos tras el rechazo")

    # Encogimiento brusco: 4 de 10 está por debajo del 70 %.
    comprobar(
        guardar_lista_json(ruta, [{"n": i} for i in range(4)], etiqueta="t") is False,
        "un encogimiento del 60 % se rechaza",
    )
    comprobar(len(_leer(ruta)) == 10, "los datos buenos sobreviven al encogimiento")

    # Encogimiento tolerable: 8 de 10 es exactamente el 80 %.
    comprobar(
        guardar_lista_json(ruta, [{"n": i} for i in range(8)], etiqueta="t") is True,
        "una bajada del 20 % sí se acepta",
    )
    comprobar(len(_leer(ruta)) == 8, "el fichero refleja los 8 elementos")

    # Crecer siempre vale.
    comprobar(
        guardar_lista_json(ruta, [{"n": i} for i in range(50)], etiqueta="t") is True,
        "crecer de 8 a 50 se acepta",
    )

    # Backup del contenido anterior.
    comprobar(os.path.exists(f"{ruta}.bak"), "se dejó copia de seguridad .bak")
    comprobar(len(_leer(f"{ruta}.bak")) == 8, "el .bak tiene el contenido anterior")

    # No debe quedar basura del fichero temporal.
    comprobar(not os.path.exists(f"{ruta}.tmp"), "no queda ningún .tmp suelto")

    # min_ratio configurable: con 0.95, perder 3 de 50 debe rechazarse.
    comprobar(
        guardar_lista_json(
            ruta, [{"n": i} for i in range(47)], etiqueta="t", min_ratio=0.95
        )
        is False,
        "con min_ratio=0.95 se rechaza perder 3 de 50",
    )

    # permitir_vacio explícito, para el caso legítimo de borrar a propósito.
    comprobar(
        guardar_lista_json(ruta, [], etiqueta="t", permitir_vacio=True) is True,
        "permitir_vacio=True sí deja escribir la lista vacía",
    )
    comprobar(_leer(ruta) == [], "el fichero quedó vacío al pedirlo explícitamente")


def test_fichero_corrupto(tmp: str) -> None:
    print("\nFichero previo corrupto")
    ruta = os.path.join(tmp, "roto.json")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("{esto no es json")

    comprobar(
        guardar_lista_json(ruta, [{"n": 1}], etiqueta="t") is True,
        "un JSON corrupto no bloquea la siguiente escritura buena",
    )
    comprobar(_leer(ruta) == [{"n": 1}], "el corrupto quedó reemplazado por datos válidos")


# ---------------------------------------------------------------------- #
# Escritura atómica sin guardas (cachés y ficheros de estado)
# ---------------------------------------------------------------------- #

def test_atomico(tmp: str) -> None:
    """El caso del 03-09-2026: disco lleno dejando ficheros en 0 bytes.

    Se simula el disco lleno haciendo que `json.dump` falle a mitad del volcado
    (un objeto que no es serializable revienta *después* de haber abierto el
    fichero), que es exactamente la secuencia peligrosa: destino ya truncado y
    escritura sin terminar. Con `tmp` + `os.replace` el destino no se toca.
    """
    print("\nEscritura atómica")
    ruta = os.path.join(tmp, "cache.json")

    comprobar(
        guardar_json_atomico(ruta, {"a": 1, "b": 2}, etiqueta="t") is True,
        "escribe un dict normal",
    )
    comprobar(_leer(ruta) == {"a": 1, "b": 2}, "el contenido es el esperado")

    # Un dict que encoge SÍ debe poder escribirse: es una caché, no un roster.
    comprobar(
        guardar_json_atomico(ruta, {"a": 1}, etiqueta="t") is True,
        "un dict más pequeño se acepta (aquí no hay guarda de recuento, a propósito)",
    )

    # Fallo a mitad del volcado: el fichero bueno debe seguir en pie.
    class NoSerializable:
        pass

    escribio = guardar_json_atomico(ruta, {"malo": NoSerializable()}, etiqueta="t")
    comprobar(escribio is False or _leer(ruta) == {"a": 1},
              "un volcado que falla no deja el destino truncado")
    comprobar(_leer(ruta) == {"a": 1}, "el contenido anterior sobrevive al fallo")
    comprobar(not os.path.exists(f"{ruta}.tmp"), "no queda .tmp suelto tras el fallo")


def test_tolerancia_a_cero_bytes(tmp: str) -> None:
    """Un fichero de 0 bytes no puede impedir arrancar.

    `load_announced_games` se llama desde `ActiveGameTracker.__init__`, así que
    cuando leía con `json.load` a pelo un fichero vacío no costaba un aviso:
    tumbaba la construcción del tracker. Es lo que quedó montado el 03-09-2026
    después de que el disco se llenara.
    """
    print("\nFicheros de 0 bytes")
    from tracking.soloq import notifier

    original = notifier.ANNOUNCED_GAMES_PATH
    ruta = os.path.join(tmp, "announced_games.json")
    notifier.ANNOUNCED_GAMES_PATH = ruta
    try:
        open(ruta, "w").close()  # 0 bytes, como lo dejó el disco lleno
        comprobar(notifier.load_announced_games() == {},
                  "un announced_games.json de 0 bytes devuelve {} en vez de reventar")

        with open(ruta, "w", encoding="utf-8") as f:
            f.write("{no es json")
        comprobar(notifier.load_announced_games() == {},
                  "un announced_games.json corrupto devuelve {}")

        notifier.save_announced_games({"123": {"456": 1}})
        comprobar(notifier.load_announced_games() == {"123": {"456": 1}},
                  "se vuelve a escribir y leer bien tras el arreglo")
        comprobar(not os.path.exists(f"{ruta}.tmp"), "no queda .tmp tras guardar")
    finally:
        notifier.ANNOUNCED_GAMES_PATH = original


# ---------------------------------------------------------------------- #
# Extractor del payload de dpm.lol
# ---------------------------------------------------------------------- #

def _html_falso(jugadores: list[dict]) -> str:
    """Reproduce la estructura real: el JSON troceado entre varios push."""
    bloque = '34:["$","$L3c",null,{"players":' + json.dumps(jugadores) + "}]"
    mitad = len(bloque) // 2
    trozos = [bloque[:mitad], bloque[mitad:]]
    partes = [
        f"self.__next_f.push([1,{json.dumps(t)}])" for t in trozos
    ]
    ruido = (
        'self.__next_f.push([1,"[\\"$\\",\\"path\\",null,'
        '{\\"d\\":\\"M17 21C16.7 21 5.7 21 5.8 20.1L8.8 17.1Z\\"}]"])'
    )
    return "<html><script>" + ruido + "".join(partes) + "</script></html>"


JUGADORES_FALSOS = [
    {
        "puuid": "P" * 78,
        "gameName": "G2 SkewMond",
        "tagLine": "3327",
        "displayName": "SkewMond",
        "role": "PRO",
        "team": "G2",
        "lane": "JUNGLE",
        "platform": "EUW1",
        "ranks": [
            {"queue": "RANKED_FLEX_SR", "tier": "DIAMOND", "leaguePoints": 10},
            {"queue": "RANKED_SOLO_5x5", "tier": "CHALLENGER", "leaguePoints": 2820},
        ],
    },
    {
        "puuid": "Q" * 78,
        "gameName": "G2 Caps",
        "tagLine": "1918",
        "displayName": "Caps",
        "lane": "MIDDLE",
        "platform": "EUW1",
        "ranks": [],
    },
]


def test_payload() -> None:
    print("\nExtractor del payload de dpm.lol")
    html = _html_falso(JUGADORES_FALSOS)

    flujo = reconstruir_payload(html)
    comprobar('"players":[' in flujo, "el payload se reconstruye uniendo los push")

    jugadores = extraer_jugadores(html)
    comprobar(len(jugadores) == 2, "extrae los 2 jugadores partidos entre dos push")
    comprobar(
        [j["displayName"] for j in jugadores] == ["SkewMond", "Caps"],
        "conserva el orden y los displayName",
    )
    comprobar(len(jugadores[0]["puuid"]) == 78, "el PUUID llega completo")

    # El ruido de los SVG lleva corchetes dentro de cadenas: el recorte por
    # conteo de corchetes tiene que ignorarlos.
    comprobar(
        extraer_jugadores("<html><script>" + "".join(
            f'self.__next_f.push([1,{json.dumps(t)}])' for t in ['{"players":[{"gameName":"a]b","tagLine":"1"}]}']
        ) + "</script></html>")[0]["gameName"] == "a]b",
        "un corchete dentro de una cadena no corta el recorte",
    )

    comprobar(extraer_jugadores("<html>sin payload</html>") == [], "sin payload devuelve []")
    comprobar(
        extraer_jugadores(_html_falso([])) == [],
        "un array players vacío devuelve [] (y la guarda lo rechazará)",
    )

    print("\nNormalización")
    comprobar(normalizar_lane("JUNGLE") == "jungle", "JUNGLE -> jungle")
    comprobar(normalizar_lane("MIDDLE") == "mid", "MIDDLE -> mid")
    comprobar(normalizar_lane("UTILITY") == "support", "UTILITY -> support")
    comprobar(normalizar_lane("BOTTOM") == "bot", "BOTTOM -> bot")
    comprobar(normalizar_lane(None) is None, "None -> None")
    comprobar(normalizar_lane("cualquiera") is None, "un valor desconocido -> None")

    rango = mejor_rango_soloq(JUGADORES_FALSOS[0])
    comprobar(
        rango is not None and rango["tier"] == "CHALLENGER",
        "elige SoloQ y no Flex aunque Flex vaya primero",
    )
    comprobar(mejor_rango_soloq(JUGADORES_FALSOS[1]) is None, "sin rangos devuelve None")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="jetabot_safejson_")
    try:
        test_guardas(tmp)
        test_fichero_corrupto(tmp)
        test_atomico(tmp)
        test_tolerancia_a_cero_bytes(tmp)
        test_payload()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = _ok + len(_fallos)
    print(f"\n{_ok}/{total} comprobaciones pasadas")
    if _fallos:
        print("Fallos:")
        for f in _fallos:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""El bot no puede arrancar sin censo, aunque dpm.lol no conteste.

Qué vigila esta prueba
----------------------
El 01-11-2026 el servicio se reanudó con el contador a cero y **cero cuentas**:
Cloudflare contestaba 403 a la IP de Render, así que `accounts_from_teams.json`
no llegaba a crearse. El bot parecía sano —`/health` en 200, `/live-games` con
JSON válido— y no avisaba de nada. El síntoma era indistinguible de «no hay
partidos ahora mismo».

La red de seguridad es una copia **compacta** del censo (274 KB frente a 1,7 MB)
que viaja en la rama de estado y se lee cuando el fichero bueno no está. Esto
comprueba que:

1. La copia conserva lo que el barrido necesita: nombre, equipo, liga y las
   cuentas con su PUUID y su plataforma.
2. Es de verdad más pequeña (si no, no cabría en la rama de estado).
3. `load_tracked_accounts` cae en ella cuando falta el censo grande.
4. El censo grande **manda** cuando existe: la copia no puede taparlo.
5. Una copia vacía o corrupta no tumba nada.

Uso:
    python scripts/test_censo.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracking.soloq import censo  # noqa: E402
from tracking.soloq import accounts_io  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def _jugador(nombre: str, liga: str, cuentas: list[tuple[str, str, str, str]]):
    """`cuentas` = (game_name, tag_line, puuid, platform)."""
    return {
        "name": nombre,
        "displayName": nombre,
        "team": "T1",
        "team_name": "T1 Esports",
        "league": liga,
        "role": "Mid",
        # Datos de ficha que la copia tiene que tirar: no sirven para barrer.
        "age": 29,
        "country": "Korea",
        "contract": "2028-11-20T00:00:00.000Z",
        "last_champions": [{"champion_name": "Azir", "games": 40}],
        "links": [{"url": "https://x.com/faker"}],
        "accounts": [
            {
                "riot_id": {"game_name": g, "tag_line": t},
                "puuid": p,
                "platform": s,
                "rank": {"tier": "CHALLENGER", "lp": 1200},
                "profile_icon": 7,
                "summoner_level": 900,
            }
            for g, t, p, s in cuentas
        ],
    }


class _Rutas:
    """Desvía los ficheros a un directorio temporal y los deja como estaban."""

    def __init__(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="lolpro_censo_")
        self._censo_ruta = censo.RUTA
        self._teams = accounts_io.JSON_TEAMS_PATH
        self._cache = accounts_io._tracked_cache

    def __enter__(self) -> "_Rutas":
        censo.RUTA = os.path.join(self.tmp, "censo_compacto.json")
        accounts_io.JSON_TEAMS_PATH = os.path.join(self.tmp, "accounts_from_teams.json")
        accounts_io._tracked_cache = None
        return self

    def __exit__(self, *_) -> None:
        censo.RUTA = self._censo_ruta
        accounts_io.JSON_TEAMS_PATH = self._teams
        accounts_io._tracked_cache = self._cache


def prueba_ida_y_vuelta() -> None:
    print("\n=== la copia conserva lo que hace falta ===")
    original = [
        _jugador("Faker", "lck", [
            ("Hide on bush", "KR1", "puuid-faker-1", "KR"),
            ("Hide in bush", "NA1", "puuid-faker-2", "NA1"),
        ]),
        _jugador("Jojopyun", "worlds", [
            ("jojooooooo", "NA1", "puuid-jojo-1", "NA1"),
        ]),
    ]

    compacto = censo.compactar(original)
    ok(len(compacto) == 2, "salen los dos jugadores", str(len(compacto)))

    # Los datos de ficha no viajan: la copia es para barrer, no para pintar.
    crudo = json.dumps(compacto)
    ok("last_champions" not in crudo, "no se lleva las estadísticas de campeones")
    ok("contract" not in crudo, "ni el contrato")
    ok("profile_icon" not in crudo, "ni el icono de perfil")

    # Y lo que sí hace falta, sí.
    ida = censo._expandir(compacto[0])
    ok(ida["name"] == "Faker", "se recupera el nombre")
    ok(ida["team"] == "T1", "el equipo")
    ok(ida["league"] == "lck", "la liga")
    ok(ida["displayName"] == "Faker",
       "y `displayName`, que es lo que resuelve /track")
    ok(len(ida["accounts"]) == 2, "las dos cuentas")
    ok(ida["accounts"][0]["puuid"] == "puuid-faker-1", "con su PUUID")
    ok(ida["accounts"][0]["platform"] == "KR", "y su plataforma")
    ok(ida["accounts"][1]["riot_id"]["tag_line"] == "NA1",
       "y su riot id completo")


def prueba_tamano() -> None:
    print("\n=== la copia es lo bastante pequeña para viajar ===")
    # Se mide sobre el censo real si está; si no, se simula con 900 jugadores.
    ruta = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tracking", "soloq", "accounts_from_teams.json",
    )
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            completo = json.load(fh)
        origen = "el censo real"
    else:
        completo = [
            _jugador(f"Jugador{i}", "lec", [
                (f"cuenta{i}", "EUW", f"puuid-{i}", "EUW1"),
                (f"cuenta{i}b", "EUW", f"puuid-{i}b", "KR"),
            ])
            for i in range(900)
        ]
        origen = "un censo simulado de 900"

    compacto = censo.compactar(completo)
    kb_completo = len(json.dumps(completo).encode()) / 1024
    kb_compacto = len(
        json.dumps(compacto, ensure_ascii=False, separators=(",", ":")).encode()
    ) / 1024

    print(f"         ({origen}: {kb_completo:.0f} KB -> {kb_compacto:.0f} KB)")
    ok(kb_compacto < 1024,
       "cabe en la API de contenidos de GitHub (por debajo de 1 MB)",
       f"{kb_compacto:.0f} KB")
    ok(kb_compacto < kb_completo / 2,
       "y pesa menos de la mitad que el censo completo",
       f"{kb_compacto / kb_completo:.0%}")
    ok(len(compacto) == len(completo),
       "sin perder jugadores por el camino",
       f"{len(compacto)} de {len(completo)}")


def prueba_fallback() -> None:
    print("\n=== sin censo grande, se usa la copia ===")
    with _Rutas() as rutas:
        # No hay fichero bueno: solo la copia.
        ok(not os.path.exists(accounts_io.JSON_TEAMS_PATH), "no hay censo grande")
        censo.escribir([
            _jugador("Faker", "lck", [("Hide on bush", "KR1", "p1", "KR")]),
            _jugador("Jojopyun", "worlds", [("jojooooooo", "NA1", "p2", "NA1")]),
        ])
        ok(os.path.exists(censo.RUTA), "la copia se escribe")

        jugadores = accounts_io.load_tracked_accounts()
        ok(len(jugadores) == 2, "se leen dos jugadores de la copia",
           str(len(jugadores)))
        ok({j.name for j in jugadores} == {"Faker", "Jojopyun"},
           "con sus nombres")
        ok(all(j.accounts for j in jugadores),
           "y cada uno con sus cuentas, que es lo que el barrido necesita")
        ok(any(a.puuid == "p2" for j in jugadores for a in j.accounts),
           "los PUUID llegan intactos: sin ellos no se puede sondear")

        # El censo grande manda en cuanto aparece: la copia no puede taparlo.
        with open(accounts_io.JSON_TEAMS_PATH, "w", encoding="utf-8") as fh:
            json.dump([
                _jugador("Caps", "lec", [("G2 Caps", "EUW", "p3", "EUW1")]),
            ], fh)
        # `mtime` con la misma resolución que el sistema de ficheros: sin esto la
        # caché por fecha podría devolver lo de la copia.
        os.utime(accounts_io.JSON_TEAMS_PATH, None)
        accounts_io._tracked_cache = None

        jugadores = accounts_io.load_tracked_accounts()
        ok(len(jugadores) == 1 and jugadores[0].name == "Caps",
           "cuando existe el censo grande, manda el censo grande")


def prueba_copias_malas() -> None:
    print("\n=== una copia mala no tumba nada ===")
    with _Rutas():
        ok(censo.leer() == [], "sin copia devuelve lista vacía")
        ok(censo.edad_dias() is None, "y no inventa una antigüedad")

        # Vacía: no se escribe. Una copia vacía es peor que ninguna, porque
        # taparía el fallo con un «todo bien» de cero jugadores.
        ok(not censo.escribir([]), "no se escribe una copia sin jugadores")
        ok(not censo.escribir([_jugador("X", "lec", [])]),
           "ni una con jugadores que no tienen cuentas")

        # Corrupta: se ignora y se sigue.
        with open(censo.RUTA, "w", encoding="utf-8") as fh:
            fh.write("{esto no es json")
        ok(censo.leer() == [], "una copia ilegible se ignora")
        ok(accounts_io.load_tracked_accounts() == [],
           "y el tracker se queda sin cuentas sin reventar")


def prueba_antiguedad() -> None:
    print("\n=== la copia dice su edad ===")
    with _Rutas():
        censo.escribir([_jugador("Faker", "lck", [("a", "b", "p", "KR")])])
        edad = censo.edad_dias()
        ok(edad is not None and edad < 0.01,
           "recién escrita, 0 días", "None" if edad is None else f"{edad:.3f}")
        ok("antigüedad" in censo.resumen(), "y el resumen la enseña",
           censo.resumen())


def main() -> int:
    print("=" * 74)
    print("El censo sobrevive aunque dpm.lol no responda.")
    print("=" * 74)

    prueba_ida_y_vuelta()
    prueba_tamano()
    prueba_fallback()
    prueba_copias_malas()
    prueba_antiguedad()

    print("\n" + "=" * 74)
    if fallos:
        print(f"fallos: {len(fallos)}")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("fallos: 0")
    print("El bot arranca con jugadores aunque el censo no se pueda bajar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

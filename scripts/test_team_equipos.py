"""Prueba offline de `/team`: repetidos, sugerencias y el "mejor de N".

Por qué existe
--------------
El dueño probó `/team koi` y `/team mkoi` a mano y encontró tres cosas que
ninguna prueba miraba:

1. **Jugadores repetidos.** El roster guarda una entrada por (jugador, liga), así
   que quien juega su liga y además el MSI salía dos veces. `/team G2` listaba a
   Caps dos veces. Afectaba a 11 equipos de 168 y no se veía en los tests porque
   todos usaban jugadores sintéticos de un solo equipo.
2. **Sin pista cuando el equipo no existe.** `/team koi` decía «no hay
   jugadores» y soltaba los 168 tricodes. Para un bot que presume de datos, eso
   es peor que no decir nada.
3. **«mejor de 4» sin explicar y contando de más.** No se entendía que el rango
   es el de la mejor cuenta del jugador, y además contaba cuentas `stale` que no
   traen rango: Myrwn tiene 4 cuentas y solo 1 con datos, así que «mejor de 4»
   no era verdad.

Esta prueba no toca la red ni la API de Riot: importa el cuerpo real del comando
y le cambia la capa de datos por un doble. Sí usa el **fichero de rosters de
verdad**, que es lo que hace que los casos de G2 y MKOI se reproduzcan.

Uso:
    python scripts/test_team_equipos.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core.register_team_commands as mod  # noqa: E402
from tracking.soloq.accounts_io import load_tracked_accounts  # noqa: E402

fallos: list[str] = []


def check(etiqueta: str, ok: bool, detalle: str = "") -> None:
    marca = "OK  " if ok else "FALLO"
    print(f"  [{marca}] {etiqueta}" + (f" — {detalle}" if detalle else ""))
    if not ok:
        fallos.append(etiqueta)


class RespuestaFalsa:
    """Lo mínimo que `_cuerpo_team` usa de `Respuesta`."""

    def __init__(self) -> None:
        self.guild_id = None
        self.enviados: list[str] = []

    async def esperando(self, texto: str = "") -> None:
        pass  # el "⏳ Consultando…" no interesa aquí

    async def error(self, texto: str):
        self.enviados.append(texto)

    async def enviar_partido(self, texto: str, limite: int = 1900) -> None:
        self.enviados.append(texto)

    async def enviar_bloque(self, texto: str, lenguaje: str = "markdown") -> None:
        self.enviados.append(texto)

    async def send(self, content=None, **kwargs):
        if content:
            self.enviados.append(str(content))

    def todo(self) -> str:
        return "\n".join(self.enviados)

    def ultimo(self) -> str:
        return self.enviados[-1] if self.enviados else ""


#: Una línea de jugador: `**Nombre** (cuenta#tag) - Rango`.
_LINEA_JUGADOR = re.compile(r"^\*\*.+?\*\* \(", re.MULTILINE)

#: Las funciones reales, guardadas antes de sustituirlas por dobles. Sin esto,
#: el doble de la sección 1 se cuela en la 3 y la prueba se comprueba a sí misma
#: (pasó: `comparadas` salía 4 porque devolvía `len(cuentas)`, no las válidas).
MEJOR_REAL = mod._mejor_cuenta_de
RANK_REAL = mod._rank_de_cuenta


async def _rank_fijo(jugador, semaforo):
    """Doble de `_mejor_cuenta_de`: sin Riot, la primera cuenta y un rango."""
    cuentas = list(jugador.accounts)
    if not cuentas:
        return None, None, 0
    return cuentas[0], {"tier": "CHALLENGER", "division": "I", "lp": 900}, len(cuentas)


class _Cuenta:
    def __init__(self, nombre: str, puuid: str | None) -> None:
        self.puuid = puuid
        self.riot_id = {"game_name": nombre, "tag_line": "EUW"}
        self.platform = "euw1"
        self.stale = puuid is None


class _Jugador:
    def __init__(self, cuentas) -> None:
        self.name = "Prueba"
        self.team = "G2"
        self.role = "Mid"
        self.accounts = cuentas


async def main() -> int:
    print("=" * 74)
    print("PRUEBA OFFLINE DE /team")
    print("=" * 74)

    disponibles = mod.equipos_disponibles()
    print(f"\n   {len(disponibles)} equipos con jugadores en el fichero")

    # ------------------------------------------------------------------ #
    # 1. Repetidos
    # ------------------------------------------------------------------ #
    print("\n1) Un jugador, una línea")
    crudos = [p for p in load_tracked_accounts() if (p.team or "").upper() == "G2"]
    unicos = mod.sin_repetidos(crudos)
    check(
        "G2: el roster trae al jugador dos veces (liga + MSI)",
        len(crudos) > len(unicos),
        f"{len(crudos)} entradas -> {len(unicos)} jugadores",
    )
    nombres = [p.name for p in unicos]
    check(
        "G2: no queda ningún nombre repetido",
        len(nombres) == len(set(nombres)),
        ", ".join(sorted(nombres)),
    )

    # El mismo caso por el cuerpo del comando: es lo que ve el usuario.
    mod._mejor_cuenta_de = _rank_fijo
    res = RespuestaFalsa()
    await mod._cuerpo_team(res, "g2")
    lineas_g2 = _LINEA_JUGADOR.findall(res.ultimo())
    print(f"   /team g2: {len(lineas_g2)} líneas de jugador")
    for linea in res.ultimo().splitlines():
        if _LINEA_JUGADOR.match(linea):
            print(f"      {linea}")
    check(
        "/team G2 enseña 5 jugadores, no 10",
        len(lineas_g2) == 5,
        f"{len(lineas_g2)} líneas",
    )

    # ------------------------------------------------------------------ #
    # 2. Sugerencias
    # ------------------------------------------------------------------ #
    print("\n2) «¿Quisiste decir…?»")

    casos = [
        ("koi", {"MKOI", "MKF"}, "los dos equipos que son KOI"),
        ("mko", {"MKOI"}, "tricode a medias"),
        ("fenix", {"MKF"}, "el nombre largo lleva acento"),
        ("g2e", {"G2"}, "nombre largo pegado al tricode"),
        ("navy", {"NAVI"}, "errata sin trozo en común"),
    ]
    for consulta, esperados, nota in casos:
        pistas = set(mod.sugerir_equipos(consulta, disponibles))
        check(
            f"«{consulta}» propone {sorted(esperados)} ({nota})",
            esperados <= pistas,
            f"propone {sorted(pistas)}",
        )

    check(
        "una consulta sin parecido no propone nada",
        mod.sugerir_equipos("zzzqqq", disponibles) == [],
        str(mod.sugerir_equipos("zzzqqq", disponibles)),
    )
    check(
        "la sugerencia está acotada (no vuelca los 168)",
        len(mod.sugerir_equipos("a", disponibles)) <= 3,
        f"{len(mod.sugerir_equipos('a', disponibles))} equipos",
    )
    # «koi» y «EKO» se parecen 0,67: es casualidad, no una sugerencia. Sin este
    # corte, /team koi proponía EKO y ensuciaba la respuesta.
    check(
        "«koi» no propone EKO (parecido casual)",
        "EKO" not in mod.sugerir_equipos("koi", disponibles),
        str(mod.sugerir_equipos("koi", disponibles)),
    )
    check(
        "el equipo principal va primero: MKOI antes que MKF",
        mod.sugerir_equipos("koi", disponibles)[:1] == ["MKOI"],
        str(mod.sugerir_equipos("koi", disponibles)),
    )

    print()
    res = RespuestaFalsa()
    await mod._cuerpo_team(res, "koi")
    salida = res.todo()
    print(f"   /team koi ->\n      {salida.replace(chr(10), chr(10) + '      ')}")
    check("/team koi dice «¿Quisiste decir»", "Quisiste decir" in salida)
    check("/team koi propone MKOI", "MKOI" in salida)
    check("/team koi propone MKF (Movistar KOI Fénix)", "MKF" in salida)
    check(
        "/team koi ya no suelta la lista entera de equipos",
        "NAVI" not in salida and "Equipos disponibles" not in salida,
    )

    # Sin ningún parecido sí se enseña la lista: es la red de seguridad.
    res = RespuestaFalsa()
    await mod._cuerpo_team(res, "zzzqqq")
    check(
        "sin parecido, sigue enseñando los equipos disponibles",
        "Equipos disponibles" in res.todo(),
    )

    # ------------------------------------------------------------------ #
    # 3. El «mejor de N»: qué cuenta y a quién se le pone
    # ------------------------------------------------------------------ #
    print("\n3) El sufijo del mejor Elo")

    # 3a. Recuento exacto, con cuentas de laboratorio.
    RANGOS = {
        "p-chall": {"tier": "CHALLENGER", "division": "I", "lp": 900},
        "p-diam": {"tier": "DIAMOND", "division": "II", "lp": 40},
    }

    async def _rank_por_puuid(account, semaforo):
        return RANGOS.get(account.puuid)

    mod._mejor_cuenta_de = MEJOR_REAL
    mod._rank_de_cuenta = _rank_por_puuid

    jugador = _Jugador([
        _Cuenta("principal", "p-chall"),
        _Cuenta("secundaria", "p-diam"),
        _Cuenta("muerta", None),
        _Cuenta("muerta2", None),
    ])
    cuenta, _rango, comparadas = await mod._mejor_cuenta_de(jugador, asyncio.Semaphore(2))
    check(
        "4 cuentas, 2 con rango: se cuentan 2, no 4",
        comparadas == 2,
        f"comparadas={comparadas}",
    )
    check(
        "se elige la de más Elo (Challenger, no Diamante)",
        cuenta.riot_id["game_name"] == "principal",
        cuenta.riot_id["game_name"],
    )

    jugador = _Jugador([_Cuenta("sola", "p-chall"), _Cuenta("muerta", None)])
    _c, _r, comparadas = await mod._mejor_cuenta_de(jugador, asyncio.Semaphore(2))
    check(
        "una sola cuenta con rango: no se anuncia comparación",
        comparadas == 1,
        f"comparadas={comparadas}",
    )

    # 3b. Con el roster de verdad: cuentas `stale` fuera del recuento.
    async def _rank_si_viva(account, semaforo):
        """Rango solo para cuentas consultables, como hace Riot de verdad."""
        if not getattr(account, "puuid", None) or getattr(account, "stale", False):
            return None
        return {"tier": "CHALLENGER", "division": "I", "lp": 900}

    mod._rank_de_cuenta = _rank_si_viva
    res = RespuestaFalsa()
    await mod._cuerpo_team(res, "mkoi")
    salida = res.todo()
    print(f"   /team mkoi ->\n      {salida.replace(chr(10), chr(10) + '      ')}")
    check(
        "con datos reales: Myrwn (1 cuenta con datos) ya no lleva sufijo",
        "Myrwn" in salida and not re.search(r"Myrwn.*mejor de", salida),
    )
    check(
        "Jojopyun (5 cuentas consultables) sí lleva sufijo",
        re.search(r"Jojopyun.*mejor de \d+ cuentas", salida) is not None,
    )
    check("el sufijo nunca dice «mejor de 1»", "mejor de 1" not in salida)

    mod._mejor_cuenta_de = MEJOR_REAL
    mod._rank_de_cuenta = RANK_REAL

    print("\n" + "=" * 74)
    if fallos:
        print(f"FALLOS ({len(fallos)}):")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("Todo correcto: /team sin repetidos, con sugerencias y el sufijo claro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Prueba de los objetivos por canal: `/subscribe soloq lck`, `/subscribe esports lck`.

Por qué existe
--------------
Hasta el 22-09-2026 un canal recibía **todo** lo que siguiera su servidor, y no
había forma de tener un canal para la LEC y otro para la LCK, ni uno solo de
partidos de esports. Ahora `/subscribe` acepta el mismo tipo de objetivo que
`/track` —liga, equipo, pro o cuenta— con la misma semántica: **lo que pides es lo
que llega**.

Lo que hay que defender aquí, y que no se ve mirando el código:

1. **Un canal sin entrada no es un canal vacío.** Si «sin entrada» y «entrada
   vacía» significaran lo mismo, cualquier fichero ilegible dejaría sin avisos a
   los servidores que ya funcionaban, y sin ningún error.
2. **La liga del objetivo tiene que entrar en el barrido.** Un aviso solo existe
   si la liga se consulta: sin esto, `/subscribe soloq lck` dejaría un canal que
   no recibe nada **nunca** y sin ningún error, que es el peor fallo posible.
3. **Un equipo aparece en el roster en dos ligas** (la suya y el MSI), y quedarse
   con la primera coincidencia metía el MSI en el barrido: T1 se quedaba sin
   avisos de LCK.

Es offline: el fichero de objetivos se apunta a un temporal y el roster es el
real, que es lo que hace que el caso de T1 se reproduzca.

Uso:
    python scripts/test_canales_objetivos.py
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import tracking.soloq.channel_targets as ct  # noqa: E402

# El fichero de objetivos, a un temporal: la prueba no toca el del repo.
ct.RUTA = pathlib.Path(tempfile.mkdtemp()) / "channel_targets.json"

import core.notification_config_commands as nc  # noqa: E402
from tracking.soloq import channel_config, leagues, plans  # noqa: E402

GUILD = 111222333444555666
CANAL = 987654321

fallos: list[str] = []


def check(etiqueta: str, ok: bool, detalle: str = "") -> None:
    marca = "OK  " if ok else "FALLO"
    print(f"  [{marca}] {etiqueta}" + (f" — {detalle}" if detalle else ""))
    if not ok:
        fallos.append(etiqueta)


class RespuestaFalsa:
    def __init__(self, guild_id=GUILD, canal_id=CANAL):
        self.guild_id = guild_id
        self.autor_id = 1
        self.canal = type("C", (), {"id": canal_id, "mention": f"<#{canal_id}>"})()
        self.guild = None
        self.salida: list[str] = []

    def es_admin(self) -> bool:
        return True

    async def esperando(self, texto: str = "") -> None:
        pass

    async def error(self, texto: str) -> None:
        self.salida.append("ERROR: " + texto)

    async def send(self, content=None, **kwargs):
        if content:
            self.salida.append(str(content))

    async def send_privado(self, texto: str, **kwargs) -> None:
        self.salida.append(str(texto))

    def todo(self) -> str:
        return "\n".join(self.salida)


def probar_almacen() -> None:
    print("\n1) El almacén: «sin entrada» no es «entrada vacía»")
    check(
        "un canal sin entrada no tiene objetivos",
        ct.objetivos_de(GUILD, CANAL) == {},
        str(ct.objetivos_de(GUILD, CANAL)),
    )

    ct.poner(GUILD, CANAL, "soloq", "lec")
    ct.poner(GUILD, CANAL, "esports", "lck")
    check(
        "lo guardado se lee igual",
        ct.objetivos_de(GUILD, CANAL) == {"soloq": ["lec"], "esports": ["lck"]},
        str(ct.objetivos_de(GUILD, CANAL)),
    )
    check(
        "otro canal del mismo servidor sigue sin objetivos",
        ct.objetivos_de(GUILD, 555) == {},
        str(ct.objetivos_de(GUILD, 555)),
    )
    check("poner dos veces el mismo no lo duplica", _no_duplica())

    check("limpiar deja el canal como estaba", ct.limpiar(GUILD, CANAL) is True)
    check("y ahora no tiene objetivos", ct.objetivos_de(GUILD, CANAL) == {})
    check("limpiar dos veces devuelve False", ct.limpiar(GUILD, CANAL) is False)


def _no_duplica() -> bool:
    ct.poner(GUILD, 777, "soloq", "lec")
    ct.poner(GUILD, 777, "soloq", "lec")
    return ct.objetivos_de(GUILD, 777) == {"soloq": ["lec"]}


def probar_filtros() -> None:
    print("\n2) El filtro: lo que pides es lo que llega")
    casos = [
        ("la liga pedida entra", ct.acepta_soloq(["lec"], liga="lec"), True),
        ("otra liga no entra", ct.acepta_soloq(["lec"], liga="lck"), False),
        ("un pro pedido entra", ct.acepta_soloq(["Elyoya"], jugador="Elyoya"), True),
        ("otro pro no entra", ct.acepta_soloq(["Elyoya"], jugador="Caps"), False),
        ("un equipo pedido entra", ct.acepta_soloq(["T1"], equipo="T1"), True),
        ("una cuenta pedida entra", ct.acepta_soloq(["Caps#EUW"], cuenta="Caps#EUW"), True),
        ("«*» es todas las ligas", ct.acepta_soloq(["*"], liga="cblol"), True),
        ("mayúsculas y espacios dan igual", ct.acepta_soloq(["  LEC "], liga="lec"), True),
        ("sin objetivos no le toca nada", ct.acepta_soloq(None, liga="lec"), False),
        ("lista vacía tampoco", ct.acepta_soloq([], liga="lec"), False),
    ]
    for etiqueta, obtenido, esperado in casos:
        check(etiqueta, obtenido is esperado, f"{obtenido} (esperaba {esperado})")

    print("\n3) El filtro de partidos oficiales")
    check(
        "la liga del partido manda",
        ct.acepta_esports(["lec"], liga="LEC", equipos=("G2", "FNC")) is True,
    )
    check(
        "otra liga no pasa",
        ct.acepta_esports(["lec"], liga="LCK", equipos=("T1", "GEN")) is False,
    )
    check(
        "seguir un equipo es querer sus partidos",
        ct.acepta_esports(["T1"], liga="LCK", equipos=("T1", "GEN")) is True,
    )
    check(
        "y no los de otros",
        ct.acepta_esports(["T1"], liga="LCK", equipos=("GEN", "KT")) is False,
    )


def probar_resolucion() -> None:
    print("\n4) Qué acepta el objetivo")
    casos = [
        ("lec", ("lec", "LEC", "lec"), "una liga por su código"),
        ("korea", ("lck", "LCK", "lck"), "una liga por su alias"),
        ("Caps#EUW", ("Caps#EUW", "Caps#EUW", ""), "una cuenta suelta"),
        ("loquesea", None, "algo que no existe no se acepta"),
    ]
    for texto, esperado, nota in casos:
        obtenido = nc._resolver_objetivo(texto)
        check(f"«{texto}» -> {esperado} ({nota})", obtenido == esperado, str(obtenido))

    # Un equipo sale en su liga **y** en el MSI: hay que quedarse con la suya.
    for equipo, liga in (("T1", "lck"), ("G2", "lec"), ("BLG", "lpl")):
        obtenido = nc._resolver_objetivo(equipo)
        check(
            f"«{equipo}» resuelve a su liga doméstica ({liga}), no al MSI",
            obtenido is not None and obtenido[2] == liga,
            str(obtenido),
        )

    jugador = nc._resolver_objetivo("Elyoya")
    check(
        "un pro del roster se reconoce y trae su liga",
        jugador is not None and jugador[2] == "lec",
        str(jugador),
    )


async def probar_comando() -> None:
    print("\n5) `/subscribe soloq lck` de punta a punta")

    # Con plan gratuito solo cabe **una** liga, así que pedir la LCK sin cupo
    # falla — y eso es correcto: se prueba aparte, más abajo. Aquí se parte del
    # Pro para poder ver el camino bueno.
    plans.asignar_plan(GUILD, "pro")
    leagues.establecer_ligas(GUILD, ["lec"])
    check("el servidor empieza siguiendo solo la LEC", leagues.ligas_de(GUILD) == ["lec"])

    res = RespuestaFalsa()
    await nc._cuerpo_subscribe(res, {"type": "soloq", "target": "lck"})
    salida = res.todo()
    check("el canal queda añadido", CANAL in channel_config.canales_de(GUILD))
    check(
        "y con su objetivo guardado",
        ct.objetivos_de(GUILD, CANAL) == {"soloq": ["lck"]},
        str(ct.objetivos_de(GUILD, CANAL)),
    )
    check(
        "y la LCK entra en el barrido del servidor",
        "lck" in leagues.ligas_de(GUILD),
        str(leagues.ligas_de(GUILD)),
    )
    check("y se le dice al usuario", "LCK" in salida, salida.replace("\n", " · ")[:110])

    print("\n6) Sin objetivo, el canal vuelve al reparto de siempre")
    res = RespuestaFalsa()
    await nc._cuerpo_subscribe(res, {"type": "soloq", "target": ""})
    check("los objetivos se van", ct.objetivos_de(GUILD, CANAL) == {})
    check("y se avisa de la vuelta", "todas las ligas" in res.todo(), res.todo()[:130])

    print("\n6b) Y sin cupo de ligas, se dice en vez de dejar el canal mudo")
    ct.poner(GUILD, CANAL, "soloq", "lec")
    plans.asignar_plan(GUILD, "gratis")   # 1 liga: la LCK ya no cabe
    res = RespuestaFalsa(canal_id=444555666)
    await nc._cuerpo_subscribe(res, {"type": "soloq", "target": "lck"})
    check(
        "el canal NO se añade a medias",
        444555666 not in channel_config.canales_de(GUILD),
        str(channel_config.canales_de(GUILD)),
    )
    check("y se explica que no cabe", "no cabe" in res.todo(), res.todo()[:130])
    plans.asignar_plan(GUILD, "pro")

    print("\n7) Un objetivo que no se reconoce no deja el canal a medias")
    antes = channel_config.canales_de(GUILD)
    res = RespuestaFalsa(canal_id=123123123)
    await nc._cuerpo_subscribe(res, {"type": "soloq", "target": "loquesea"})
    check("no se añade el canal", 123123123 not in channel_config.canales_de(GUILD))
    check("ni se guarda objetivo", ct.objetivos_de(GUILD, 123123123) == {})
    check("y se explica qué vale", "ERROR" in res.todo(), res.todo()[:110])
    check("lo que ya había no se toca", channel_config.canales_de(GUILD) == antes)

    print("\n8) `/channels` enseña lo que pidió cada canal")
    ct.poner(GUILD, CANAL, "soloq", "lck")
    res = RespuestaFalsa()
    await nc._cuerpo_channels(res)
    salida = res.todo()
    check(
        "sale el canal con su objetivo, legible",
        "SoloQ:" in salida and "lck" in salida and "→" in salida,
        salida[:150].replace("\n", " · "),
    )


async def main() -> int:
    print("=" * 74)
    print("PRUEBA DE LOS OBJETIVOS POR CANAL")
    print("=" * 74)

    probar_almacen()
    probar_filtros()
    probar_resolucion()
    await probar_comando()

    print("\n" + "=" * 74)
    if fallos:
        print(f"FALLOS ({len(fallos)}):")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("Todo correcto: cada canal recibe lo que pidió, y nada más.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

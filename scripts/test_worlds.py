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

import json
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


def prueba_carrera_del_reparador() -> None:
    """El bug que se comió Worlds justo después de añadirlo.

    `repair_file` lee el fichero de rosters al empezar, tarda minutos y lo
    guardaba al final **tal cual lo leyó**. El arranque añadió Worlds en medio y
    la reparación lo pisó con la lista de antes: el bot seguía barriendo 256
    cuentas en vez de 342, sin un solo error en el log.

    Ahora, antes de guardar, se relee y se aplican solo los PUUIDs.
    """
    print("\n=== la carrera del reparador de PUUIDs ===")
    from tracking.soloq.puuid_repair import aplicar_resoluciones

    # Lo que hay en disco cuando la reparación termina: ya trae Worlds.
    en_disco = [
        {"name": "Vladi", "league": "lec", "accounts": [
            {"riot_id": {"game_name": "Vladi", "tag_line": "EUW"}, "puuid": ""},
        ]},
        {"name": "Faker", "league": "worlds", "accounts": [
            {"riot_id": {"game_name": "Hide on bush", "tag_line": "KR1"}, "puuid": ""},
        ]},
    ]
    resueltos = {"Vladi#EUW": "puuid-vladi", "Hide on bush#KR1": "puuid-faker"}
    aplicar_resoluciones(en_disco, resueltos, [])

    ok(len(en_disco) == 2, "no se pierde el jugador que entró mientras tanto")
    ok(en_disco[1]["league"] == "worlds", "Worlds sigue en la lista")
    ok(en_disco[0]["accounts"][0]["puuid"] == "puuid-vladi", "se aplica el PUUID")
    ok(en_disco[1]["accounts"][0]["puuid"] == "puuid-faker",
       "también el del jugador que acaba de entrar")

    # Una cuenta que Riot ya no encuentra se marca, pero no se borra.
    lista = [{"name": "X", "league": "lec",
              "accounts": [{"riot_id": {"game_name": "Fantasma", "tag_line": "X"}}]}]
    aplicar_resoluciones(lista, {}, ["Fantasma#X"])
    ok(lista[0]["accounts"][0].get("stale") is True, "una cuenta perdida se marca")

    # Y una que **no se pudo consultar** (429) no se marca de nada: si se
    # marcara, se quedaría sin sondear 6 horas por un fallo pasajero. Fue el
    # motivo de que las 86 cuentas de Worlds no se barrieran.
    viva = [{"name": "Y", "league": "worlds",
             "accounts": [{"riot_id": {"game_name": "Viva", "tag_line": "1"}}]}]
    aplicar_resoluciones(viva, {}, [])
    ok(not viva[0]["accounts"][0].get("stale"),
       "una cuenta no consultada (429) no se da por perdida")


def prueba_estado_http() -> None:
    """La diferencia entre «no existe» y «no se pudo preguntar».

    El fallo real medido el 18-10-2026: `get_account_by_riot_id` devuelve `None`
    para cualquier estado que no sea 200, así que un 429 y un 404 llegaban
    iguales a quien marcaba las cuentas. Las 86 cuentas de NA de Worlds se
    quedaron `stale` —sin sondearse— por eso.
    """
    print("\n=== el estado HTTP no se puede perder ===")
    import asyncio

    from apis.riot_client import RiotClient
    from tracking.soloq.puuid_repair import _resolve

    class FakeClient:
        """Cliente de mentira: devuelve lo que se le diga por estado."""

        def __init__(self, puuid, status):
            self._puuid, self._status = puuid, status

        async def get_puuid_con_estado(self, game_name, tag_line, region="europe"):
            return self._puuid, self._status

    async def _caso(puuid, status):
        return await _resolve(FakeClient(puuid, status), "Alguien", "TAG")

    ok(asyncio.run(_caso("PUUID-DE-VUELTA", 200)) == "PUUID-DE-VUELTA",
       "un 200 devuelve el PUUID")
    ok(asyncio.run(_caso(None, 404)) is None, "un 404 es «no existe»")

    for estado in (429, 500, 503):
        try:
            asyncio.run(_caso(None, estado))
            ok(False, f"un {estado} tiene que avisar de que no se pudo preguntar")
        except Exception as exc:
            ok(type(exc).__name__ == "_SinConsultar",
               f"un {estado} lanza «no se pudo consultar», no «no existe»")

    # Y el cliente real: que el estado llegue desde `_request`.
    class FakeReq(RiotClient):
        def __init__(self, puuid, status):
            self._puuid, self._status = puuid, status

        async def _request(self, url, method_key):
            return self._status, ({"puuid": self._puuid} if self._status == 200 else None)

    c = FakeReq("PUUID", 429)
    puuid, status = asyncio.run(c.get_puuid_con_estado("Alguien", "TAG"))
    ok(status == 429 and puuid is None,
       "`get_puuid_con_estado` conserva el 429 en vez de aplastarlo a None")
    c2 = FakeReq("PUUID", 404)
    puuid, status = asyncio.run(c2.get_puuid_con_estado("Alguien", "TAG"))
    ok(status == 404, "y el 404 también")


def prueba_no_reconsultar() -> None:
    """La reparación respeta el PUUID que ya está y no lo tira por un 404.

    Medido el 18-10-2026: la reparación volvía a preguntar a Riot por **todas**
    las cuentas (~1.200, más de 6 minutos) y cada 404 acababa en `stale`, así que
    una cuenta con su PUUID perfectamente resuelto dejaba de sondearse porque la
    API no contestó en ese momento. Las 86 cuentas de NA de Worlds se quedaron
    fuera del barrido exactamente así.
    """
    print("\n=== un PUUID que ya está no se vuelve a preguntar ===")
    import asyncio
    import tempfile

    from _estado_de_prueba import estado_temporal
    from tracking.soloq.puuid_repair import repair_file

    preguntadas: list[str] = []

    class Cliente:
        """Contesta lo que se le diga, y apunta qué se le preguntó."""

        async def get_puuid_con_estado(self, gn, tl, region="europe"):
            preguntadas.append(f"{gn}#{tl}")
            if gn == "Nueva":
                return "PUUID-NUEVO", 200
            if gn == "Perdida":
                return None, 404
            return None, 429

    with estado_temporal(avisar=False) as tmp:
        ruta = tmp / "accounts.json"
        ruta.write_text(json.dumps([
            # Ya tiene PUUID: no se debe tocar ni preguntar.
            {"name": "Faker", "league": "lck", "accounts": [
                {"riot_id": {"game_name": "Hide on bush", "tag_line": "KR1"},
                 "puuid": "PUUID-BUENO"}]},
            # Sin PUUID, y Riot la conoce.
            {"name": "Nuevo", "league": "lck", "accounts": [
                {"riot_id": {"game_name": "Nueva", "tag_line": "1"}}]},
            # Sin PUUID, y Riot dice que no existe.
            {"name": "Perdida", "league": "lck", "accounts": [
                {"riot_id": {"game_name": "Perdida", "tag_line": "1"}}]},
            # Sin PUUID, y Riot no contesta (429): se queda como estaba.
            {"name": "Lenta", "league": "lck", "accounts": [
                {"riot_id": {"game_name": "Lenta", "tag_line": "1"}}]},
        ]), encoding="utf-8")

        res = asyncio.run(repair_file(Cliente(), ruta, dry_run=False))
        despues = json.loads(ruta.read_text(encoding="utf-8"))
        cuentas = [a for p in despues for a in p.get("accounts") or []]

    ok("Hide on bush#KR1" not in preguntadas,
       "una cuenta con PUUID no se pregunta (ni una sola vez)")
    ok(cuentas[0]["puuid"] == "PUUID-BUENO",
       "y el PUUID que tenía se queda como estaba")
    ok(cuentas[1].get("puuid") == "PUUID-NUEVO",
       "una cuenta sin PUUID se resuelve contra Riot")
    ok(cuentas[2].get("stale") is True,
       "y una que Riot no conoce se marca stale")
    ok(not cuentas[3].get("stale") and not cuentas[3].get("puuid"),
       "una que no se pudo consultar no se marca: se reintentará")
    ok(res.get("ya_correctas", 0) >= 1,
       "el resumen cuenta las que ya estaban bien")


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
    prueba_carrera_del_reparador()
    prueba_estado_http()
    prueba_no_reconsultar()

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

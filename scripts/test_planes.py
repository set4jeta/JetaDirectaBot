"""Comprueba que los cupos de los planes se cumplen de verdad.

Por qué existe
--------------
`plans.py` y `/premium` describían límites que **ningún camino de código leía**:
`establecer_ligas` recortaba en el límite físico para todos y
`notify_config.json` guardaba un solo canal por servidor mientras `/premium`
vendía 3 y 10. Un plan que se anuncia y no se aplica es peor que no tenerlo, así
que aquí se prueba lo que el usuario paga:

* que el cupo de ligas del plan se aplica al leer y no destruye lo guardado;
* que el cupo de canales impide añadir de más y deja quitar para hacer hueco;
* que el cupo de historial sale del plan y no de una constante;
* que bajar de plan no borra configuración y subir la recupera;
* que `notify_config.json` en el formato viejo (un entero por servidor) se sigue
  leyendo, porque el usuario ya tiene uno así en disco.

Todo se hace sobre ficheros temporales: la prueba **no puede** tocar la config
real del bot.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracking.soloq import channel_config, leagues, plans  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    if condicion:
        print(f"  OK    {etiqueta}{f' ({extra})' if extra else ''}")
    else:
        print(f"  FALLA {etiqueta}{f' ({extra})' if extra else ''}")
        fallos.append(etiqueta)


def _redirigir(tmp: str) -> None:
    """Apunta los tres módulos a ficheros dentro de `tmp`."""
    plans._CONFIG_PATH = os.path.join(tmp, "plans.json")
    leagues._CONFIG_PATH = os.path.join(tmp, "leagues.json")
    channel_config.CONFIG_PATH = os.path.join(tmp, "notify.json")


GUILD = 111222333


def prueba_cupo_ligas() -> None:
    print("\n=== cupo de ligas ===")
    ok(plans.plan_de(GUILD).codigo == "gratis", "sin registro, plan gratuito")
    ok(leagues.tope_de_ligas(GUILD) == 1, "el gratuito puede seguir 1 liga",
       str(leagues.tope_de_ligas(GUILD)))

    en_uso = leagues.establecer_ligas(GUILD, ["lec", "lck", "les", "lfl"])
    ok(en_uso == ["lec"], "pide 4 con plan gratuito y solo se usa 1", str(en_uso))
    ok(leagues.ligas_guardadas(GUILD) == ["lec", "lck", "les", "lfl"],
       "pero las 4 quedan guardadas", str(leagues.ligas_guardadas(GUILD)))
    ok(leagues.ligas_de(GUILD) == ["lec"], "y al leer sigue saliendo 1")

    plans.asignar_plan(GUILD, "pro", motivo="prueba")
    ok(leagues.tope_de_ligas(GUILD) == 3, "con Pro el tope sube a 3")
    ok(leagues.ligas_de(GUILD) == ["lec", "lck", "les"],
       "y recupera las que ya había elegido sin volver a escribirlas",
       str(leagues.ligas_de(GUILD)))

    plans.asignar_plan(GUILD, "elite", motivo="prueba")
    ok(leagues.ligas_de(GUILD) == ["lec", "lck", "les", "lfl"],
       "con Elite entran las 4")

    plans.asignar_plan(GUILD, "gratis", motivo="baja")
    ok(leagues.ligas_de(GUILD) == ["lec"], "al bajar de plan vuelve a 1")
    ok(len(leagues.ligas_guardadas(GUILD)) == 4,
       "y bajar de plan NO borra la configuración")


def prueba_tope_fisico() -> None:
    print("\n=== el tope físico manda sobre el plan ===")
    ok(plans.ELITE.ligas <= leagues.MAX_LIGAS_POR_SERVIDOR,
       "ningún plan promete más ligas que el límite de la API",
       f"elite={plans.ELITE.ligas} max={leagues.MAX_LIGAS_POR_SERVIDOR}")

    plans.asignar_plan(GUILD, "elite")
    guardadas = leagues.establecer_ligas(
        GUILD, ["lec", "lck", "lcs", "lfl", "nlc", "prm"]
    )
    ok(len(guardadas) <= leagues.MAX_LIGAS_POR_SERVIDOR,
       "pedir 6 con Elite no pasa del límite físico", str(len(guardadas)))


def prueba_ligas_en_uso() -> None:
    print("\n=== la pasada global también respeta el cupo ===")
    plans.asignar_plan(GUILD, "gratis")
    leagues.establecer_ligas(GUILD, ["lec", "lck", "les", "lfl"])
    # Otro servidor, en Pro, con ligas distintas.
    otro = 999888777
    plans.asignar_plan(otro, "pro")
    leagues.establecer_ligas(otro, ["tcl", "hll", "ebl"])

    union = leagues.ligas_en_uso()
    ok("lec" in union, "entra la liga del servidor gratuito")
    ok("lck" not in union,
       "no se descargan las ligas que un plan gratuito no puede usar", str(union))
    ok({"tcl", "hll", "ebl"} <= set(union), "entran las 3 del servidor Pro")


def prueba_cupo_canales() -> None:
    print("\n=== cupo de canales ===")
    plans.asignar_plan(GUILD, "gratis")
    r1, tope = channel_config.agregar_canal(GUILD, 1001)
    ok((r1, tope) == ("añadido", 1), "el primero entra con plan gratuito", str((r1, tope)))
    ok(channel_config.agregar_canal(GUILD, 1001)[0] == "repetido",
       "el mismo canal dos veces se detecta")
    ok(channel_config.agregar_canal(GUILD, 1002)[0] == "cupo",
       "el segundo no entra con plan gratuito")

    plans.asignar_plan(GUILD, "pro")
    ok(channel_config.agregar_canal(GUILD, 1002)[0] == "añadido",
       "con Pro sí entra el segundo")
    ok(channel_config.agregar_canal(GUILD, 1003)[0] == "añadido", "y el tercero")
    ok(channel_config.agregar_canal(GUILD, 1004)[0] == "cupo", "el cuarto ya no")

    plans.asignar_plan(GUILD, "gratis")
    ok(channel_config.canales_de(GUILD) == [1001],
       "al bajar de plan solo se usa el primero", str(channel_config.canales_de(GUILD)))
    ok(len(channel_config.canales_guardados(GUILD)) == 3,
       "pero los tres siguen guardados")
    plans.asignar_plan(GUILD, "pro")
    ok(len(channel_config.canales_de(GUILD)) == 3, "y al volver a Pro se recuperan")

    ok(channel_config.quitar_canal(GUILD, 1002) is True, "se puede quitar uno concreto")
    ok(channel_config.quitar_canal(GUILD, 1002) is False, "quitarlo dos veces devuelve False")
    ok(channel_config.canales_de(GUILD) == [1001, 1003], "y quedan los otros dos",
       str(channel_config.canales_de(GUILD)))
    ok(channel_config.quitar_todos(GUILD) == 2, "quitar todos devuelve cuántos había")
    ok(channel_config.canales_de(GUILD) == [], "y deja el servidor sin avisos")


def prueba_cupo_historial() -> None:
    print("\n=== cupo de historial ===")
    from core import historial_commands as hist

    plans.asignar_plan(GUILD, "gratis")
    ok(hist._tope_partidas(GUILD) == plans.GRATIS.historial,
       "el gratuito enseña lo que dice su plan", str(hist._tope_partidas(GUILD)))

    plans.asignar_plan(GUILD, "pro")
    ok(hist._tope_partidas(GUILD) == plans.PRO.historial,
       "con Pro sube", str(hist._tope_partidas(GUILD)))

    plans.asignar_plan(GUILD, "elite")
    ok(hist._tope_partidas(GUILD) == plans.ELITE.historial,
       "con Elite sube más", str(hist._tope_partidas(GUILD)))

    # Lo que hace que el cupo sea honesto: ningún plan promete más líneas de las
    # que caben en los 3 mensajes que manda `/historial`.
    ok(plans.ELITE.historial <= hist.TOPE_FISICO,
       "ningún plan promete más partidas de las que caben en Discord",
       f"elite={plans.ELITE.historial} tope={hist.TOPE_FISICO}")
    ok(hist._tope_partidas(None) == plans.GRATIS.historial,
       "en DM se usa el gratuito")
    ok(hist._tope_partidas("no_es_un_id") >= 1,
       "un id ilegible nunca deja el historial en 0")


def prueba_formato_viejo() -> None:
    print("\n=== formato viejo de notify_config.json ===")
    # Es literalmente lo que el usuario tiene en disco ahora mismo.
    with open(channel_config.CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump({"922599273160409108": 922599273160409111}, fh)

    plans.asignar_plan(922599273160409108, "gratis")
    leidos = channel_config.canales_de(922599273160409108)
    ok(leidos == [922599273160409111],
       "un entero suelto se lee como lista de uno", str(leidos))
    ok(channel_config.todos_los_canales() == {922599273160409108: [922599273160409111]},
       "y la pasada del tracker lo ve igual")
    ok(channel_config.load_channel_ids() == {922599273160409108: 922599273160409111},
       "la función vieja sigue devolviendo lo que devolvía")

    # La primera escritura lo deja en el formato nuevo, sin perder lo que había.
    plans.asignar_plan(922599273160409108, "pro")
    channel_config.agregar_canal(922599273160409108, 555)
    with open(channel_config.CONFIG_PATH, encoding="utf-8") as fh:
        crudo = json.load(fh)
    ok(crudo["922599273160409108"] == [922599273160409111, 555],
       "al escribir se migra a lista y se conserva el canal original", str(crudo))


def prueba_limite_no_revienta() -> None:
    print("\n=== limite() no puede tirar un aviso ===")
    ok(plans.limite(GUILD, "recurso_que_no_existe") == 0,
       "un recurso mal escrito devuelve 0 en vez de levantar")
    ok(plans.limite(None, "ligas") == plans.GRATIS.ligas,
       "sin servidor (DM) se usa el plan gratuito")
    ok(plans.plan_de("no_es_un_id").codigo == "gratis",
       "un id que no existe cae en gratuito")
    devuelto = plans.asignar_plan(GUILD, "plan_inventado")
    ok(devuelto.codigo in plans.PLANES, "asignar un plan inexistente deja el actual",
       devuelto.codigo)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _redirigir(tmp)
        prueba_cupo_ligas()
        prueba_tope_fisico()
        prueba_ligas_en_uso()
        prueba_cupo_canales()
        prueba_cupo_historial()
        prueba_formato_viejo()
        prueba_limite_no_revienta()

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()

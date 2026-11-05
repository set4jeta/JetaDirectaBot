"""El bot no puede volver a agotar el ancho de banda del hosting.

Por qué existe
--------------
El 29-09-2026 Render **suspendió el workspace** y el bot estuvo caído 3 días
40 minutos. No fue un fallo del código: Render bajó en abril de 2026 el ancho de
banda incluido en el plan Hobby **de 100 GB a 5 GB**, y el bot venía gastando
más de 5.

Lo que gastaba era esto: en cada aviso adjuntaba la foto del jugador, el logo
del equipo y el `.bat`, y **los re-subía para cada destinatario**. Un aviso a
tres servidores con dos canales cada uno son seis subidas de los mismos ~35 kB.
Discord no deduplica nada.

Esta prueba vigila las dos mitades del arreglo:

1. **Que no se vuelva a adjuntar una imagen.** Es un fallo que no da ningún
   error: el bot funciona perfectamente y solo se nota en la factura, tres
   semanas después. Por eso se comprueba aquí y no se deja a la vista.
2. **Que el contador de salida funcione**, que es lo que avisa antes de que el
   proveedor corte.

Las imágenes no cambian al pasar a URL: se sirven desde dpm.lol, que es
exactamente de donde el bot las **descargaba** para adjuntarlas. Se comprueba
que las URLs apunten ahí.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.test_i18n_embed import RANGOS, mapa, partida  # noqa: E402
from models.soloq_match import SoloQMatch  # noqa: E402
from ui.active_match_embed import create_match_embed  # noqa: E402
from ui.player_image_utils import url_imagen_jugador  # noqa: E402
from ui.team_image_utils import url_imagen_equipo  # noqa: E402
from utils import egress  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def _adjuntos(files) -> list[str]:
    """Nombres de los ficheros que se van a subir."""
    nombres = []
    for f in files or []:
        nombres.append(getattr(f, "filename", None) or str(f))
    return nombres


async def embed_de_prueba(**kw):
    match = SoloQMatch.from_riot_game_data(partida(**kw))
    n = kw.pop("jugadores", 1)
    return await create_match_embed(match, mapa(n), RANGOS, idioma="es")


# --------------------------------------------------------------------- #
# 1. Las imágenes ya no se adjuntan
# --------------------------------------------------------------------- #

def prueba_sin_adjuntos_de_imagen() -> None:
    print("\n=== las imágenes van por URL, no adjuntas ===")

    for etiqueta, kw in (("partida normal", {}), ("en carga", {"en_carga": True})):
        embed, files = asyncio.run(embed_de_prueba(**kw))
        nombres = _adjuntos(files)

        # La foto y el logo NO pueden estar en la lista de adjuntos. Este es el
        # punto entero de la prueba: si alguien vuelve a poner
        # `files.append(nextcord.File(...))` con una imagen, el bot seguirá
        # funcionando y solo se verá en la factura del hosting.
        imagenes = [n for n in nombres if n.endswith((".webp", ".png", ".jpg"))]
        ok(not imagenes, f"[{etiqueta}] no se adjunta ninguna imagen",
           ", ".join(imagenes) or "ninguna")

        # Y el `.bat` sí sigue: es único por partida (lleva la clave de cifrado)
        # y son 1,1 kB, así que no puede ser un enlace.
        #
        # Desde el 05-11-2026 se llama por el jugador, el equipo, el campeón y la
        # fecha, no `spectate_lol.bat`: en la lista de adjuntos de Discord un
        # `spectate_lol.bat` parece un ejecutable sin dueño.
        ok(len(nombres) == 1 and nombres[0].endswith(".bat"),
           f"[{etiqueta}] lo único adjunto es el .bat", ", ".join(nombres) or "nada")
        if nombres:
            ok(nombres[0] != "spectate_lol.bat",
               f"[{etiqueta}] y el nombre dice de qué partida es", nombres[0])

        # Las imágenes tienen que estar, pero como URL de dpm.lol.
        miniatura = embed.thumbnail.url if embed.thumbnail else ""
        imagen = embed.image.url if embed.image else ""
        ok(miniatura.startswith("https://dpm.lol/esport/players/"),
           f"[{etiqueta}] la foto del jugador es una URL de dpm.lol",
           miniatura or "sin miniatura")
        ok(imagen.startswith("https://dpm.lol/esport/teams/"),
           f"[{etiqueta}] el logo del equipo es una URL de dpm.lol",
           imagen or "sin imagen")


def prueba_urls() -> None:
    """Las URLs apuntan a la misma fuente de la que antes se descargaba."""
    print("\n=== las URLs son las de la fuente original ===")

    ok(url_imagen_jugador("Caps") == "https://dpm.lol/esport/players/caps.webp",
       "la foto del jugador apunta a dpm.lol", url_imagen_jugador("Caps"))

    ok(url_imagen_jugador("") == "https://dpm.lol/esport/players/nopicture.webp",
       "sin nombre cae al marcador de dpm.lol, que es una URL válida",
       url_imagen_jugador(""))
    ok(url_imagen_equipo("") is None, "sin equipo no se pone imagen")
    ok(url_imagen_equipo("G2") == "https://dpm.lol/esport/teams/G2.webp",
       "el logo apunta a dpm.lol", url_imagen_equipo("G2") or "")

    # El nombre del fichero remoto es el mismo que el de la caché local: es lo que
    # garantiza que Discord reciba exactamente la imagen que antes se subía.
    for nombre, fichero in (("Caps", "caps.webp"), ("Broken Blade", "brokenblade.webp")):
        ok(url_imagen_jugador(nombre) == f"https://dpm.lol/esport/players/{fichero}",
           f"la URL de {nombre!r} usa el fichero de dpm", url_imagen_jugador(nombre))


def prueba_foto_sin_bloquearse() -> None:
    """Un 403 **no** es un 404: si no se puede comprobar, se manda la URL igual.

    Este es el fallo del 01-11-2026. Para saber si un jugador tenía foto, el bot
    la descargaba desde Render, donde dpm contesta 403. La descarga fallaba y el
    bot mandaba `nopicture.webp`: JackieLove e Inspired salían con el muñeco
    aunque su foto existe. Solo se libraban los 62 jugadores que ya estaban en
    `assets/player_images/`, porque esos se resolvían del disco sin tocar la red.
    """
    print("\n=== sin poder comprobar la foto, se usa la URL (un 403 no es un 404) ===")
    from ui import player_image_utils as pj
    from ui import team_image_utils as teq

    estado_pj, estado_eq = dict(pj._estado), dict(teq._estado)
    bloqueado_pj, bloqueado_eq = pj._dpm_bloqueado, teq._dpm_bloqueado
    pedir_antes = pj.requests.get
    try:
        # dpm bloqueado: ni se intenta la descarga.
        pj._dpm_bloqueado = lambda: True
        teq._dpm_bloqueado = lambda: True
        pj._estado.clear()
        teq._estado.clear()

        url = pj.url_imagen_jugador("Inspired")
        ok(url == "https://dpm.lol/esport/players/inspired.webp",
           "un jugador sin caché local sale con su foto, no con el muñeco", url)
        ok(pj._estado.get("Inspired") is None,
           "el resultado es «no se pudo comprobar», no «no hay foto»",
           str(pj._estado.get("Inspired")))

        logo = teq.url_imagen_equipo("LYON")
        ok(logo == "https://dpm.lol/esport/teams/LYON.webp",
           "el logo del equipo sale aunque no esté en la caché local", logo or "None")

        # Y el 404 de verdad sí lleva al muñeco: no se trata de no usar nunca el
        # marcador, sino de no confundir «no lo sé» con «no existe».
        pj._estado["Nadie"] = False
        ok(pj.url_imagen_jugador("Nadie").endswith("/nopicture.webp"),
           "con 404 confirmado sí se usa el marcador",
           pj.url_imagen_jugador("Nadie"))
        teq._estado["NADIE"] = False
        ok(teq.url_imagen_equipo("NADIE") is None,
           "con 404 confirmado el equipo se queda sin logo")

        # Un 403 de verdad (sin bloqueo declarado) tampoco puede concluir nada.
        class _Respuesta:
            status_code = 403

        pj._dpm_bloqueado = lambda: False
        pj._estado.clear()
        pj.requests.get = lambda *a, **k: _Respuesta()
        ok(pj.url_imagen_jugador("Inspired") ==
           "https://dpm.lol/esport/players/inspired.webp",
           "un 403 en la descarga no se toma por «no hay foto»")
    finally:
        pj._estado.clear()
        pj._estado.update(estado_pj)
        teq._estado.clear()
        teq._estado.update(estado_eq)
        pj._dpm_bloqueado = bloqueado_pj
        teq._dpm_bloqueado = bloqueado_eq
        pj.requests.get = pedir_antes


# --------------------------------------------------------------------- #
# 2. El contador de salida
# --------------------------------------------------------------------- #

def prueba_contador() -> None:
    print("\n=== contador de salida ===")

    class EmbedFalso:
        def to_dict(self):
            return {"title": "x" * 1000}

    egress.reiniciar()
    e = egress.estado()
    ok(e["mb"] == 0, "arranca en cero", f"{e['mb']:.2f} MB")
    ok(e["tope_mb"] == egress.PRESUPUESTO_MB_DEFECTO,
       "el presupuesto por defecto es el de por defecto", f"{e['tope_mb']:.0f} MB")

    # El presupuesto tiene que quedar POR DEBAJO de los 5 GB de Render: el
    # margen es lo que evita la suspensión.
    ok(egress.PRESUPUESTO_MB_DEFECTO < 5000,
       "el presupuesto deja margen bajo los 5 GB del proveedor",
       f"{egress.PRESUPUESTO_MB_DEFECTO} MB")

    un_envio = egress.estimar(EmbedFalso())
    ok(un_envio > 1000, "un embed sin adjuntos se estima en bytes", f"{un_envio} B")

    # `destinatarios` multiplica: el mismo aviso a 10 personas son 10 subidas.
    egress.reiniciar()
    egress.registrar(EmbedFalso(), None, destinatarios=10)
    ok(egress.estado()["mensajes"] == 10,
       "se cuentan los destinatarios, no las partidas",
       str(egress.estado()["mensajes"]))

    egress.reiniciar()
    egress.registrar(EmbedFalso(), None, destinatarios=3)
    esperado = egress.estimar(EmbedFalso()) * 3
    ok(egress.estado()["mb"] * 1024 * 1024 == esperado,
       "los bytes acumulados son los del envío por los destinatarios")

    # Se guarda en disco: en Render el disco es efímero, pero el fichero está en
    # la lista que `core/estado_remoto` sube a GitHub, así que sobrevive.
    ok(os.path.exists(egress.RUTA), "el acumulado se escribe en disco")

    # Y sobrevive a un reinicio del proceso: se relee del disco.
    import importlib
    antes = egress.estado()["mb"]
    modulo = importlib.reload(egress)
    ok(modulo.estado()["mb"] == antes and modulo.estado()["mb"] > 0,
       "el acumulado sobrevive a reiniciar el módulo",
       f"{antes:.4f} MB antes, {modulo.estado()['mb']:.4f} MB después")


def prueba_degradacion() -> None:
    """Al agotarse el presupuesto se cae el `.bat`, nunca el aviso."""
    print("\n=== al agotarse el presupuesto, el aviso sigue saliendo ===")

    egress.reiniciar()
    ok(egress.puede_adjuntar(1100), "con presupuesto de sobra se puede adjuntar")

    # Presupuesto diminuto: se fuerza por entorno, que es como se lee en caliente.
    anterior = os.environ.get("EGRESS_PRESUPUESTO_MB")
    os.environ["EGRESS_PRESUPUESTO_MB"] = "1"
    try:
        egress.reiniciar()
        class EmbedFalso:
            def to_dict(self):
                return {"title": "x" * (2 * 1024 * 1024)}
        egress.registrar(EmbedFalso(), None)
        ok(not egress.puede_adjuntar(1100),
           "pasado el presupuesto deja de adjuntar")

        # Y el embed se sigue montando entero, sin el `.bat`.
        embed, files = asyncio.run(embed_de_prueba())
        ok(embed.title is not None, "el embed se monta igual")
        ok(not any(n.endswith(".bat") for n in _adjuntos(files)),
           "sin el .bat", ", ".join(_adjuntos(files)) or "ninguno")
        ok(any("espect" in f.name.lower() for f in embed.fields),
           "pero se sigue explicando cómo espectar")
    finally:
        if anterior is None:
            os.environ.pop("EGRESS_PRESUPUESTO_MB", None)
        else:
            os.environ["EGRESS_PRESUPUESTO_MB"] = anterior
        egress.reiniciar()


def prueba_cambio_de_mes() -> None:
    """El contador vuelve a cero al cambiar el mes, también **en caliente**.

    Antes del 01-11-2026 esto solo afectaba al número que enseña `/health`.
    Ahora la cadencia reparte el presupuesto con `total_bytes()`, así que un
    contador que no se reiniciara dejaría el barrido a 3 600 s **todo el mes
    nuevo** — el bot seguiría vivo pero ciego, que es peor que caerse.
    """
    from datetime import datetime, timezone

    print("\n=== el contador vuelve a cero al cambiar de mes ===")

    # Se parte de un disco limpio: si quedara el `egress.json` de las pruebas
    # anteriores, `_cargar()` lo releería y el cero no probaría nada.
    egress.reiniciar()
    try:
        os.remove(egress.RUTA)
    except OSError:
        pass

    # Se finge el mes viejo **en memoria**, que es como lo tiene un proceso que
    # lleva semanas corriendo. Leerlo del disco ya funcionaba; lo que fallaba
    # era la caché de `_cargar()`, y por eso se toca el atributo a propósito.
    egress._estado = {
        "mes": "2020-01", "bytes": 3 * 1024 ** 3,
        "mensajes": 10, "adjuntos": 2, "sondeo": 1024 ** 3,
    }
    egress._pendiente_sondeo = 0

    ok(egress.total_bytes() == 0,
       "lo gastado el mes viejo no cuenta en el nuevo",
       f"había {4 * 1024 ** 3 / 1048576:.0f} MB de 2020-01")
    ok(egress.estado()["mes"] == datetime.now(timezone.utc).strftime("%Y-%m"),
       "y el mes que se informa es el de verdad", egress.estado()["mes"])
    ok(egress.estado()["porcentaje_total"] == 0,
       "el porcentaje del mes nuevo también empieza en cero")

    # Y no se queda tonto: lo que se gaste ahora sí cuenta.
    egress.registrar_sondeo(1024 * 1024)
    egress.volcar_sondeo()
    ok(abs(egress.total_bytes() - 1024 * 1024) < 2,
       "y a partir de ahí vuelve a contar", f"{egress.total_bytes()} B")


def main() -> None:
    # El contador de ancho de banda vive en `egress.json`; sin esto la prueba lo
    # escribía en el de verdad, y ese fichero es justo el que el bot usa para no
    # volver a quedarse sin ancho de banda sin enterarse.
    from _estado_de_prueba import estado_temporal

    with estado_temporal():
        prueba_sin_adjuntos_de_imagen()
        prueba_urls()
        prueba_foto_sin_bloquearse()
        prueba_contador()
        prueba_degradacion()
        prueba_cambio_de_mes()

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()

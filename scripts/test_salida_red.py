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
        ok(nombres == ["spectate_lol.bat"],
           f"[{etiqueta}] lo único adjunto es el .bat", ", ".join(nombres) or "nada")

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

    # El contrato que hace que el cambio sea invisible: **la URL remota y el
    # fichero local son el mismo nombre de fichero**. Es lo que garantiza que
    # Discord reciba exactamente la imagen que antes se subía, y se comprueba
    # así —comparando los dos nombres— en vez de contra un nombre escrito a mano,
    # porque un jugador inventado no tiene foto y la comparación fallaría por el
    # motivo equivocado.
    import os as _os
    from ui.player_image_utils import get_player_image_path

    for nombre in ("Caps", "Broken Blade", "Odoamne Jr.", "Nemesis"):
        url = url_imagen_jugador(nombre)
        local = _os.path.basename(get_player_image_path(nombre))
        ok(url.endswith(local),
           f"la URL de {nombre!r} usa el mismo fichero que la caché local",
           f"{url.rsplit('/', 1)[-1]} == {local}")

    ok(url_imagen_jugador("") == "https://dpm.lol/esport/players/nopicture.webp",
       "sin nombre cae al marcador de dpm.lol, que es una URL válida",
       url_imagen_jugador(""))
    ok(url_imagen_equipo("") is None, "sin equipo no se pone imagen")
    ok(url_imagen_equipo("G2") == "https://dpm.lol/esport/teams/G2.webp",
       "el logo apunta a dpm.lol", url_imagen_equipo("G2") or "")


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
        ok("spectate_lol.bat" not in _adjuntos(files),
           "sin el .bat", ", ".join(_adjuntos(files)) or "ninguno")
        ok(any("espect" in f.name.lower() for f in embed.fields),
           "pero se sigue explicando cómo espectar")
    finally:
        if anterior is None:
            os.environ.pop("EGRESS_PRESUPUESTO_MB", None)
        else:
            os.environ["EGRESS_PRESUPUESTO_MB"] = anterior
        egress.reiniciar()


def main() -> None:
    prueba_sin_adjuntos_de_imagen()
    prueba_urls()
    prueba_contador()
    prueba_degradacion()

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()

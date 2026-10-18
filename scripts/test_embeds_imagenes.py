"""Los logos de los embeds de esports tienen que llegar en `https`.

Por qué existe
--------------
El 29-09-2026 el dueño mandó una captura del embed de un partido (Asian Games,
Chinese Taipei vs Republic of Korea): la miniatura y la imagen grande salían
**difuminadas**, y el texto perfecto.

No era un problema de Discord ni de la imagen. La API de lolesports devuelve los
logos por **`http://`**, y `http://static.lolesports.com/...` responde **301**
hacia `https`. El proxy de imágenes de Discord no sigue esa redirección, así que
se queda con el marcador de «cargando»: el recuadro borroso.

Y no hay ningún error en ninguna parte. El embed se envía bien, el log no dice
nada y solo se ve mirando el mensaje. Por eso esta prueba mira las **URLs**, que
es lo único que se puede comprobar sin abrir Discord:

- que `url_imagen` suba a `https` y no toque nada más,
- que los tres modelos que leen la API la usen,
- y que un embed sin logo se quede **sin imagen** en vez de con un hueco roto.

Uso:
    python scripts/test_embeds_imagenes.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nextcord import Embed  # noqa: E402

from esports_extension.models.live import LiveTeamMetadata  # noqa: E402
from esports_extension.models.match import TeamEventDetails, TeamSchedule  # noqa: E402
from esports_extension.services.embed_service import EmbedService  # noqa: E402
from esports_extension.utils.imagenes import url_imagen  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


#: La URL real que devolvió la API al mirar el caso del 29-09-2026.
LOGO_HTTP = "http://static.lolesports.com/teams/1704458610869_6596f892741d1355702004.png"
LOGO_HTTPS = "https://static.lolesports.com/teams/1704458610869_6596f892741d1355702004.png"


def prueba_normalizador() -> None:
    print("\n=== el normalizador ===")
    ok(url_imagen(LOGO_HTTP) == LOGO_HTTPS, "sube un logo de http a https",
       url_imagen(LOGO_HTTP)[:46] + "…")
    ok(url_imagen(LOGO_HTTPS) == LOGO_HTTPS, "y deja igual uno que ya estaba en https")
    ok(url_imagen("") == "", "una URL vacía sigue vacía")
    ok(url_imagen(None) == "", "y `None` no revienta: devuelve vacío")
    ok(url_imagen("  " + LOGO_HTTP + "  ") == LOGO_HTTPS, "quita los espacios de alrededor")
    # Solo se toca el esquema. Una ruta relativa no se inventa.
    ok(url_imagen("//static.lolesports.com/x.png") == "//static.lolesports.com/x.png",
       "no toca una URL sin esquema (adivinar rompería casos que hoy van bien)")


def prueba_modelos() -> None:
    print("\n=== los tres sitios que leen la API ===")
    schedule = TeamSchedule({"id": "1", "name": "Karmine Corp", "code": "KC",
                             "image": LOGO_HTTP})
    ok(schedule.image == LOGO_HTTPS, "TeamSchedule (calendario)")

    detalle = TeamEventDetails({"id": "2", "name": "G2", "code": "G2",
                                "image": LOGO_HTTP})
    ok(detalle.image == LOGO_HTTPS, "TeamEventDetails (detalle del partido)")

    vivo = LiveTeamMetadata({"esportsTeamId": "3", "name": "T1", "code": "T1",
                             "image": LOGO_HTTP, "participantMetadata": []})
    ok(vivo.image == LOGO_HTTPS, "LiveTeamMetadata (partido en vivo)")

    # Y el `to_dict`, porque de ahí beben la web y el estado guardado.
    ok(detalle.to_dict()["image"] == LOGO_HTTPS,
       "y el `to_dict` también, que es de donde lee la web")


def prueba_embed() -> None:
    print("\n=== el embed ===")
    embed = Embed(title="prueba")
    EmbedService._con_imagenes(embed, LOGO_HTTP, LOGO_HTTP)
    ok(embed.thumbnail.url == LOGO_HTTPS, "la miniatura sale en https")
    ok(embed.image.url == LOGO_HTTPS, "la imagen grande también")

    # El caso que hace un hueco roto: `set_image(url="")` no quita la imagen.
    vacio = Embed(title="prueba")
    EmbedService._con_imagenes(vacio, "", "")
    ok(vacio.thumbnail.url is None, "sin logo, no hay miniatura (ni un hueco roto)")
    ok(vacio.image.url is None, "sin logo, no hay imagen grande")

    # Un equipo sí y el otro no: el que tiene logo lo pone, el otro no.
    mixto = Embed(title="prueba")
    EmbedService._con_imagenes(mixto, LOGO_HTTP, "")
    ok(mixto.thumbnail.url == LOGO_HTTPS and mixto.image.url is None,
       "si solo uno tiene logo, se pone el que hay")


def prueba_info() -> None:
    print("\n=== /info sin foto ===")
    from ui.player_info_embed import crear_embed_infoplayer

    sin_foto, _ = crear_embed_infoplayer({"nombre": "Supa", "nombre_real": "David"},
                                         idioma="es")
    ok(sin_foto.thumbnail.url is None,
       "sin foto de jugador no se pone miniatura vacía")

    con_foto, _ = crear_embed_infoplayer(
        {"nombre": "Supa", "nombre_real": "David",
         "imagen_jugador": "https://dpm.lol/esport/players/supa.webp"}, idioma="es")
    ok(con_foto.thumbnail.url == "https://dpm.lol/esport/players/supa.webp",
       "con foto, se pone")


def main() -> int:
    print("=" * 74)
    print("LOS LOGOS DE LOS EMBEDS TIENEN QUE IR EN HTTPS")
    print("=" * 74)

    prueba_normalizador()
    prueba_modelos()
    prueba_embed()
    prueba_info()

    print("\n" + "=" * 74)
    if fallos:
        print(f"fallos: {len(fallos)}")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("fallos: 0")
    print("Los logos llegan en https: Discord los puede cargar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

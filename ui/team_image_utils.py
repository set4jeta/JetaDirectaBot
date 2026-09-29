import os
import requests
from PIL import Image
from io import BytesIO
from typing import Optional

TEAM_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "team_images")
os.makedirs(TEAM_IMG_DIR, exist_ok=True)

MAX_SIZE = 200  # Tamaño máximo (ancho o alto)

#: Dónde viven los logos. Igual que en las fotos de jugador, es la misma fuente
#: de la que `get_team_image_path` descarga el fichero.
BASE_EQUIPOS = "https://dpm.lol/esport/teams/"


#: Memoria del proceso: `tricode -> ¿tiene logo?`.
#:
#: Antes de esto, cada aviso llamaba a `get_team_image_path`, que descarga el
#: logo y lo **redimensiona a 200 px** — trabajo que ya no sirve para nada,
#: porque el fichero resultante no se sube a ningún sitio. Con el resultado
#: memorizado, cada equipo se comprueba como mucho una vez por arranque y el
#: resto de avisos no tocan ni la red ni la CPU. Importa porque Render da 0,1
#: CPU y esto corría dentro del bucle de avisos.
_existe: dict[str, bool] = {}


def url_imagen_equipo(team_tricode: str) -> Optional[str]:
    """La URL **pública** del logo del equipo, para que la traiga Discord.

    Mismo motivo que `player_image_utils.url_imagen_jugador`: el logo se subía a
    Discord en cada aviso y a cada destinatario, y eso es lo que agotó el ancho
    de banda de salida de Render (ver `DESPLIEGUE.md` §8).

    Devuelve `None` cuando el equipo no tiene logo, que es lo que hacía
    `get_team_image_path`, para que el embed se quede sin imagen en vez de
    apuntar a una URL rota.

    Ojo con un detalle que **no** es un problema: el fichero local estaba
    redimensionado a 200 px y el remoto es el original, más grande (500–1000 px).
    Se ve igual o mejor, porque Discord escala la imagen al hueco del embed; lo
    único que cambia es que esos bytes los sirve dpm.lol y no Render.
    """
    if not team_tricode:
        return None
    if team_tricode not in _existe:
        _existe[team_tricode] = get_team_image_path(team_tricode) is not None
    if not _existe[team_tricode]:
        return None
    return f"{BASE_EQUIPOS}{team_tricode}.webp"


def resize_image_proportionally(image: Image.Image, max_size: int) -> Image.Image:
    width, height = image.size
    if width <= max_size and height <= max_size:
        return image  # No hace falta cambiar
    ratio = min(max_size / width, max_size / height)
    new_size = (int(width * ratio), int(height * ratio))
    return image.resize(new_size, Image.Resampling.LANCZOS)

def get_team_image_path(team_tricode: str) -> Optional[str]:
    if not team_tricode:
        return None

    filename = f"{team_tricode}.webp"
    local_path = os.path.join(TEAM_IMG_DIR, filename)
    url = f"https://dpm.lol/esport/teams/{filename}"

    # Si ya existe, asegurarse que esté bien
    if os.path.exists(local_path):
        try:
            with Image.open(local_path) as img:
                img.verify()
            return local_path
        except Exception:
            print(f"[IMG] Imagen local de equipo corrupta: {filename}")
            os.remove(local_path)

    # Descargar y redimensionar
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            try:
                img = Image.open(BytesIO(resp.content)).convert("RGBA")
                img = resize_image_proportionally(img, MAX_SIZE)
                img.save(local_path, "WEBP")
                return local_path
            except Exception as e:
                print(f"[IMG] Fallo al procesar imagen del equipo {team_tricode}: {e}")
    except Exception as e:
        print(f"[IMG] Fallo al descargar logo de {team_tricode}: {e}")

    return None

"""El logo de un equipo, como URL pública para que la traiga Discord.

Mismo motivo que `ui/player_image_utils.py` para usar una URL en vez de un
adjunto: el logo se subía a Discord en cada aviso y a cada destinatario, y eso es
lo que agotó el ancho de banda de salida de Render (`DESPLIEGUE.md` §8).

Y el mismo fallo, arreglado igual
---------------------------------
Para saber si un equipo tenía logo, el bot **lo descargaba** desde Render, donde
dpm.lol contesta 403. La descarga fallaba, `get_team_image_path` devolvía `None` y
el embed salía **sin logo** aunque el equipo se supiera de sobra: `LYON.webp` y
`G2.webp` contestan 200 desde cualquier IP que no sea de datacenter.

De ahí que la comprobación tenga tres estados, y que solo el 404 lleve a «no hay
logo»:

* `True`  — hay logo (en disco, o dpm lo sirvió).
* `False` — dpm contestó **404**: de verdad no hay.
* `None`  — no se pudo comprobar (403, timeout, 5xx). Se usa la URL igualmente y
  la descarga la hace Discord, que no está bloqueado.
"""

import os
import requests
from PIL import Image
from io import BytesIO
from typing import Optional

TEAM_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "team_images")
os.makedirs(TEAM_IMG_DIR, exist_ok=True)

MAX_SIZE = 200  # Tamaño máximo (ancho o alto)

#: Dónde viven los logos. Igual que en las fotos de jugador, es la misma fuente
#: de la que se descarga el fichero.
BASE_EQUIPOS = "https://dpm.lol/esport/teams/"


#: Memoria del proceso: `tricode -> True/False/None`.
#:
#: Antes de esto, cada aviso llamaba a `get_team_image_path`, que descarga el
#: logo y lo **redimensiona a 200 px** — trabajo que ya no sirve para nada,
#: porque el fichero resultante no se sube a ningún sitio. Con el resultado
#: memorizado, cada equipo se comprueba como mucho una vez por arranque.
_estado: dict[str, Optional[bool]] = {}


def _dpm_bloqueado() -> bool:
    """¿Sabemos que dpm.lol nos contesta 403 ahora mismo? Entonces no se prueba."""
    try:
        from apis import transporte_dpm

        return transporte_dpm.bloqueado_recientemente()
    except Exception:
        return False


def _estado_logo(team_tricode: str) -> Optional[bool]:
    """Comprueba el logo **una vez por equipo y arranque**. Ver el módulo."""
    if not team_tricode:
        return False

    filename = f"{team_tricode}.webp"
    local_path = os.path.join(TEAM_IMG_DIR, filename)

    # Si ya existe, asegurarse que esté bien
    if os.path.exists(local_path):
        try:
            with Image.open(local_path) as img:
                img.verify()
            return True
        except Exception:
            print(f"[IMG] Imagen local de equipo corrupta: {filename}")
            os.remove(local_path)

    if _dpm_bloqueado():
        return None

    url = f"{BASE_EQUIPOS}{filename}"
    try:
        resp = requests.get(url, timeout=5)
    except Exception as e:
        print(f"[IMG] Fallo al descargar logo de {team_tricode}: {e}")
        return None

    if resp.status_code == 404:
        return False
    if resp.status_code != 200:
        print(f"[IMG] dpm contestó {resp.status_code} al logo {url}; no se concluye nada")
        return None

    # Descargar y redimensionar
    try:
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        img = resize_image_proportionally(img, MAX_SIZE)
        img.save(local_path, "WEBP")
        return True
    except Exception as e:
        # dpm sirvió algo, pero no una imagen que sepamos leer. No es un 404: el
        # logo puede existir y Discord sabrá qué hacer con él.
        print(f"[IMG] Fallo al procesar imagen del equipo {team_tricode}: {e}")
        return None


def url_imagen_equipo(team_tricode: str) -> Optional[str]:
    """La URL **pública** del logo del equipo, para que la traiga Discord.

    Devuelve `None` **solo** cuando dpm ha dicho que ese equipo no tiene logo
    (404) o cuando no hay equipo. Si no se pudo comprobar, devuelve la URL igual:
    quedarse sin logo por un 403 propio era el fallo, no la solución.
    """
    if not team_tricode:
        return None
    if team_tricode not in _estado:
        _estado[team_tricode] = _estado_logo(team_tricode)
    if _estado[team_tricode] is False:
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
    """La ruta **local** del logo, o `None` si no hay.

    Se conserva por compatibilidad. El embed ya no pasa por aquí: `url_imagen_equipo`
    no necesita tener el fichero en disco para saber qué URL mandar.
    """
    if not team_tricode:
        return None
    if team_tricode not in _estado:
        _estado[team_tricode] = _estado_logo(team_tricode)
    if _estado[team_tricode] is False:
        return None
    local_path = os.path.join(TEAM_IMG_DIR, f"{team_tricode}.webp")
    return local_path if os.path.exists(local_path) else None

#ui/player_image_utils.py
import os
import requests

PLAYER_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "player_images")
os.makedirs(PLAYER_IMG_DIR, exist_ok=True)

from typing import Optional

#: Dónde viven las fotos. Es la misma fuente de la que `get_player_image_path`
#: **descarga** el fichero, así que la URL y el fichero local son la misma
#: imagen: usarla directa no cambia ni un píxel de lo que se ve en Discord.
BASE_JUGADORES = "https://dpm.lol/esport/players/"
SIN_IMAGEN = "nopicture.webp"


#: Memoria del proceso: `nombre -> nombre del fichero que hay que pedir`.
#:
#: `get_player_image_path` abre el fichero y lo valida con PIL en cada llamada, y
#: eso ocurría **en cada aviso**. Con esto se resuelve una vez por jugador y
#: arranque, y el resto de avisos no tocan el disco. Importa porque Render da
#: 0,1 CPU y esto corre dentro del bucle de avisos.
_cache_url: dict[str, str] = {}


def url_imagen_jugador(player_name: str) -> str:
    """La URL **pública** de la foto del jugador, para que la traiga Discord.

    Existe para no adjuntar la imagen al aviso. Antes el bot subía el fichero a
    Discord en cada envío y **a cada destinatario**: un mismo aviso reenviado a
    tres servidores con dos canales cada uno son seis subidas de la misma foto.
    Eso agotó los 5 GB de salida del plan gratuito de Render y tumbó el bot tres
    días (ver `DESPLIEGUE.md` §8). Con una URL, los bytes los sirve dpm.lol y por
    Render solo viaja el enlace.

    Nunca devuelve una ruta local, y por eso el tipo es `str` y no `Optional`:
    un `None` aquí volvería a dejar al llamante eligiendo entre subir o no poner
    imagen, que es justo la decisión que se quiere quitar de en medio.

    Si dpm.lol no tiene foto de ese jugador se devuelve **su propio marcador de
    "sin imagen"**, que también es una URL pública: así el hueco se sigue viendo
    como antes en vez de quedarse en blanco.
    """
    if player_name not in _cache_url:
        ruta = get_player_image_path(player_name)
        # `get_player_image_path` devuelve la ruta local cuando el fichero existe,
        # y `nopicture.webp` cuando dpm.lol no tenía foto. El nombre del fichero
        # local es exactamente el de la URL remota, así que traducir es directo y
        # no hay que repetir aquí la lógica de descarga.
        _cache_url[player_name] = os.path.basename(ruta) if ruta else SIN_IMAGEN
    return f"{BASE_JUGADORES}{_cache_url[player_name]}"


def get_player_image_path(player_name: str) -> Optional[str]:
    from PIL import Image
    from io import BytesIO

    name_clean = player_name.lower().replace(" ", "").replace("'", "").replace(".", "")
    url = f"https://dpm.lol/esport/players/{name_clean}.webp"
    local_path = os.path.join(PLAYER_IMG_DIR, f"{name_clean}.webp")
    default_path = os.path.join(PLAYER_IMG_DIR, "nopicture.webp")

    # Si ya existe local y es válido, úsala
    if os.path.exists(local_path):
        try:
            with Image.open(local_path) as img:
                img.verify()  # Verifica que sea una imagen válida
            return local_path
        except Exception:
            print(f"[IMG] Imagen local corrupta o inválida: {local_path}")
            os.remove(local_path)  # Eliminar la imagen corrupta

    # Intentar descargar
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            try:
                img = Image.open(BytesIO(resp.content))
                img.verify()  # Verifica que sea imagen válida

                # Si es válida, guardarla
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                return local_path

            except Exception:
                print(f"[IMG] Imagen descargada no es válida: {url}")
    except Exception as e:
        print(f"[IMG] Error al intentar descargar imagen de {url}: {e}")

    # Si todo falla, usar la imagen por defecto
    return default_path

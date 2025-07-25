#ui/player_image_utils.py
import os
import requests

PLAYER_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "player_images")
os.makedirs(PLAYER_IMG_DIR, exist_ok=True)

from typing import Optional

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

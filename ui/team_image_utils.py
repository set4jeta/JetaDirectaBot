import os
import requests
from PIL import Image
from io import BytesIO
from typing import Optional

TEAM_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "team_images")
os.makedirs(TEAM_IMG_DIR, exist_ok=True)

MAX_SIZE = 200  # Tamaño máximo (ancho o alto)

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

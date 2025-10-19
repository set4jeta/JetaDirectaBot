import os
from io import BytesIO
from PIL import Image
import cloudscraper  # asegúrate de instalarlo con pip install cloudscraper

SAVE_DIR = "assets/player_images"
os.makedirs(SAVE_DIR, exist_ok=True)

def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).rstrip().replace(" ", "_")

def get_player_image(player_name: str, img_url: str) -> BytesIO | None:
    filename = sanitize_filename(player_name.lower()) + ".png"
    local_path = os.path.join(SAVE_DIR, filename)

    # Si ya existe localmente, cargarla
    if os.path.exists(local_path):
        try:
            with Image.open(local_path) as image:
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                buffer.seek(0)
                return buffer
        except Exception as e:
            print(f"[✗] Error leyendo imagen local '{local_path}': {e}")
            return None

    scraper = cloudscraper.create_scraper()  # Crea el scraper que simula navegador

    try:
        res = scraper.get(img_url, timeout=15)
        res.raise_for_status()

        image = Image.open(BytesIO(res.content)).convert("RGBA")
        image = image.resize((200, 200), Image.Resampling.LANCZOS)

        image.save(local_path, format="PNG")
        print(f"[✓] Imagen de '{player_name}' guardada en '{local_path}'")

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    except Exception as e:
        print(f"[✗] Error descargando imagen de '{player_name}': {e}")
        return None

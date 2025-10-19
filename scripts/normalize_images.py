#normalize_images.py
from PIL import Image
import os

# Ruta de la carpeta con las imágenes
IMAGE_DIR = "assets/normaliz"
TARGET_SIZE = (250, 250)

# Asegura que la carpeta existe
if not os.path.exists(IMAGE_DIR):
    print(f"[✗] Carpeta no encontrada: {IMAGE_DIR}")
    exit()

# Recorre los archivos
for filename in os.listdir(IMAGE_DIR):
    if filename.lower().endswith(".png"):
        path = os.path.join(IMAGE_DIR, filename)
        try:
            with Image.open(path) as img:
                img = img.convert("RGBA")  # Asegura transparencia
                img = img.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
                img.save(path)
                print(f"[✓] Redimensionada: {filename}")
        except Exception as e:
            print(f"[✗] Error con {filename}: {e}")
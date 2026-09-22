import os
import requests
from PIL import Image
from io import BytesIO
from difflib import get_close_matches

# La clave se lee de la configuración central (.env), no del código.
import config
API_KEY = config.LOL_API_KEY


HEADERS = {
    "x-api-key": API_KEY
}

SAVE_DIR = "assets/team_logos"
os.makedirs(SAVE_DIR, exist_ok=True)

def sanitize_filename(name):
    sanitized = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).rstrip().replace(" ", "_")
    print(f"[🔧] Sanitizando nombre '{name}' -> '{sanitized}'")
    return sanitized

def get_team_logo_image(team_name: str) -> BytesIO | None:
    print(f"\n[➡️] Iniciando búsqueda de logo para: '{team_name}'")

    team_name_clean = sanitize_filename(team_name.lower().strip())
    local_path = os.path.join(SAVE_DIR, f"{team_name_clean}.png")
    print(f"[🛠️] Ruta local para la imagen: {local_path}")

    # Si ya existe, cargar desde disco
    if os.path.exists(local_path):
        print(f"[💾] Cargando desde caché: {local_path}")
        try:
            with Image.open(local_path) as image:
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                buffer.seek(0)
                print(f"[✓] Imagen cargada desde disco correctamente.")
                return buffer
        except Exception as e:
            print(f"[✗] Error leyendo imagen local '{local_path}': {e}")
            return None

    print("[🌐] No existe la imagen local. Consultando API...")

    # Consultar API para obtener lista de equipos
    url = "https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US"
    try:
        res = requests.get(url, headers=HEADERS)
        print(f"[🌐] Solicitud API realizada, código HTTP: {res.status_code}")
    except Exception as e:
        print(f"[✗] Error al hacer la solicitud a la API: {e}")
        return None

    if res.status_code != 200:
        print(f"[✗] Error en la API: {res.status_code}")
        return None

    teams = res.json().get("data", {}).get("teams", [])
    print(f"[ℹ️] {len(teams)} equipos recibidos desde la API.")

    all_team_names = [t.get("name", "").strip() for t in teams]

    # Intento 1: búsqueda exacta en el campo 'name'
    team = next((t for t in teams if t.get("name", "").strip().lower() == team_name.strip().lower()), None)
    if team:
        print(f"[🔍] Coincidencia exacta encontrada para '{team_name}'")
    else:
        print(f"[⚠️] No se encontró coincidencia exacta para '{team_name}', intentando fuzzy match...")

    # Intento 2: fuzzy matching si no encontró nada
    if not team:
        closest = get_close_matches(team_name.strip(), all_team_names, n=1, cutoff=0.6)
        if closest:
            matched_name = closest[0]
            print(f"[~] Usando fuzzy match: '{team_name}' ≈ '{matched_name}'")
            team = next((t for t in teams if t.get("name", "") == matched_name), None)
        else:
            print(f"[✗] No se encontró coincidencia ni fuzzy match para '{team_name}'")
            return None

    img_url = team.get("image", "") if team else ""
    if not img_url:
        team_name_display = team.get('name', '?') if team else team_name
        print(f"[✗] El equipo '{team_name_display}' no tiene imagen.")
        return None

    try:
        print(f"[🖼️] URL de imagen recibida de la API para '{team_name}': {img_url}")
        img_res = requests.get(img_url)
        img_res.raise_for_status()

        image = Image.open(BytesIO(img_res.content)).convert("RGBA")
        print(f"[📐] Imagen descargada, tamaño original: {image.size}")

        image = image.resize((256, 256), Image.Resampling.LANCZOS)
        print(f"[📐] Imagen redimensionada a: {image.size}")

        image.save(local_path, format="PNG")
        print(f"[✓] Imagen guardada en '{local_path}'")

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    except Exception as e:
        print(f"[✗] Error procesando imagen de '{team_name}': {e}")
        return None

import os
import requests

# Carpeta base donde guardarás las imágenes
BASE_PATH = r"d:\msi_tracker_bot\assets"
PLAYERS_PATH = os.path.join(BASE_PATH, "players")
TEAMS_PATH = os.path.join(BASE_PATH, "teams")

# Asegúrate de que las carpetas existen
os.makedirs(PLAYERS_PATH, exist_ok=True)
os.makedirs(TEAMS_PATH, exist_ok=True)

# Lista única de jugadores
jugadores = [
    "Bwipo", "Quad", "Massu", "Inspired", "Busio", "Myrwn", "Supa", "Alvaro", "Elyoya", "Jojopyun",
    "Emo", "Levi", "Easylove", "Kiaya", "Elio", "Knight", "Aress", "Tatu", "Ayu", "BrokenBlade",
    "Tutsz", "JunJia", "ON", "SkewMond", "Artemis", "Gumayusi", "JoJo", "Canyon", "Duro",
    "HongQ", "Shanks", "Driver", "Labrov", "Elk", "Guigo", "Flandre", "Caps", "Kael",
    "Hans Sama", "Beichuan", "Bin", "Faker", "Ruler", "Kiin", "Rest", "Doran", "Tarzan",
    "Keria", "Chovy", "Oner", "Hope", "Doggo"
]

# Lista única de equipos por su TRICODE
equipos = [
    "FLY", "MKOI", "GAM", "BLG", "FUR", "G2", "CFO", "T1", "GENG", "AL"
]

def descargar_imagen(url, ruta_destino):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(ruta_destino, "wb") as f:
                f.write(response.content)
            print(f"✅ Descargado: {ruta_destino}")
        else:
            print(f"⚠️ Error al descargar {url} (Status {response.status_code})")
    except Exception as e:
        print(f"❌ Error al descargar {url}: {e}")

# Descargar imágenes de jugadores
for nombre in set(jugadores):
    url = f"https://dpm.lol/esport/players/{nombre}.webp"
    ruta = os.path.join(PLAYERS_PATH, f"{nombre}.webp")
    descargar_imagen(url, ruta)

# Descargar imágenes de equipos
for code in set(equipos):
    url = f"https://dpm.lol/esport/teams/{code}.webp"
    ruta = os.path.join(TEAMS_PATH, f"{code}.webp")
    descargar_imagen(url, ruta)

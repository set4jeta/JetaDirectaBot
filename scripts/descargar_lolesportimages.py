import requests
import os

# Tricodes y nombres de los equipos MSI 2025
TEAM_TRICODES = {
    "FLY": "FlyQuest",
    "G2": "G2 Esports",
    "CFO": "CTBC Flying Oyster",
    "BLG": "Bilibili Gaming",
    "GENG": "Gen.G",
    "T1": "T1",
    "MKOI": "MOVISTAR KOI",
    "FUR": "FURIA",
    "GAM": "GAM Esports",
    "AL": "Anyone's Legend",
    "CGN": "CGN Esports",
}

# Carpeta destino
SAVE_DIR = "assets/msi_images"
os.makedirs(SAVE_DIR, exist_ok=True)

# API key y headers
HEADERS = {
    "x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
}

# Endpoint con parámetro obligatorio
url = "https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US"
response = requests.get(url, headers=HEADERS)

if response.status_code != 200:
    print(f"[✗] Error en la petición: {response.status_code}")
    print(response.text)
    exit()

data = response.json()
teams = data.get("data", {}).get("teams", [])

descargadas = 0

# Hacemos copia de los códigos que faltan
faltantes = TEAM_TRICODES.copy()

for team in teams:
    code = team.get("code", "")
    name = team.get("name", "")
    img_url = team.get("image", "")

    for key, expected_name in list(faltantes.items()):
        if code.startswith(key[:3]):  # compara primeros caracteres
            if img_url:
                try:
                    img_response = requests.get(img_url)
                    if img_response.status_code == 200:
                        filename = f"{key}.png"
                        filepath = os.path.join(SAVE_DIR, filename)
                        with open(filepath, "wb") as f:
                            f.write(img_response.content)
                        print(f"[✓] Imagen descargada: {filename} ({name})")
                        descargadas += 1
                        del faltantes[key]  # ya descargado
                        break
                    else:
                        print(f"[✗] Error al descargar imagen de {code}: {img_response.status_code}")
                except Exception as e:
                    print(f"[✗] Excepción al descargar {code}: {e}")

if descargadas == 0:
    print("[!] No se descargó ninguna imagen. Verifica los códigos.")
else:
    print(f"[✓] Total de imágenes descargadas: {descargadas}")

if faltantes:
    print("[!] Equipos no encontrados o sin imagen:")
    for k, v in faltantes.items():
        print(f" - {k}: {v}")

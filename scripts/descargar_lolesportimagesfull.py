import requests
import os

# Carpeta destino
SAVE_DIR = "assets/msi_images"
os.makedirs(SAVE_DIR, exist_ok=True)

# Headers con API key
HEADERS = {
    "x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
}

# Endpoint de equipos
url = "https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US"
response = requests.get(url, headers=HEADERS)

if response.status_code != 200:
    print(f"[✗] Error en la petición: {response.status_code}")
    print(response.text)
    exit()

data = response.json()
teams = data.get("data", {}).get("teams", [])

descargadas = 0
fallidas = []

for team in teams:
    code = team.get("code", "").strip()
    name = team.get("name", "").strip()
    img_url = team.get("image", "")

    if not code:
        print(f"[✗] Equipo sin código encontrado, saltando.")
        continue

    if not img_url:
        print(f"[✗] {code} no tiene imagen, saltando.")
        fallidas.append(code)
        continue

    try:
        img_response = requests.get(img_url)
        if img_response.status_code == 200:
            filename = f"{code}.png"
            filepath = os.path.join(SAVE_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(img_response.content)
            print(f"[✓] Imagen descargada: {filename} ({name})")
            descargadas += 1
        else:
            print(f"[✗] Error al descargar imagen de {code}: {img_response.status_code}")
            fallidas.append(code)
    except Exception as e:
        print(f"[✗] Excepción al descargar {code}: {e}")
        fallidas.append(code)

# Resumen
print(f"\n[✓] Total de imágenes descargadas: {descargadas}")
if fallidas:
    print("[!] Equipos sin imagen descargada:")
    for code in fallidas:
        print(f" - {code}")
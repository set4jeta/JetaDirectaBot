import os
import json
import requests
from bs4 import BeautifulSoup
from time import sleep

BASE_URL = "https://www.trackingthepros.com"
OUTPUT_DIR = "tracking"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Ruta de salida
JSON_DATOS = os.path.join(OUTPUT_DIR, "pro_players_full.json")

# 1. Obtener todos los jugadores
endpoint = (
    "https://www.trackingthepros.com/d/list_players?"
    "filter_region=NA&draw=1&start=0&length=300"
)
print("📥 Obteniendo lista completa de jugadores...")
res = requests.get(endpoint)
data = res.json()
players = data.get("data", [])

# Diccionario de salida
datos_completos = {}

for jugador in players:
    nombre_visible = BeautifulSoup(jugador["player_name"], "html.parser").text.strip()
    slug = jugador["name"]
    perfil_url = f"{BASE_URL}/player/{slug}"
    print(f"🔎 Procesando: {nombre_visible} ({perfil_url})")

    # Guardar todos los datos base del jugador
    datos_completos[nombre_visible] = jugador

    try:
        res = requests.get(perfil_url)
        soup = BeautifulSoup(res.text, "html.parser")

        # Buscar la tabla de cuentas
        h4 = soup.find("h4", string="Accounts")
        if not h4:
            print(f"  ❌ No se encontró sección 'Accounts'")
            continue

        table = h4.find_next("table")
        if not table:
            print(f"  ❌ No se encontró tabla de cuentas para {nombre_visible}")
            continue

        cuentas_na = []

        for fila in table.find_all("tr"):  # type: ignore
            if not fila or not hasattr(fila, "text"):
                continue

            clases = fila.get("class") or []  # type: ignore

            if "[NA]" in fila.text and "inactive_account" not in clases:
                celdas = fila.find_all("td")  # type: ignore
                if not celdas:
                    continue

                texto_cuenta = celdas[0].get_text(strip=True)
                if "]" in texto_cuenta:
                    cuenta_limpia = texto_cuenta.split("]", 1)[1].strip()
                    cuentas_na.append(cuenta_limpia)

        # Añadir la lista de cuentas NA al bloque del jugador
        datos_completos[nombre_visible]["cuentas_na"] = cuentas_na
        print(f"  ✅ Cuentas NA activas: {cuentas_na}" if cuentas_na else "  ⚠️ Sin cuentas NA activas")

        sleep(0.3)

    except Exception as e:
        print(f"  ⚠️ Error procesando {nombre_visible}: {e}")

# Guardar el archivo con todo unificado
with open(JSON_DATOS, "w", encoding="utf-8") as f:
    json.dump(datos_completos, f, indent=2, ensure_ascii=False)

print("\n✅ Archivo generado:")
print(f"   • {JSON_DATOS}")

import json
import os

# Ruta relativa al archivo JSON crudo
CHAMPION_JSON_PATH = os.path.join(os.path.dirname(__file__), "champion_data_raw.json")

# Diccionario final
CHAMPION_ID_TO_NAME = {}

# Cargar JSON y construir diccionario ID → Nombre
with open(CHAMPION_JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)
    for champ_data in data["data"].values():
        champ_id = champ_data["key"]  # es un string, ej: "43"
        champ_name = champ_data["name"]  # ej: "Karma"
        CHAMPION_ID_TO_NAME[champ_id] = champ_name
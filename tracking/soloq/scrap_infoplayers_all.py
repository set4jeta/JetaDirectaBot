# scrape_all_dpm.py
import os
import json
from tracking.soloq.infoplayers_eu_dpm import guardar_datos_jugador_en_json

ACCOUNTS_PATH = "tracking/soloq/accounts.json"
ACCOUNTS_TEAMS_PATH = "tracking/soloq/accounts_from_teams.json"

def load_unique_player_names():
    seen = set()
    unique_names = []

    for path in [ACCOUNTS_PATH, ACCOUNTS_TEAMS_PATH]:
        if not os.path.exists(path):
            print(f"❌ Archivo no encontrado: {path}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            players = json.load(f)

        for player in players:
            name = player.get("name")
            if name and name not in seen:
                seen.add(name)
                unique_names.append(name)

    return unique_names

def main():
    names = load_unique_player_names()
    print(f"🔍 Total de jugadores únicos: {len(names)}")

    for name in names:
        print(f"⏳ Scrapeando {name}...")
        try:
            guardar_datos_jugador_en_json(name)
        except Exception as e:
            print(f"❌ Error con {name}: {e}")

if __name__ == "__main__":
    main()
# tracking/soloq/accounts_from_leaderboards.py

import os
import json
import cloudscraper
from collections import defaultdict
from models.bootcamp_player import BootcampPlayer, Account

ENDPOINT = "https://dpm.lol/v1/leaderboards/soloq?page={page}&platform=euw1&isPro=true"
JSON_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")

def fetch_players():
    scraper = cloudscraper.create_scraper()
    all_players = []
    page = 1
    while True:
        
        try:
            resp = scraper.get(ENDPOINT.format(page=page))
            data = resp.json()
            players = data.get("players", [])
            if not players:
                break  # No hay más jugadores
            all_players.extend(players)
            print(f"✅ Página {page}: {len(players)} jugadores")
            page += 1
        except Exception as e:
            print(f"❌ Error al parsear JSON página {page}:", e)
            break
    print(f"✅ Total jugadores obtenidos: {len(all_players)}")
    return all_players

def agrupar_por_display_name(players):
    agrupados = defaultdict(list)
    for p in players:
        nombre = p.get("displayName", p["gameName"])
        agrupados[nombre].append(p)
    return agrupados

def cargar_existentes():
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def main():
    raw_players = fetch_players()
    agrupados = agrupar_por_display_name(raw_players)
    antiguos = cargar_existentes()
    nuevos = []

    for nombre, cuentas in agrupados.items():
        player = BootcampPlayer.from_leaderboard_group(nombre, cuentas)
        previo = next((p for p in antiguos if p.get("name", "").lower() == player.name.lower()), None)
        if previo:
            print(f"🔄 Jugador actualizado/mantenido: {player.name}")
        else:
            print(f"🆕 Jugador nuevo: {player.name}")
        cuentas_nuevas = []
        for acc in player.accounts:
            if previo:
                for acc_ant in previo.get("accounts", []):
                    if (
                        acc.riot_id["game_name"].lower() == acc_ant["riot_id"]["game_name"].lower() and
                        acc.riot_id["tag_line"].lower() == acc_ant["riot_id"]["tag_line"].lower() and
                        "puuid" in acc_ant
                    ):
                        acc.puuid = acc_ant["puuid"]
            cuentas_nuevas.append(acc)
        player.accounts = cuentas_nuevas
        nuevos.append(player.to_dict())

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(nuevos, f, ensure_ascii=False, indent=2)

    print(f"✅ Se guardaron {len(nuevos)} jugadores en {JSON_PATH}")

if __name__ == "__main__":
    main()

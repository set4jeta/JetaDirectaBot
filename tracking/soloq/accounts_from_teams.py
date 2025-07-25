from models.bootcamp_player import BootcampPlayer
from utils.player_filters import TRACKED_TEAMS
import cloudscraper
from bs4 import BeautifulSoup
import os
import json
from urllib.parse import quote
EUROPE_PLATFORMS = {"EUW1", "EUN1"}
JSON_PATH = os.path.join(os.path.dirname(__file__), "accounts_from_teams.json")

scraper = cloudscraper.create_scraper(browser={'custom': 'Chrome'}, delay=10)



import time

MAX_RETRIES = 3

def safe_request(url):
    for attempt in range(MAX_RETRIES):
        try:
            scraper = cloudscraper.create_scraper(browser={'custom': 'Chrome'})
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"⚠️ Intento {attempt+1} fallido para {url}: {e}")
            time.sleep(2)
    print(f"❌ No se pudo acceder a {url} después de varios intentos.")
    return None



def load_existing_players():
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Convertir dicts a BootcampPlayer
        return [BootcampPlayer.from_dict(p) for p in raw]
    return []

def cargar_existentes_teams():
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def get_players_from_team(team):
    url_html = f"https://dpm.lol/esport/soloq/teams/{team}"
    print(f"🌐 Obteniendo HTML para equipo: {team} ({url_html})")

    try:
        response = scraper.get(url_html, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        players = set()
        name_spans = soup.find_all("span", class_="font-semibold text-bm lg:text-bxl")
        for span in name_spans:
            name = span.get_text(strip=True)
            if name:
                players.add(name)

        players_list = sorted(players)
        print(f"👥 Jugadores encontrados en {team}: {players_list}")
        return players_list
    except Exception as e:
        print(f"❌ Error obteniendo jugadores para {team}: {e}")
        return []

def get_pro_players():
    all_players = []

    for team in TRACKED_TEAMS:
        print(f"🚩 Procesando equipo: {team}")
        names = get_players_from_team(team)
        for name in names:
            url = f"https://dpm.lol/v1/pros/{quote(name)}"
            print(f"📤 Consultando API: {url}")

            response = safe_request(url)
            if response is None:
                continue  # Si falla después de los reintentos, salta al siguiente jugador

            try:
                data = response.json()
                if not data:
                    print(f"⚠️ No hay datos para {name}")
                    continue

                players_data = data.get("players")
                if not players_data:
                    print(f"⚠️ No hay 'players' en la respuesta de {name}")
                    continue

                player = BootcampPlayer.from_pro_api(name, data)
                all_players.append(player)
                print(f"✅ Jugador agregado: {name}")

            except Exception as e:
                print(f"❌ Error procesando la respuesta de {name}: {e}")
                print(f"Response: {data}")
                continue

    return all_players

def main():
    print("🚀 Iniciando recopilación de jugadores...")
    players = get_pro_players()
    antiguos = cargar_existentes_teams()
    nuevos = []

    for player in players:
        previo = next((p for p in antiguos if p.get("name", "").lower() == player.name.lower()), None)
        if previo:
            print(f"🔄 Jugador actualizado/mantenido: {player.name}")
        else:
            print(f"🆕 Jugador nuevo: {player.name}")
        cuentas_nuevas = []
        for acc in player.accounts:
            if (acc.platform or "").upper() not in EUROPE_PLATFORMS:
                continue
            puuid_mantenido = False
            if previo:
                for acc_ant in previo.get("accounts", []):
                    if (
                        acc.riot_id["game_name"].lower() == acc_ant["riot_id"]["game_name"].lower() and
                        acc.riot_id["tag_line"].lower() == acc_ant["riot_id"]["tag_line"].lower() and
                        "puuid" in acc_ant
                    ):
                        acc.puuid = acc_ant["puuid"]
                        puuid_mantenido = True
            cuentas_nuevas.append(acc)
            if puuid_mantenido:
                print(f"🔄 {player.name} | {acc.riot_id['game_name']}#{acc.riot_id['tag_line']} - PUUID mantenido")
            else:
                print(f"🆕 {player.name} | {acc.riot_id['game_name']}#{acc.riot_id['tag_line']} - PUUID nuevo o pendiente")
        player.accounts = cuentas_nuevas
        nuevos.append(player.to_dict())

    print(f"📦 Total de jugadores recopilados: {len(nuevos)}")
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(nuevos, f, ensure_ascii=False, indent=2)
    print(f"✅ Se guardaron {len(nuevos)} jugadores de equipos en {JSON_PATH}")

if __name__ == "__main__":
    main()

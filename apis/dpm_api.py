#apis/dpm_api.py
import aiohttp
import cloudscraper
import asyncio
import json
import os

# dpm_api.py

#endpoint para solicitar lista de players MSI
async def fetch_leaderboard_players():
    url = "https://dpm.lol/v1/leaderboards/custom/f1a01cf4-0352-4dac-9c6d-e8e1e44db67a"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["players"]
            return []
        
        
#Api para solicitar lista de puuids desde DPM lol        
async def get_puuid_from_dpmlol(game_name, tag_line):
    url = f"https://dpm.lol/v1/players/search?gameName={game_name}&tagLine={tag_line}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("puuid")
    return None        



async def get_match_history_from_dpmlol(puuid):
    url = f"https://dpm.lol/v1/players/{puuid}/match-history"
    def fetch():
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url)
        if resp.status_code == 200:
            return resp.json()
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch)





async def get_dpmlol_puuid(game_name, tag_line):
    url = f"https://dpm.lol/v1/players/search?gameName={game_name.replace(' ', '+')}&tagLine={tag_line}"
    def fetch():
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return data.get("puuid")
            elif isinstance(data, list) and data:
                return data[0].get("puuid")
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch)


async def get_is_live_and_updated_from_dpmlol(game_name, tag_line):
    import functools
    game_name_enc = game_name.replace(" ", "+")
    tag_line_enc = tag_line
    url = f"https://dpm.lol/v1/players/search?gameName={game_name_enc}&tagLine={tag_line_enc}"
    print(f"[DPMLOL] Consultando (cloudscraper): {url}")

    def fetch():
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url)
        print(f"[DPMLOL] Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"[DPMLOL] Respuesta: {data}")
            if isinstance(data, list):
                for player in data:
                    if (
                        player.get("gameName", "").lower() == game_name.lower()
                        and player.get("tagLine", "").lower() == tag_line.lower()
                    ):
                        print(f"[DPMLOL] Encontrado en lista: isLive={player.get('isLive')}, updatedAt={player.get('updatedAt')}")
                        return player.get("isLive", False), player.get("updatedAt", None)
                print("[DPMLOL] No encontrado en lista")
                return False, None
            print(f"[DPMLOL] Dict directo: isLive={data.get('isLive')}, updatedAt={data.get('updatedAt')}")
            is_live = data.get("isLive", False)
            updated_at = data.get("updatedAt", None)
            return is_live, updated_at
        print("[DPMLOL] Respuesta no válida o error")
        return False, None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch)




def get_rank_from_dpmlol(game_name: str, tag_line: str) -> dict:
    import cloudscraper
    import urllib.parse

    game_name_enc = urllib.parse.quote_plus(game_name)
    tag_line_enc = urllib.parse.quote_plus(tag_line)
    url = f"https://dpm.lol/v1/players/search?gameName={game_name_enc}&tagLine={tag_line_enc}"
    print(f"[DEBUG] URL DPMLOL: {url}")
    scraper = cloudscraper.create_scraper()
    resp = scraper.get(url)
    print(f"[DEBUG] Respuesta DPMLOL: {resp.text}")

    if resp.status_code == 200:
        data = resp.json()
        player = None
        if isinstance(data, list) and data:
            for p in data:
                if (p.get("gameName", "").lower() == game_name.lower() and
                    p.get("tagLine", "").lower() == tag_line.lower()):
                    player = p
                    break
            if player is None:
                player = data[0]
        elif isinstance(data, dict):
            player = data
        else:
            return {}

        # Busca el rank de SoloQ
        ranks = player.get("ranks", [])
        for rank_info in ranks:
            if rank_info.get("queue") == "RANKED_SOLO_5x5":
                return rank_info

        # Si no hay ranks, busca el campo "rank"
        if "rank" in player and player["rank"].get("tier"):
            return player["rank"]

    return {}



# --- FUNCION PARA OBTENER PICKRATES POR ROL DESDE DPM.LOL ---
async def fetch_champion_lane_pickrates(timeframe="15.14", game_mode="ranked"):
    """
    Obtiene del endpoint de dpm.lol los datos de pickrate por lane (rol) para cada campeón.
    Devuelve un dict {championName: {lane: pickrate, ...}, ...}
    """
    url = f"https://dpm.lol/v1/tierlist?tier=emerald_plus&timeframe={timeframe}&gameMode={game_mode}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                champions = data.get("champions", [])
                # Parseamos a dict simple: championName -> {lane: pickrate,...}
                pickrate_by_champ = {}
                for champ in champions:
                    name = champ.get("championName")
                    lanes_pickrate = champ.get("lanesPickrate", {})
                    # Convertir a porcentajes 0-100 para facilidad (original viene en 0-100)
                    # Confirmamos que ya está en % (ej: 99.5)
                    # Si fuera en 0-1, multiplicar por 100
                    pickrate_by_champ[name] = lanes_pickrate
                return pickrate_by_champ
            else:
                print(f"[ERROR] fetch_champion_lane_pickrates HTTP status {resp.status}")
                return None

# --- FUNCION PARA GUARDAR EL JSON EN DISCO ---
async def save_pickrate_json(filepath="champion_lane_pickrates.json", timeframe="15.14", game_mode="ranked"):
    data = await fetch_champion_lane_pickrates(timeframe, game_mode)
    if data:
        # Cargar el mapping de nombre a ID
        from cache.champion_cache import CHAMPION_ID_TO_NAME
        # Invertir el mapping: nombre -> id
        NAME_TO_ID = {v: k for k, v in CHAMPION_ID_TO_NAME.items()}
        # Reemplazar keys por ID
        data_by_id = {}
        for champ_name, pickrates in data.items():
            champ_id = NAME_TO_ID.get(champ_name)
            if champ_id:
                data_by_id[champ_id] = pickrates
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_by_id, f, ensure_ascii=False, indent=4)
        print(f"[INFO] Guardado JSON de pickrates en {filepath} (por ID)")
        return True
    else:
        print("[ERROR] No se pudo obtener datos para guardar.")
        return False
  
    
async def fetch_champion_stats(puuid):
    url = f"https://dpm.lol/v1/players/{puuid}/champions?queue=solo&currentSplit=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
    return []




#PARA RANKING

async def fetch_lec_leaderboard():
    url = "https://dpm.lol/v1/esport/soloq/leagues/lec/leaderboard"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
    return []

async def fetch_pro_leaderboard():
    url = "https://dpm.lol/v1/leaderboards/soloq?page=1&platform=euw1&isPro=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("players", [])
    return []


INFO_PLAYERS_PATH = os.path.join(os.path.dirname(__file__), "../tracking/soloq/infoplayers_eu.json")

async def fetch_infoplayers_eu():
    url = "https://www.trackingthepros.com/d/list_players?filter_region=EU&&draw=1&columns%5B0%5D%5Bdata%5D=player_name"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                players = data.get("data", [])
                with open(INFO_PLAYERS_PATH, "w", encoding="utf-8") as f:
                    json.dump(players, f, ensure_ascii=False, indent=2)
                print(f"✅ Actualizado {len(players)} jugadores en {INFO_PLAYERS_PATH}")
                return True
            else:
                print(f"[ERROR] fetch_infoplayers_eu HTTP status {resp.status}")
    return False
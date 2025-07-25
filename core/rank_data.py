#core/rank_data.py
import json
import os
import aiohttp
import time
from tracking.soloq.accounts_io import load_tracked_accounts
from utils.cache_utils import save_ranking_cache, load_puuid_cache
from apis.dpm_api import get_rank_from_dpmlol, fetch_lec_leaderboard, fetch_pro_leaderboard, fetch_champion_stats
import asyncio

RANKED_DATA_FILE = "ranked_data.json"

# Cargar datos persistentes al inicio
if os.path.exists(RANKED_DATA_FILE):
    with open(RANKED_DATA_FILE, "r") as f:
        saved_ranks = json.load(f)
else:
    saved_ranks = {}

def get_cached_rank(account):
    puuid = account.puuid
    # Siempre recarga desde disco para asegurar persistencia
    if os.path.exists(RANKED_DATA_FILE):
        with open(RANKED_DATA_FILE, "r") as f:
            saved_ranks_disk = json.load(f)
        return saved_ranks_disk.get(puuid)
    return None

import time

def save_rank_data(account):
    puuid = account.puuid
    # Solo guarda si el rank es válido
    if account.rank and account.rank.get("tier") and account.rank.get("tier") != "Desconocido":
        saved_ranks[puuid] = {
            "tier": account.rank["tier"],
            "division": account.rank["division"],
            "lp": account.rank["lp"],
            "timestamp": int(time.time())
        }
        with open(RANKED_DATA_FILE, "w") as f:
            json.dump(saved_ranks, f, indent=2)
            
            
            
            
def get_rank_from_ranked_data(puuid):
    if os.path.exists(RANKED_DATA_FILE):
        with open(RANKED_DATA_FILE, "r") as f:
            data = json.load(f)
        return data.get(puuid)
    return None



# Abreviaciones de campeones
CHAMPION_ABBR = {
    "Twisted Fate": "Twisted F",
    "Miss Fortune": "Miss F",
    "Ezreal": "Ez",
    "Katarina": "Kata",
    "Nautilus": "Nauty",
    "Dr. Mundo": "Dr.Mundo",
    "Tristana": "Trist",
    # Añade más aquí si quieres
}

def abbreviate_champion_name(champ_name):
    return CHAMPION_ABBR.get(champ_name, champ_name)





CACHE_TTL = 1800  # 30 minutos
RANKING_CACHE_FILE = "ranking_cache.json"



def build_lec_index(lec_data):
    # Indexa por (gameName.lower(), tagLine.lower())
    index = {}
    for p in lec_data:
        game = p.get("gameName", "")
        tag = p.get("tagLine", "")
        if game and tag:
            index[(game.lower(), tag.lower())] = p
    return index

def build_pro_index(pro_data):
    # Indexa por (gameName.lower(), tagLine.lower())
    index = {}
    for p in pro_data:
        game = p.get("gameName", "")
        tag = p.get("tagLine", "")
        if game and tag:
            index[(game.lower(), tag.lower())] = p
    return index









async def build_and_cache_ranking():
    players = load_tracked_accounts()
    puuid_cache = load_puuid_cache()
    now = int(time.time())

    # 1. Carga los datos de LEC y PRO leaderboard
    lec_data, pro_data = await asyncio.gather(
        fetch_lec_leaderboard(),
        fetch_pro_leaderboard()
    )

    # 2. Indexa por PUUID para lookup rápido
    lec_by_name = build_lec_index(lec_data)
    pro_by_name = build_pro_index(pro_data)

    ranking = []
    missing_players = []

    for player in players:
        main_acc = None
        puuid_riot = None
        puuid_dpmlol = None
        for acc in player.accounts:
            acc_name = acc.riot_id.get("game_name", "")
            acc_tag = acc.riot_id.get("tag_line", "")
            key = f"{acc_name}#{acc_tag}"
            puuid_dpm = puuid_cache.get(key)
            if puuid_dpm and acc.puuid:
                main_acc = acc
                puuid_riot = acc.puuid
                puuid_dpmlol = puuid_dpm
                break
        if not main_acc or not puuid_riot or not puuid_dpmlol:
            continue

        
        # --- 1. Busca en LEC leaderboard por PUUID ---
        acc_name = main_acc.riot_id.get("game_name", "").lower()
        acc_tag = main_acc.riot_id.get("tag_line", "").lower()
        lec_entry = lec_by_name.get((acc_name, acc_tag))
        if lec_entry:
            champs = lec_entry.get("mostChamps", [])[:3]
            from cache.champion_cache import CHAMPION_ID_TO_NAME
            champ_names = [
                abbreviate_champion_name(CHAMPION_ID_TO_NAME.get(str(cid), str(cid)))
                for cid in champs
            ]
            ranking.append({
                "player": lec_entry.get("displayName", player.name),
                "team": lec_entry.get("team", player.team or ""),
                "riot_id": main_acc.riot_id,
                "role": lec_entry.get("lane", player.role),
                "tier": lec_entry.get("tier", "Unranked"),
                "division": lec_entry.get("rank", ""),
                "lp": lec_entry.get("leaguePoints", 0),
                "winrate": (lec_entry["wins"] / (lec_entry["wins"] + lec_entry["losses"]) * 100) if (lec_entry["wins"] + lec_entry["losses"]) > 0 else 0,
                "kda": round(lec_entry.get("kda", 0), 2),
                "best_champions": champ_names,
                "profile_icon": main_acc.profile_icon,
                "wins": lec_entry.get("wins", 0),
                "losses": lec_entry.get("losses", 0),
                "total_games": lec_entry.get("wins", 0) + lec_entry.get("losses", 0),
            })
            continue

        
        # --- 2. Busca en PRO leaderboard por PUUID ---
        pro_entry = pro_by_name.get((acc_name, acc_tag))
        if pro_entry:
            champs = pro_entry.get("championIds", [])[:3]
            from cache.champion_cache import CHAMPION_ID_TO_NAME
            champ_names = [
                abbreviate_champion_name(CHAMPION_ID_TO_NAME.get(str(cid), str(cid)))
                for cid in champs
            ]
            rank = pro_entry.get("rank", {})
            # lane puede ser dict o string
            lane = pro_entry.get("lane")
            if isinstance(lane, dict):
                lane_value = lane.get("value", player.role)
            else:
                lane_value = lane or player.role
            ranking.append({
                "player": pro_entry.get("displayName", player.name),
                "team": pro_entry.get("team", player.team or ""),
                "riot_id": main_acc.riot_id,
                "role": lane_value,
                "tier": rank.get("tier", "Unranked"),
                "division": rank.get("rank", ""),
                "lp": rank.get("leaguePoints", 0),
                "winrate": (rank.get("wins", 0) / (rank.get("wins", 0) + rank.get("losses", 0)) * 100) if (rank.get("wins", 0) + rank.get("losses", 0)) > 0 else 0,
                "kda": round(pro_entry.get("kda", 0), 2),
                "best_champions": champ_names,
                "profile_icon": main_acc.profile_icon,
                "wins": rank.get("wins", 0),
                "losses": rank.get("losses", 0),
                "total_games": rank.get("wins", 0) + rank.get("losses", 0),
            })
            continue

        # --- 3. Si no está en ninguna, usa champion stats ---
        missing_players.append((player, main_acc, puuid_dpmlol, puuid_riot))

    # 4. Para los que faltan, consulta champion stats como antes (en paralelo)
    tasks = [fetch_champion_stats(puuid_dpmlol) for (_, _, puuid_dpmlol, _) in missing_players]
    champ_stats_list = await asyncio.gather(*tasks) if tasks else []

    for idx, (player, main_acc, puuid_dpmlol, puuid_riot) in enumerate(missing_players):
        champ_stats = champ_stats_list[idx]
        total_wins = sum(c.get("win", 0) for c in champ_stats)
        total_games = sum(c.get("gamesPlayed", 0) for c in champ_stats)
        total_kills = sum(c.get("kills", 0) * c.get("gamesPlayed", 0) for c in champ_stats)
        total_deaths = sum(c.get("deaths", 0) * c.get("gamesPlayed", 0) for c in champ_stats)
        total_assists = sum(c.get("assists", 0) * c.get("gamesPlayed", 0) for c in champ_stats)
        kda = (total_kills + total_assists) / max(1, total_deaths)
        winrate = (total_wins / total_games * 100) if total_games else 0
        best_champs = sorted(champ_stats, key=lambda c: c.get("gamesPlayed", 0), reverse=True)[:3]
    
        # --- ABREVIATURAS DE CAMPEONES ---
        best_champ_names = [
            abbreviate_champion_name(c.get("championName", "?"))
            for c in best_champs
        ]
            
        # --- BUSCA RANK EN ranked_data.json POR PUUID ---
        rank_data = get_rank_from_ranked_data(puuid_riot)
        if rank_data and rank_data.get("lp", 0) > 0:
            tier = rank_data.get("tier", "Unranked")
            division = rank_data.get("division", "")
            lp = rank_data.get("lp", 0)
        else:
            tier = "Unranked"
            division = ""
            lp = 0
    
        wins = total_wins
        losses = total_games - total_wins
    
        ranking.append({
            "player": player.name,
            "team": (player.team or "").upper(),
            "riot_id": main_acc.riot_id,
            "role": player.role,
            "tier": tier,
            "division": division,
            "lp": lp,
            "winrate": winrate,
            "kda": round(kda, 2),
            "best_champions": best_champ_names,
            "profile_icon": main_acc.profile_icon,
            "wins": wins,
            "losses": losses,
            "total_games": wins + losses,
        })
    ranking.sort(key=lambda x: x["lp"], reverse=True)
    save_ranking_cache(ranking)
    return ranking
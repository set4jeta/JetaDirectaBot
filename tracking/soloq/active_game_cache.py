# tracking/soloq/active_game_cache.py
import time

# Estructura: {puuid: {"active_game": dict, "timestamp": float, "game_length": int | None, "ranked_data_map": dict (opcional)}}
ACTIVE_GAME_CACHE = {}
ACTIVE_GAME_CACHE_BY_NAME = {}


def set_active_game(puuid, active_game, player_name=None):
    print(f"[CACHE] Actualizando caché para {puuid} a {time.time()}")
    game_length = active_game.get("gameLength")
    cache_entry = {
        "active_game": active_game,
        "timestamp": time.time(),
        "game_length": game_length if isinstance(game_length, int) else None
    }
    ACTIVE_GAME_CACHE[puuid] = cache_entry
    if player_name:
        ACTIVE_GAME_CACHE_BY_NAME[player_name.lower()] = cache_entry

def get_active_game_cache(puuid):
    return ACTIVE_GAME_CACHE.get(puuid)

def get_active_game_cache_by_name(player_name):
    return ACTIVE_GAME_CACHE_BY_NAME.get(player_name.lower())

def set_active_game_with_ranked(puuid, active_game, ranked_data_map, player_name):
    print(f"[CACHE] Actualizando caché para {puuid} a {time.time()} (con ranked)")
    game_length = active_game.get("gameLength")
    cache_entry = {
        "active_game": active_game,
        "timestamp": time.time(),
        "game_length": game_length if isinstance(game_length, int) else None,
        "ranked_data_map": ranked_data_map
    }
    ACTIVE_GAME_CACHE[puuid] = cache_entry
    ACTIVE_GAME_CACHE_BY_NAME[player_name.lower()] = cache_entry  # ✅ línea nueva

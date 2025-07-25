# core/background_tasks.py

import asyncio
from nextcord.ext import tasks
import aiohttp



from tracking.soloq.active_game_checker import ActiveGameTracker
from tracking.soloq.accounts_io import load_accounts, save_accounts
from tracking.soloq.accounts_from_leaderboard import main as update_accounts_from_leaderboards
from apis.riot_api import get_puuid_from_riot_id
from utils.cache_utils import limpiar_cache_partidas_viejas
from tracking.soloq.accounts_io import load_accounts, save_accounts, load_tracked_accounts, save_tracked_accounts

_bot_instance = None  # instancia del bot
_tracker_instance = None  # instancia del checker
_players = load_accounts()


def start_background_tasks(bot):
    global _bot_instance, _tracker_instance
    _bot_instance = bot
    _tracker_instance = ActiveGameTracker(bot)

    if not check_games_loop.is_running():
        check_games_loop.start()
 
    if not actualizar_puuids_poco_a_poco.is_running():
        actualizar_puuids_poco_a_poco.start()
    if not actualizar_accounts_diario.is_running():
        actualizar_accounts_diario.start()
    
    if not actualizar_pickrates_semanal.is_running():
        actualizar_pickrates_semanal.start() 
   
    if not actualizar_infoplayers_poco_a_poco.is_running():
        actualizar_infoplayers_poco_a_poco.start() 


@tasks.loop(seconds=60)
async def check_games_loop():
    limpiar_cache_partidas_viejas()
    if _tracker_instance:
        await _tracker_instance.run()













# Nueva lista combinada y su índice
_puuids_players_list = None
_puuids_index = 0

def build_combined_players():
    # Prioriza los de teams, luego los del leaderboard, sin duplicados por riot_id
    tracked = load_tracked_accounts()
    leaderboard = load_accounts()
    seen = set()
    combined = []
    for player in tracked + leaderboard:
        for acc in player.accounts:
            key = (acc.riot_id.get("game_name", "").lower(), acc.riot_id.get("tag_line", "").lower())
            if key not in seen:
                seen.add(key)
                combined.append((player, acc))
    return combined

@tasks.loop(seconds=60)
async def actualizar_puuids_poco_a_poco():
    global _puuids_players_list, _puuids_index

    if _puuids_players_list is None:
        _puuids_players_list = build_combined_players()
        _puuids_index = 0

    if _puuids_index >= len(_puuids_players_list):
        print("✅ Revisión de PUUIDs completada para todas las cuentas.")
        _puuids_players_list = None  # Para volver a empezar en el siguiente ciclo si quieres
        return

    player, account = _puuids_players_list[_puuids_index]
    game_name = account.riot_id.get("game_name", "")
    tag_line = account.riot_id.get("tag_line", "")

    if not game_name or not tag_line:
        _puuids_index += 1
        return

    async with aiohttp.ClientSession() as session:
        print(f"🔍 [BG] Buscando PUUID para {player.name} | {game_name}#{tag_line}...")
        puuid_real, status = await get_puuid_from_riot_id(game_name, tag_line, session)

    if puuid_real:
        if account.puuid != puuid_real:
            print(f"🟡 [BG] Actualizado: {account.puuid} → {puuid_real}")
            account.puuid = puuid_real
            # Guarda en el archivo correspondiente
            if player in load_tracked_accounts():
                save_tracked_accounts(load_tracked_accounts())
            else:
                save_accounts(load_accounts())
        else:
            print(f"✅ [BG] PUUID ya correcto")
    else:
        print(f"❌ [BG] No se pudo obtener el PUUID (status {status})")

    _puuids_index += 1
    
    
    
    
@tasks.loop(hours=24)
async def actualizar_accounts_diario():
    await asyncio.sleep(24 * 60 * 60)  # Esperar 24 horas antes de la primera ejecución
    print("🔄 Actualizando accounts.json y accounts_from_teams.json (sin PUUIDs)...")
    from tracking.soloq.accounts_from_leaderboard import main as update_accounts_from_leaderboard
    from tracking.soloq.accounts_from_teams import main as update_accounts_from_teams
    update_accounts_from_leaderboard()
    update_accounts_from_teams()
    print("✅ Descarga de cuentas completada. Los procesos de actualización de PUUIDs se encargarán del resto.")
    # Recarga _players en memoria
    global _players
    _players = load_accounts()
    print("✅ _players recargado en memoria.")


from apis.dpm_api import save_pickrate_json

@tasks.loop(hours=168)  # 168 horas = 1 semana
async def actualizar_pickrates_semanal():
    print("🔄 Actualizando champion_lane_pickrates.json desde dpm.lol...")
    await save_pickrate_json()
    print("✅ Pickrates actualizados.")    
    
    
    


from tracking.soloq.infoplayers_eu_dpm import guardar_datos_jugador_en_json
from utils.load_accounts import load_all_accounts
import os
import asyncio
from nextcord.ext import tasks

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Infoplayers"))

@tasks.loop(hours=1)
async def actualizar_infoplayers_poco_a_poco():
    cuentas = load_all_accounts()
    nombres_jugadores = set(acc["name"] for acc in cuentas)
    total = len(nombres_jugadores)

    if total == 0:
        print("[BG] No hay jugadores en las cuentas para actualizar.")
        return

    intervalo = 3600 / total

    print(f"[BG] Actualizando {total} jugadores durante 1 hora, intervalo: {intervalo:.2f} segundos")

    for i, nombre in enumerate(nombres_jugadores, start=1):
        print(f"[BG] ({i}/{total}) Actualizando datos de {nombre}...")
        guardar_datos_jugador_en_json(nombre)
        print(f"[BG] ({i}/{total}) Datos de {nombre} actualizados.")
        await asyncio.sleep(intervalo)

    print("[BG] Actualización completa de Infoplayers.")
    
    


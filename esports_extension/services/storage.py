import os
import json
import logging
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timezone
from esports_extension.utils.time_utils import get_network_time 
from esports_extension.models.tracker import TrackedMatch, TrackedStatus  #  # Ajusta si la importación es distinta

FIREBASE_JSON = "firestore_matches.json"


async def save_tracked_matches(matches: List[TrackedMatch], file_path: str) -> None:
    
    matches = await cleanup_completed_matches(matches, hours=2)
    print("Limpiando partidos completados")
    
    
    
    data = [match.to_dict() for match in matches]
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            print("Guardando partidos trackeados en", file_path)
            json.dump(data, f, indent=2, ensure_ascii=False)
    except (IOError, TypeError) as e:
        print(f"Error guardando: {str(e)}")

def load_tracked_matches(file_path: str) -> List[TrackedMatch]:
    path = Path(file_path)
    
    if not path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print("Cargando partidos trackeados desde", file_path)
        return [TrackedMatch.from_dict(item) for item in data]
    
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error cargando datos: {str(e)}")
        return []

#limpieza de partidos completados

async def cleanup_completed_matches(matches: list, hours: int = 2) -> list:
    """Devuelve una nueva lista sin partidos COMPLETED con más de X horas de antigüedad."""
    now = await get_network_time()
    cleaned = []
    for match in matches:
        # Si el match está completado y han pasado más de X horas desde last_checked, lo omite
        status = getattr(match, "status", None)
        if status == "completed" or getattr(status, "value", None) == "completed":
            last_checked = getattr(match, "last_checked", None)
            if last_checked and (now - last_checked).total_seconds() > hours * 3600:
                print(f"[🗑️] Eliminando partido completado {getattr(match, 'match_id', '')} por antigüedad")
                continue
        cleaned.append(match)
    return cleaned

# Limpieza de partidos completados en memoria
async def cleanup_completed_matches_in_memory(tracked_matches: dict, hours: int = 2):
    """Elimina partidos COMPLETED con más de X horas de antigüedad del diccionario en memoria."""
   
    now = await get_network_time()
    to_delete = []
    for match_id, tracked in tracked_matches.items():
        status = getattr(tracked, "status", None)
        if status == TrackedStatus.COMPLETED or getattr(status, "value", None) == "completed":
            last_checked = getattr(tracked, "last_checked", None)
            if last_checked and (now - last_checked).total_seconds() > hours * 3600:
                print(f"[🗑️] Eliminando partido completado {getattr(tracked, 'match_id', '')} por antigüedad (memoria)")
                to_delete.append(match_id)
    for match_id in to_delete:
        del tracked_matches[match_id]






async def format_elapsed_time(start_time: datetime, tracked_game=None) -> str:
    now = await get_network_time()
    if start_time is None or now is None:
        return "Tiempo no disponible"
    elapsed = now - start_time
    paused = 0
    if tracked_game:
        paused = tracked_game.total_paused_duration
        # Si está actualmente pausado, suma la pausa en curso
        if tracked_game.paused and tracked_game.pause_start_time:
            paused += (now - tracked_game.pause_start_time).total_seconds()
    elapsed_seconds = elapsed.total_seconds() - paused
    minutes, seconds = divmod(int(elapsed_seconds), 60)
    return f"{minutes}:{seconds:02d} minutos"



def save_notification_channel(guild_id: int, channel_id: int):
    file_path = Path(__file__).parent.parent / "config.json"
    data = {}
    if file_path.exists():
        with open(file_path, "r") as f:
            data = json.load(f)
    data[str(guild_id)] = channel_id
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Archivo config.json actualizado con {guild_id=}, {channel_id=}")
    
    
def remove_notification_channel(guild_id: int):
    file_path = Path(__file__).parent.parent / "config.json"
    if not file_path.exists():
        print(f"[REMOVE] No existe {file_path}")
        return

    with open(file_path, "r") as f:
        data = json.load(f)

    guild_id_str = str(guild_id)
    if guild_id_str in data:
        del data[guild_id_str]
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"[REMOVE] Canal de notificaciones eliminado para guild_id={guild_id}")
    else:
        print(f"[REMOVE] guild_id={guild_id} no estaba en config.json")

def load_notification_channel(guild_id: int):
    file_path = Path(__file__).parent.parent / "config.json"
    if not file_path.exists():
        return None
    with open(file_path, "r") as f:
        data = json.load(f)
    return data.get(str(guild_id))




async def save_firestore_data(game_id: str, data: dict) -> None:
    print(f"[Firestore] Guardando datos para game_id={game_id} en firestore_data.json")
    """Guarda datos de Firestore para un game_id específico"""
    try:
        all_data = {}
        file_path = "firestore_data.json"
        
        # Cargar datos existentes si el archivo existe
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        
        # Actualizar con nuevos datos
        all_data[game_id] = data
        
        # Guardar
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"[Firestore] Error guardando datos: {str(e)}")

def load_firestore_data() -> Dict[str, dict]:
    """Carga todos los datos de Firestore guardados"""
    file_path = "firestore_data.json"
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Firestore] Error cargando datos: {str(e)}")
        return {}


NOTIFIED_GAMES_FILE = "notified_games.json"

def load_notified_games():
    import os, json
    if not os.path.exists(NOTIFIED_GAMES_FILE):
        return {}
    try:
        with open(NOTIFIED_GAMES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_notified_games(data):
    import json
    with open(NOTIFIED_GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)



#logica de uso # Cargar los partidos trackeados                       #importar siempre las funciones 
#tracked_matches = load_tracked_matches("tracked_matches.json")

# ... actualizar lógica ...

# Guardar los partidos actualizados
#save_tracked_matches(tracked_matches, "tracked_matches.json")
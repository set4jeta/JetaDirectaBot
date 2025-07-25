# tracking/soloq/accounts_io.py

import json
import os
from models.bootcamp_player import BootcampPlayer

JSON_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")

_cached_players = None

def load_accounts() -> list[BootcampPlayer]:
    global _cached_players
    if os.path.exists(JSON_PATH):
        print("📂 [accounts_io] Cargando accounts.json desde disco")
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            raw_players = json.load(f)
        jugadores = [BootcampPlayer.from_dict(p) for p in raw_players]
        _cached_players = jugadores
        return jugadores
    print("⚠️ [accounts_io] accounts.json no existe, devolviendo lista vacía")
    _cached_players = []
    return []

def save_accounts(players: list[BootcampPlayer]):
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in players], f, ensure_ascii=False, indent=2)
    print(f"💾 [accounts_io] accounts.json guardado con {len(players)} jugadores")

def get_account_by_puuid(puuid: str):
    for player in load_accounts_cached():
        for acc in player.accounts:
            if acc.puuid == puuid:
                return acc
    return None

def load_accounts_cached() -> list[BootcampPlayer]:
    global _cached_players
    if _cached_players is None:
        print("🚀 [accounts_io] Cache vacía, cargando accounts.json...")
        _cached_players = load_accounts()
    else:
        print("✅ [accounts_io] Usando caché de accounts.json")
    return _cached_players

def reload_accounts():
    global _cached_players
    print("🔄 [accounts_io] Recargando accounts.json desde disco (forzando)...")
    _cached_players = load_accounts()

    

JSON_TEAMS_PATH = os.path.join(os.path.dirname(__file__), "accounts_from_teams.json")

def load_tracked_accounts() -> list[BootcampPlayer]:
    if os.path.exists(JSON_TEAMS_PATH):
        print("📂 [accounts_io] Cargando accounts_from_teams.json desde disco")
        with open(JSON_TEAMS_PATH, "r", encoding="utf-8") as f:
            raw_players = json.load(f)
        return [BootcampPlayer.from_dict(p) for p in raw_players]
    print("⚠️ [accounts_io] accounts_from_teams.json no existe, devolviendo lista vacía")
    return []
    
    
def save_tracked_accounts(players: list[BootcampPlayer]):
    from tracking.soloq.accounts_io import JSON_TEAMS_PATH
    with open(JSON_TEAMS_PATH, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in players], f, ensure_ascii=False, indent=2)    
    
    
    
    
    
    
    
    """
    
===============================================================================
📁 Módulo: accounts_io.py
📌 Descripción:
    Este módulo centraliza toda la carga y guardado de los jugadores desde
    el archivo `accounts.json`, incluyendo soporte para uso en caché.

    ✔️ Funciones:
    - load_accounts(): Carga el archivo desde disco directamente.
    - save_accounts(players): Guarda la lista de jugadores en disco.
    - get_account_by_puuid(puuid): Busca un jugador por su puuid.
    - load_accounts_cached(): Devuelve los jugadores desde caché si ya fueron
      cargados anteriormente, o los carga desde disco si es la primera vez.
    - reload_accounts(): Fuerza la recarga del archivo desde disco a caché.

    🔁 ¿Por qué usar caché?
    Si accedes muchas veces a la lista de jugadores durante un ciclo de
    verificación o notificación, no tiene sentido volver a leer el archivo
    JSON desde disco cada vez. En lugar de eso, se guarda una versión en
    memoria (_cached_players) que se reutiliza hasta que decidas recargarla.

    🧪 Ejemplo de uso típico:
    >>> players = load_accounts_cached()   # Se carga 1 vez
    >>> players_again = load_accounts_cached()  # Usará la caché
    >>> reload_accounts()  # Fuerza recarga desde disco
    >>> players_updated = load_accounts_cached()  # Se recarga otra vez

    🛑 Precaución:
    No uses `load_accounts()` directamente en partes del bot que se ejecutan
    muchas veces seguidas, para no golpear el disco constantemente.
    Usa `load_accounts_cached()` para uso frecuente, y `reload_accounts()` si
    sabes que el archivo fue actualizado y necesitas datos nuevos.

    🖨️ Prints informativos incluidos para depuración.
===============================================================================
"""

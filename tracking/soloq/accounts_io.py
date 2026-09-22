# tracking/soloq/accounts_io.py

import json
import os
from models.bootcamp_player import BootcampPlayer
from utils.logger import get_logger
from utils.safe_json import guardar_lista_json

log = get_logger("tracking.accounts_io")

JSON_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")

_cached_players = None

def load_accounts() -> list[BootcampPlayer]:
    global _cached_players
    if os.path.exists(JSON_PATH):
        log.debug("Cargando accounts.json desde disco")
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            raw_players = json.load(f)
        jugadores = [BootcampPlayer.from_dict(p) for p in raw_players]
        _cached_players = jugadores
        return jugadores
    log.warning("accounts.json no existe, devolviendo lista vacía")
    _cached_players = []
    return []

def save_accounts(players: list[BootcampPlayer]) -> bool:
    """Guarda `accounts.json` pasando por las guardas de `utils/safe_json.py`.

    Antes escribía con `open(..., "w")` directo. Son los 572 kB con los 517
    jugadores y sus PUUID de Riot: el fichero más caro de reconstruir del
    proyecto, y se truncaba antes de saber si el volcado cabía. El 03-09-2026 el
    disco se llenó y `tracked_matches.json` (que tenía el mismo defecto) acabó
    en 0 bytes.

    Delegar aquí también trae las otras dos guardas que ya existían y no se
    aplicaban a este fichero: no escribir una lista vacía y no aceptar
    encogimientos bruscos. Los dos únicos que llaman a esto
    (`update_puuids.py`, `force_update_all_tracked_puuids.py`) cargan y guardan
    la lista completa, así que un recuento menor siempre es un fallo.
    """
    return guardar_lista_json(
        JSON_PATH,
        [p.to_dict() for p in players],
        etiqueta="accounts.json",
    )

def get_account_by_puuid(puuid: str):
    for player in load_accounts_cached():
        for acc in player.accounts:
            if acc.puuid == puuid:
                return acc
    return None

def load_accounts_cached() -> list[BootcampPlayer]:
    global _cached_players
    if _cached_players is None:
        log.debug("Caché vacía, cargando accounts.json")
        _cached_players = load_accounts()
    return _cached_players

def reload_accounts():
    global _cached_players
    log.debug("Recargando accounts.json desde disco (forzado)")
    _cached_players = load_accounts()

    

JSON_TEAMS_PATH = os.path.join(os.path.dirname(__file__), "accounts_from_teams.json")

def load_tracked_accounts() -> list[BootcampPlayer]:
    if os.path.exists(JSON_TEAMS_PATH):
        log.debug("Cargando accounts_from_teams.json desde disco")
        with open(JSON_TEAMS_PATH, "r", encoding="utf-8") as f:
            raw_players = json.load(f)
        return [BootcampPlayer.from_dict(p) for p in raw_players]
    log.warning("accounts_from_teams.json no existe, devolviendo lista vacía")
    return []
    
    
def save_tracked_accounts(players: list[BootcampPlayer]) -> bool:
    """Igual que `save_accounts`, para `accounts_from_teams.json`.

    Este es el fichero que lee el tracker de partidas en cada pasada, así que
    escribirlo vacío deja el bot mudo sin ningún síntoma visible.
    """
    return guardar_lista_json(
        JSON_TEAMS_PATH,
        [p.to_dict() for p in players],
        etiqueta="accounts_from_teams.json",
    )
    
    
    
    
    
    
    
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

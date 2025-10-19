import os
import json

# Defino el path absoluto a la carpeta tracking/soloq (desde la carpeta utils)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tracking", "soloq"))

def load_json_file(filename):
    ruta = os.path.join(BASE_DIR, filename)
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)

def load_accounts_from_teams():
    return load_json_file("accounts_from_teams.json")

def load_accounts():
    return load_json_file("accounts.json")

def load_all_accounts():
    """Devuelve una lista unificada de todos los players y sus cuentas de ambos archivos"""

    accounts_from_teams = load_accounts_from_teams()
    accounts = load_accounts()

    jugadores_unificados = {}

    # Primero agregamos todos los players de accounts_from_teams (prioridad)
    for player in accounts_from_teams:
        nombre_norm = player.get("name", "").lower()
        jugadores_unificados[nombre_norm] = player

    # Ahora agregamos los players de accounts.json que no estén ya incluidos
    for player in accounts:
        nombre_norm = player.get("name", "").lower()
        if nombre_norm not in jugadores_unificados:
            jugadores_unificados[nombre_norm] = player

    # Retornamos la lista unificada
    return list(jugadores_unificados.values())

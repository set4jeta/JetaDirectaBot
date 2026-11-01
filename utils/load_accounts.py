import os
import json

# Defino el path absoluto a la carpeta tracking/soloq (desde la carpeta utils)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tracking", "soloq"))

def load_json_file(filename):
    ruta = os.path.join(BASE_DIR, filename)
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)

def load_accounts_from_teams():
    try:
        return load_json_file("accounts_from_teams.json")
    except FileNotFoundError:
        # **La copia del censo, en la misma forma larga.** Sin esto, con dpm.lol
        # bloqueado el arranque decía «0 jugadores: el bot no está vigilando a
        # nadie» mientras el tracker sí tenía 1 007 con los que trabajar: el
        # mismo síntoma de avería para dos estados muy distintos.
        from tracking.soloq import censo

        return censo.leer()

def load_accounts():
    try:
        return load_json_file("accounts.json")
    except FileNotFoundError:
        # Es un fichero **generado** (lo escribe la escalera de pros). Que no
        # esté no es una avería, y antes tumbaba el recuento del arranque
        # entero por una excepción.
        return []

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

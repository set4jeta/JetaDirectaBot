import os
import json
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INFOPLAYERS_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "Infoplayers"))

def normalizar(texto: str):
    if not texto:
        return ""
    texto = texto.lower().replace(" ", "")
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")

def load_json_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)

def load_accounts_from_teams():
    return load_json_file(os.path.join(BASE_DIR, "accounts_from_teams.json"))

def load_accounts():
    return load_json_file(os.path.join(BASE_DIR, "accounts.json"))

def buscar_archivo_jugador(nombre_jugador: str):
    """Busca el archivo JSON correspondiente al jugador normalizado comparando todos los archivos"""
    nombre_norm = normalizar(nombre_jugador)

    for archivo in os.listdir(INFOPLAYERS_DIR):
        if archivo.endswith(".json"):
            nombre_archivo = os.path.splitext(archivo)[0]
            if normalizar(nombre_archivo) == nombre_norm:
                ruta = os.path.join(INFOPLAYERS_DIR, archivo)
                return load_json_file(ruta)

    return None

def merge_player_data(info_jugador: dict, extra_data: dict) -> dict:
    if not extra_data:
        return info_jugador
    merged = info_jugador.copy()

    # Solo agrega "birthdate" si falta en info_jugador
    if "birthdate" in extra_data and not merged["info_jugador"].get("birthdate"):
        merged["info_jugador"]["birthdate"] = extra_data["birthdate"]
    return merged

def mapear_region(region_cruda):
    """Convierte códigos como EUW1 a EUW, NA1 a NA, etc."""
    if not region_cruda:
        return "Otra"
    region_cruda = region_cruda.upper()
    if region_cruda.startswith("EUW"):
        return "EUW"
    elif region_cruda.startswith("NA"):
        return "NA"
    elif region_cruda.startswith("KR"):
        return "KR"
    elif region_cruda.startswith("EUNE"):
        return "EUNE"
    else:
        return "Otra"

def buscar_jugador_o_cuenta(nombre: str):
    nombre_norm = normalizar(nombre)
    accounts_from_teams = load_accounts_from_teams()
    accounts = load_accounts()

    # 1. Buscar JSON individual en Infoplayers/
    jugador_data = buscar_archivo_jugador(nombre)
    if jugador_data:
        cuentas = jugador_data.get("cuentas", [])
        for cuenta in cuentas:
            region_raw = cuenta.get("region") or cuenta.get("platform")
            cuenta["region"] = mapear_region(region_raw)

        # Buscar "birthdate" en accounts_from_teams para agregarlo si falta
        extra = next((e for e in accounts_from_teams if normalizar(e.get("name")) == nombre_norm), None)
        if extra:
            jugador_data = merge_player_data(jugador_data, extra)

        return {
            "jugador": jugador_data.get("info_jugador", {}),
            "cuentas": cuentas,
            "campeones_recientes": jugador_data.get("campeones_recientes", []),
            "estadisticas_2_semanas": jugador_data.get("estadisticas_2_semanas", {})
        }

    # 2. Si no hay archivo en Infoplayers, fallback a buscar por cuentas en accounts_from_teams
    for ent in accounts_from_teams:
        for acc in ent.get("accounts", []):
            riot_id = acc.get("riot_id", {})
            if normalizar(riot_id.get("game_name")) == nombre_norm:
                ent["region"] = "EUW"  # Sabemos que viene de accounts_from_teams => EUW
                return {"jugador": ent, "cuentas": ent.get("accounts", [])}

    return None

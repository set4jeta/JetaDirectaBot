#utils\cache_utils.py
import os
import json
import time
from tracking.soloq.active_game_cache import ACTIVE_GAME_CACHE, olvidar
from apis.dpm_api import get_dpmlol_puuid
from utils.safe_json import guardar_json_atomico

# Ninguna partida de LoL dura hora y media. Pasado esto, la entrada es de una
# partida que ya terminó y el tracker no llegó a limpiarla (por ejemplo porque
# la cuenta se marcó `stale` mientras jugaba).
MAX_CACHE_AGE = 90 * 60


def limpiar_cache_partidas_viejas():
    """Quita de la caché las partidas que ya no pueden estar en curso.

    El cálculo usa `utils.game_clock`, igual que `!live`: antes se sumaba
    `game_length` (el reloj del espectador, ~3 min retrasado) al tiempo que
    llevaba guardada la entrada, lo que subestimaba la duración real y retrasaba
    la limpieza.
    """
    from utils.game_clock import desde_cache

    ahora = time.time()
    caducadas = [
        puuid
        for puuid, entrada in list(ACTIVE_GAME_CACHE.items())
        if desde_cache(entrada, ahora).transcurrido > MAX_CACHE_AGE
    ]
    for puuid in caducadas:
        olvidar(puuid)
    return len(caducadas)

RANKING_CACHE_PATH = os.path.join("tracking", "ranking_cache.json")
RANKING_CACHE_TTL = 1800  # 30 minutos


def _ruta_ranking(liga: str | None = None) -> str:
    """Un fichero de caché por liga.

    Antes había uno solo. Al añadir `!ranking lck`, el resultado de una liga
    sobrescribía el de otra y el TTL de 30 minutos servía datos de la liga
    equivocada.
    """
    if not liga or liga == "lec":
        return RANKING_CACHE_PATH
    return os.path.join("tracking", f"ranking_cache_{liga}.json")


def load_ranking_cache(liga: str | None = None):
    ruta = _ruta_ranking(liga)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - data.get("timestamp", 0) < RANKING_CACHE_TTL:
        return data.get("ranking")
    return None


def save_ranking_cache(ranking, liga: str | None = None):
    ruta = _ruta_ranking(liga)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = f"{ruta}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"timestamp": time.time(), "ranking": ranking}, f,
                  ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)

HISTORIAL_CACHE_PATH = os.path.join("tracking", "historial_cache.json")

def load_historial_cache():
    if os.path.exists(HISTORIAL_CACHE_PATH):
        try:
            with open(HISTORIAL_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            # Es una caché: reconstruirla cuesta una llamada a la API, mientras
            # que propagar el error rompe `/historial` entero.
            return {}
    return {}

def save_historial_cache(cache):
    guardar_json_atomico(HISTORIAL_CACHE_PATH, cache, etiqueta="historial_cache")
        
        
        


PUUID_CACHE_FILE = "puuid_cache.json"

def load_puuid_cache():
    if os.path.isfile(PUUID_CACHE_FILE):
        try:
            with open(PUUID_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}

def save_puuid_cache(cache):
    # 64 kB de PUUID de dpm.lol ya resueltos: recuperable, pero cada entrada
    # perdida es una petición más a una fuente que responde 403 a `aiohttp`.
    guardar_json_atomico(PUUID_CACHE_FILE, cache, etiqueta="puuid_cache")




async def get_puuid_cached(game_name, tag_line, puuid_cache):
    key = f"{game_name}#{tag_line}"
    puuid = puuid_cache.get(key)

    # Si no hay puuid en cache o es None o cadena vacía, actualizar consultando API
    if not puuid:
        puuid = await get_dpmlol_puuid(game_name, tag_line)
        if puuid:
            puuid_cache[key] = puuid
            save_puuid_cache(puuid_cache)
        else:
            # Si no pudo obtener puuid, aseguramos que no quede cache inválida
            if key in puuid_cache:
                del puuid_cache[key]
                save_puuid_cache(puuid_cache)
    return puuid           


def formatear_fecha(fecha_iso):
    if not fecha_iso:
        return "Desconocido"
    return fecha_iso.split("T")[0]
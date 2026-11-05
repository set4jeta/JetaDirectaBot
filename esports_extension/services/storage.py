import os
import json
import logging
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timezone
from esports_extension.utils.time_utils import get_network_time 
from esports_extension.models.tracker import TrackedMatch, TrackedStatus  #  # Ajusta si la importación es distinta
from utils.logger import get_logger

log = get_logger("esports.storage")




async def save_tracked_matches(matches: List[TrackedMatch], file_path: str) -> None:
    """Guarda los partidos seguidos de forma atómica.

    Se escribe en `<fichero>.tmp` y se hace `os.replace` en vez de abrir el
    destino en modo `"w"`. Motivo medido, no teórico: abrir en `"w"` **trunca el
    fichero antes** de saber si el volcado cabe. El 03-09-2026 el disco se
    quedó sin espacio y `tracked_matches.json` acabó en 0 bytes con los 25 kB de
    partidos seguidos perdidos (se recuperaron de git). Con `os.replace` el
    fichero anterior sigue intacto si la escritura falla.

    El mismo patrón está en `utils/safe_json.py` y en
    `apis/dpm_api.fetch_infoplayers_eu`.
    """
    matches = await cleanup_completed_matches(matches, hours=2)
    log.debug("Limpiando partidos completados")

    data = [match.to_dict() for match in matches]
    tmp = f"{file_path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            log.debug("Guardando partidos trackeados en %s", file_path)
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, file_path)
    except (IOError, OSError, TypeError) as e:
        log.error("Error guardando %s: %s. Se conserva el fichero anterior.", file_path, e)
        try:
            os.remove(tmp)
        except OSError:
            pass

def load_tracked_matches(file_path: str) -> List[TrackedMatch]:
    path = Path(file_path)
    
    if not path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            log.debug("Cargando partidos trackeados desde %s", file_path)
        return [TrackedMatch.from_dict(item) for item in data]

    except (json.JSONDecodeError, KeyError, OSError, TypeError) as e:
        # Un fichero de 0 bytes o corrupto no puede impedir que el tracker
        # arranque: los partidos se vuelven a descubrir en la siguiente pasada
        # de `getSchedule`. `OSError` se incluye porque un disco lleno también
        # rompe la lectura, no solo la escritura.
        log.error("Error cargando %s: %s. Se empieza sin partidos seguidos.", file_path, e)
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
                log.info(f"Eliminando partido completado {getattr(match, 'match_id', '')} por antigüedad")
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
                log.info(f"Eliminando partido completado {getattr(tracked, 'match_id', '')} por antigüedad (memoria)")
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



#: Dónde vive la configuración de canales de partidos oficiales.
#:
#: Es una **constante** y no algo que `_ruta_config()` calcule cada vez porque
#: las pruebas de estado la redirigen a un temporal igual que hacen con
#: `notify_config.json` o `channel_targets.json`. Con la ruta escondida dentro de
#: una función no había forma de apuntarla a otro sitio, y una prueba que escribe
#: aquí deja el canal de esports de un servidor de mentira en el fichero real.
CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _ruta_config() -> Path:
    return CONFIG_PATH


def _leer_config() -> dict:
    """`{guild_id: [channel_id, ...]}` de los canales de partidos oficiales.

    Devuelve `{}` si el fichero no se puede leer. Se lee desde `/canales` y
    desde el resumen de arranque, así que un JSON corrupto propagando la
    excepción tumbaría los dos.
    """
    ruta = _ruta_config()
    if not ruta.exists():
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.error("%s ilegible (%s); se trata como vacío.", ruta, exc)
        return {}
    return datos if isinstance(datos, dict) else {}


def _escribir_config(data: dict) -> bool:
    """Vuelca la configuración de canales de forma atómica.

    Esto **no** es una caché: es la respuesta a "¿dónde aviso de los partidos?".
    Si se pierde, cada servidor tiene que volver a ejecutar
    `/setlivechannel` y nadie se enterará hasta que eche de menos un aviso. Por
    eso se escribe en `.tmp` y se sustituye, en vez de truncar el destino de
    entrada.
    """
    ruta = _ruta_config()
    tmp = ruta.with_name(ruta.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp, ruta)
        return True
    except OSError as exc:
        log.error("No se pudo guardar %s: %s. Se conserva el anterior.", ruta, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _canales_de(datos: dict, guild_id) -> list[int]:
    """Los canales de un servidor, aceptando el formato viejo.

    Hasta el 05-11-2026 se guardaba **un** id por servidor
    (`{"123": 456}`). Ahora es una lista (`{"123": [456, 789]}`) porque un
    servidor puede querer los partidos de Worlds en un canal y los de la LEC en
    otro, y con un solo hueco el segundo `/subscribe` se llevaba el canal del
    primero sin decirlo. El formato viejo se sigue leyendo: no hay migración que
    hacer ni fichero que reescribir al arrancar.
    """
    valor = datos.get(str(guild_id))
    if isinstance(valor, bool):
        return []
    if isinstance(valor, int):
        return [valor]
    if isinstance(valor, list):
        salida: list[int] = []
        for elemento in valor:
            try:
                salida.append(int(elemento))
            except (TypeError, ValueError):
                continue
        return salida
    return []


def canales_esports(guild_id) -> list[int]:
    """Los canales que reciben partidos oficiales en este servidor."""
    return _canales_de(_leer_config(), guild_id)


def agregar_canal_esports(guild_id, channel_id) -> bool:
    """Mete el canal en la lista. `False` si ya estaba o no se pudo guardar."""
    datos = _leer_config()
    canales = _canales_de(datos, guild_id)
    if int(channel_id) in canales:
        return False
    canales.append(int(channel_id))
    datos[str(guild_id)] = canales
    if _escribir_config(datos):
        log.debug("config.json: %s recibe partidos en %s", guild_id, channel_id)
        return True
    return False


def quitar_canal_esports(guild_id, channel_id) -> bool:
    """Saca el canal de la lista. `False` si no estaba."""
    datos = _leer_config()
    canales = _canales_de(datos, guild_id)
    if int(channel_id) not in canales:
        return False
    canales = [c for c in canales if c != int(channel_id)]
    if canales:
        datos[str(guild_id)] = canales
    else:
        datos.pop(str(guild_id), None)
    if _escribir_config(datos):
        log.debug("config.json: %s deja de recibir en %s", guild_id, channel_id)
        return True
    return False


def quitar_todos_esports(guild_id) -> bool:
    """Apaga los partidos oficiales en todo el servidor. `False` si no había."""
    datos = _leer_config()
    if str(guild_id) not in datos:
        return False
    del datos[str(guild_id)]
    if _escribir_config(datos):
        log.debug("config.json: %s sin canales de partidos", guild_id)
        return True
    return False








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
    """Vuelca `notified_games.json` de forma atómica.

    Mismo motivo que en `save_tracked_matches`: `open(..., "w")` trunca antes de
    saber si el volcado cabe, y este fichero es el que evita anunciar dos veces
    el mismo partido. Perderlo no rompe el bot, pero duplica avisos en todos los
    canales, que es justo lo que se ve desde fuera.
    """
    import json
    tmp = NOTIFIED_GAMES_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, NOTIFIED_GAMES_FILE)
    except OSError as e:
        log.error(
            "No se pudo guardar %s: %s. Se conserva el anterior.",
            NOTIFIED_GAMES_FILE, e,
        )
        try:
            os.remove(tmp)
        except OSError:
            pass



#logica de uso # Cargar los partidos trackeados                       #importar siempre las funciones 
#tracked_matches = load_tracked_matches("tracked_matches.json")

# ... actualizar lógica ...

# Guardar los partidos actualizados
#save_tracked_matches(tracked_matches, "tracked_matches.json")
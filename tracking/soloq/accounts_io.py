# tracking/soloq/accounts_io.py

import json
import os
from models.bootcamp_player import BootcampPlayer
from utils.logger import get_logger
from utils.safe_json import guardar_lista_json

log = get_logger("tracking.accounts_io")

JSON_PATH = os.path.join(os.path.dirname(__file__), "accounts.json")

_cached_players = None

#: Caché del fichero de rosters: `(mtime, jugadores)`.
_tracked_cache: tuple[float, list[BootcampPlayer]] | None = None

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
    """Jugadores del fichero de rosters, con caché por fecha del fichero.

    Antes se volvía a parsear en **cada** llamada: 2,5 MB y 908 objetos con sus
    cuentas, unos 50 ms en un PC normal y bastante más en un plan de 0,1 CPU. Y
    hay 16 sitios que lo llaman, varios dentro del mismo comando: `/track lck` lo
    pedía cuatro veces seguidas.

    La caché es por `mtime`, no por tiempo: el fichero se relee **solo cuando
    cambia de verdad**, así que quien acaba de escribir (los refrescos de rosters)
    ve el dato nuevo y quien solo lee no paga el parseo. Es el mismo criterio que
    usa `load_accounts_cached` con `accounts.json`.
    """
    global _tracked_cache

    try:
        mtime = os.path.getmtime(JSON_TEAMS_PATH)
    except OSError:
        log.warning("accounts_from_teams.json no existe, devolviendo lista vacía")
        return []

    if _tracked_cache is not None and _tracked_cache[0] == mtime:
        return _tracked_cache[1]

    log.debug("Cargando accounts_from_teams.json desde disco")
    try:
        with open(JSON_TEAMS_PATH, "r", encoding="utf-8") as f:
            raw_players = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        # Un JSON a medias (una escritura en curso, un corte del contenedor) **no
        # puede tumbar la pasada del tracker**: se devuelve lo último bueno que se
        # leyó, y si no hay nada, una lista vacía. Pasó de verdad el 22-09-2026:
        # dos tareas escribían el mismo fichero y la pasada moría con
        # "Fallo en la pasada de partidas". La causa está arreglada en
        # `utils/safe_json` (candado por ruta); esto es el cinturón.
        log.error("accounts_from_teams.json ilegible (%s); se usa lo último bueno.", exc)
        return _tracked_cache[1] if _tracked_cache else []

    jugadores = [BootcampPlayer.from_dict(p) for p in raw_players]
    _tracked_cache = (mtime, jugadores)
    return jugadores
    
    
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


# ---------------------------------------------------------------------- #
# Cuentas sueltas: las que alguien pidió seguir a mano
# ---------------------------------------------------------------------- #

#: Fichero propio, y el motivo importa: `accounts_from_teams.json` lo
#: **regeneran** las tareas de rosters (una liga por hora, y el refresco diario),
#: así que una cuenta que no pertenece a ningún roster —la de un streamer, un
#: smurf— desaparecería en el primer refresco. Aquí no la toca nadie.
JSON_SUELTAS_PATH = os.path.join(os.path.dirname(__file__), "cuentas_sueltas.json")


def load_cuentas_sueltas() -> list[BootcampPlayer]:
    """Cuentas seguidas una a una (`/track Nombre#TAG`).

    Se devuelven como `BootcampPlayer` para que la pasada las trate igual que a
    las del catálogo: el tracker no tiene que saber de dónde sale cada cuenta.
    Un fichero ilegible no puede tumbar la pasada, así que se sigue sin ellas.
    """
    if not os.path.exists(JSON_SUELTAS_PATH):
        return []
    try:
        with open(JSON_SUELTAS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("cuentas_sueltas.json ilegible (%s): se sigue sin ellas", exc)
        return []
    if not isinstance(raw, list):
        return []
    return [BootcampPlayer.from_dict(p) for p in raw if isinstance(p, dict)]


def guardar_cuenta_suelta(player: BootcampPlayer) -> bool:
    """Añade o reemplaza una cuenta suelta (por nombre). False si no se pudo.

    Se reemplaza en vez de acumular porque volver a pedir la misma cuenta suele
    ser una corrección (cambió de plataforma, se resolvió mal la primera vez), y
    duplicarla haría que la pasada la consultara dos veces por vuelta.
    """
    actuales = [p.to_dict() for p in load_cuentas_sueltas()]
    objetivo = (player.name or "").casefold()
    actuales = [p for p in actuales if (p.get("name") or "").casefold() != objetivo]
    actuales.append(player.to_dict())
    return guardar_lista_json(JSON_SUELTAS_PATH, actuales, etiqueta="cuentas_sueltas")


def quitar_cuenta_suelta(nombre: str) -> bool:
    """Quita una cuenta suelta. `False` si no estaba.

    Con `permitir_vacio=True` y `min_ratio=0` a propósito: en este fichero
    quedarse sin nada **es un estado normal** (alguien deja de seguir su última
    cuenta suelta), y las guardas de `safe_json` —que existen para no machacar los
    ficheros de cuentas cuando un scraping devuelve vacío— aquí bloquearían el
    borrado en silencio: la suscripción desaparecería y la cuenta seguiría
    consultándose en cada pasada para nadie.
    """
    actuales = load_cuentas_sueltas()
    objetivo = (nombre or "").strip().casefold()
    quedan = [p for p in actuales if (p.name or "").casefold() != objetivo]
    if len(quedan) == len(actuales):
        return False
    return guardar_lista_json(
        JSON_SUELTAS_PATH,
        [p.to_dict() for p in quedan],
        etiqueta="cuentas_sueltas",
        permitir_vacio=True,
        min_ratio=0.0,
    )


def nombres_cuentas_sueltas() -> list[str]:
    """Nombres de las cuentas sueltas, para los comandos."""
    return [p.name for p in load_cuentas_sueltas() if p.name]
    
    
    
    
    
    
    
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

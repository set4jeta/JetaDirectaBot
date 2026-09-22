"""Almacén persistente de rangos (`ranked_data.json`).

Qué problema resuelve
---------------------

El fichero se usaba como un diccionario que solo crecía. Al revisarlo tenía
**1885 entradas**, de las cuales:

* 1154 eran de julio de 2025 (más de un año) y 710 tan antiguas que se
  guardaron antes de que existiera el campo `timestamp`.
* 1829 no correspondían a ninguna cuenta seguida: son rivales aleatorios que
  aparecieron en alguna partida detectada y se quedaron ahí para siempre.
* Solo 56 servían para algo.

Tres consecuencias, todas malas:

1. **Escrituras enormes.** `save_rank_data` volcaba los 316 KB completos en
   cada llamada. Un `!team` con 25 cuentas escribía casi 8 MB en disco; cada
   partida detectada (10 participantes), más de 3 MB.
2. **Datos falsos en pantalla.** `get_cached_rank` devolvía cualquier entrada
   sin mirar su edad, así que un embed podía enseñar el rango que un jugador
   tenía hace un año como si fuera el actual.
3. **Memoria.** El diccionario entero vive en RAM en Render.

Cómo funciona ahora
-------------------

* Una sola copia en memoria, releída del disco solo si el fichero cambia
  (comparando `mtime`).
* **Escritura diferida**: las modificaciones se acumulan y se vuelcan como
  mucho una vez cada `RANK_FLUSH_INTERVAL` segundos, de forma atómica
  (`tmp` + `os.replace`) para que un corte no deje el JSON a medias.
* **Caducidad**: al volcar se descartan las entradas más viejas que
  `RANK_DATA_MAX_AGE_DAYS` y, si aún sobran, se recorta al tope
  `RANK_DATA_MAX_ENTRIES` conservando las más recientes.
* `obtener_fresco()` devuelve `None` si el dato es viejo, para que el llamador
  lo vuelva a pedir en vez de enseñar algo desfasado. `obtener_crudo()` sigue
  disponible para quien quiera el último valor conocido a cualquier precio
  (el `!ranking`, que prefiere un dato antiguo a una casilla vacía).
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

import config
from utils.logger import get_logger

log = get_logger("core.rank_store")

BASE_DIR = Path(__file__).resolve().parent.parent
RANKED_DATA_FILE = str(BASE_DIR / "ranked_data.json")

# La primera vez que se poda se guarda una copia, porque el borrado no es
# reversible y el fichero es el histórico de rangos del bot.
BACKUP_FILE = RANKED_DATA_FILE + ".bak"

_lock = threading.RLock()
_ranks: dict[str, dict] | None = None
_mtime: float = 0.0
_dirty = False
_last_flush = 0.0

_stats = {"escrituras": 0, "podadas_edad": 0, "podadas_tope": 0, "flushes": 0}


# ---------------------------------------------------------------------- #
# Carga
# ---------------------------------------------------------------------- #

def _cargar() -> dict[str, dict]:
    """Contenido del fichero, releído solo si cambió en disco."""
    global _ranks, _mtime

    try:
        mtime = os.path.getmtime(RANKED_DATA_FILE)
    except OSError:
        if _ranks is None:
            _ranks = {}
        return _ranks

    with _lock:
        # Si tenemos cambios sin volcar, la copia en memoria es la buena.
        if _ranks is not None and (_dirty or mtime == _mtime):
            return _ranks
        try:
            with open(RANKED_DATA_FILE, "r", encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("No se pudo leer %s: %s", RANKED_DATA_FILE, exc)
            if _ranks is None:
                _ranks = {}
            return _ranks
        if not isinstance(datos, dict):
            datos = {}
        _ranks = datos
        _mtime = mtime
        return _ranks


# ---------------------------------------------------------------------- #
# Lectura
# ---------------------------------------------------------------------- #

def obtener_crudo(puuid: str) -> dict | None:
    """Último rango conocido, sin importar su edad."""
    if not puuid:
        return None
    return _cargar().get(puuid)


def edad(entrada: dict | None) -> float:
    """Segundos desde que se guardó. `inf` si no tiene marca de tiempo.

    Las entradas sin `timestamp` son de la época en la que el campo no se
    guardaba: son las más antiguas de todas, así que tratarlas como infinitas
    es lo correcto.
    """
    if not isinstance(entrada, dict):
        return float("inf")
    ts = entrada.get("timestamp")
    if not ts:
        return float("inf")
    try:
        return max(0.0, time.time() - float(ts))
    except (TypeError, ValueError):
        return float("inf")


def obtener_fresco(puuid: str, max_edad: int | None = None) -> dict | None:
    """Rango solo si es reciente. `None` si está caducado o no existe."""
    entrada = obtener_crudo(puuid)
    if entrada is None:
        return None
    limite = config.RANK_CACHE_MAX_AGE if max_edad is None else max_edad
    return entrada if edad(entrada) < limite else None


# ---------------------------------------------------------------------- #
# Escritura
# ---------------------------------------------------------------------- #

def guardar(puuid: str, rank: dict, flush: bool = True) -> bool:
    """Anota el rango de una cuenta. `False` si el dato no vale.

    No se escribe en disco en cada llamada: se marca como pendiente y se
    vuelca cada `RANK_FLUSH_INTERVAL` segundos como máximo.
    """
    global _dirty

    if not puuid or not isinstance(rank, dict):
        return False

    tier = rank.get("tier")
    if not tier or str(tier).strip() in ("", "Desconocido", "Sin datos"):
        return False

    entrada = {
        "tier": tier,
        "division": rank.get("division", "") or "",
        "lp": rank.get("lp", 0) or 0,
        "timestamp": int(time.time()),
    }

    with _lock:
        datos = _cargar()
        anterior = datos.get(puuid)
        # Si no ha cambiado nada y el dato sigue fresco, no se toca el disco.
        if (
            anterior
            and anterior.get("tier") == entrada["tier"]
            and anterior.get("division") == entrada["division"]
            and anterior.get("lp") == entrada["lp"]
            and edad(anterior) < config.RANK_FLUSH_INTERVAL
        ):
            return True
        datos[puuid] = entrada
        _dirty = True
        _stats["escrituras"] += 1

    if flush:
        volcar()
    return True


def _podar(datos: dict[str, dict]) -> dict[str, dict]:
    """Quita lo caducado y recorta al tope, conservando lo más reciente."""
    limite = config.RANK_DATA_MAX_AGE_DAYS * 86400

    vivos = {p: e for p, e in datos.items() if edad(e) < limite}
    _stats["podadas_edad"] += len(datos) - len(vivos)

    tope = config.RANK_DATA_MAX_ENTRIES
    if tope > 0 and len(vivos) > tope:
        ordenadas = sorted(
            vivos.items(), key=lambda par: par[1].get("timestamp", 0), reverse=True
        )
        _stats["podadas_tope"] += len(vivos) - tope
        vivos = dict(ordenadas[:tope])

    return vivos


def volcar(forzar: bool = False) -> bool:
    """Escribe a disco si hay cambios y toca. `True` si se escribió."""
    global _ranks, _mtime, _dirty, _last_flush

    with _lock:
        if not _dirty:
            return False
        ahora = time.time()
        if not forzar and (ahora - _last_flush) < config.RANK_FLUSH_INTERVAL:
            return False

        datos = _cargar()
        antes = len(datos)
        datos = _podar(datos)
        quitadas = antes - len(datos)

        if quitadas and not os.path.exists(BACKUP_FILE):
            try:
                shutil.copyfile(RANKED_DATA_FILE, BACKUP_FILE)
                log.info("Copia de seguridad del histórico en %s", BACKUP_FILE)
            except OSError as exc:
                log.debug("No se pudo copiar el histórico: %s", exc)

        tmp = RANKED_DATA_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, indent=2)
            os.replace(tmp, RANKED_DATA_FILE)
        except OSError as exc:
            log.warning("No se pudo guardar %s: %s", RANKED_DATA_FILE, exc)
            return False

        _ranks = datos
        _dirty = False
        _last_flush = ahora
        _stats["flushes"] += 1
        try:
            _mtime = os.path.getmtime(RANKED_DATA_FILE)
        except OSError:
            pass

        if quitadas:
            log.info("Histórico de rangos podado: %d entradas fuera, %d dentro.",
                     quitadas, len(datos))
        return True


def estado() -> dict:
    """Resumen para diagnóstico."""
    datos = _cargar()
    limite = config.RANK_CACHE_MAX_AGE
    frescas = sum(1 for e in datos.values() if edad(e) < limite)
    return {
        "entradas": len(datos),
        "frescas": frescas,
        "pendiente_de_volcar": _dirty,
        **_stats,
    }

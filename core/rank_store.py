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

Frescura por actividad, no por reloj (22-09-2026)
-------------------------------------------------
Antes la validez era una ventana de tiempo (`RANK_CACHE_MAX_AGE`, 6 h). Era una
**aproximación mala**: 6 h de retraso en un dato que cambia al terminar cada
partida, y a la vez se pedían rangos de cuentas que llevaban días sin jugar.

Ahora la pregunta que se hace es la correcta: **¿ha jugado esta cuenta desde que
guardamos su rango?** El bot lo sabe de primera mano, porque en cada pasada
consulta `spectator-v5` de todas las cuentas seguidas:

* cuando ve una cuenta **en partida**, anota `en_partida = ahora` (local, sin
  ninguna petición);
* si el rango se guardó **después** de esa marca, es **exacto** — da igual que
  tenga un día o un mes. Nadie ha jugado desde entonces;
* si el rango es **anterior**, jugó y sus LP cambiaron: ahí sí se aplica la
  ventana de `RANK_CACHE_MAX_AGE` (que por eso se puede bajar a 30 min sin
  miedo: solo afecta a cuentas que se sabe que han jugado).

El caso que cierra el círculo: cuando una cuenta **deja** de estar en partida, es
el instante exacto en el que cambiaron sus LP, así que el tracker pide el rango
ahí (`active_game_checker`). Una cuenta que juega se queda exacta con **una**
petición por partida; una que no juega, con ninguna.

El hueco que queda y cómo se tapa
---------------------------------
Todo esto vale mientras el bot esté mirando. Si se reinicia (en el plan gratuito,
a diario) hay un rato en el que una partida puede pasar sin que nadie la vea.
Para eso está `_hueco_desde`: al arrancar se compara la marca de la última pasada
(`marcar_pasada`) con la hora actual, y si el hueco pasa de `RANK_HUECO_MAX` las
entradas guardadas **antes** del hueco se tratan con la ventana de tiempo normal,
no con la regla de actividad. Se pierde la ventaja en esas entradas —que se
vuelven a pedir una vez— y se gana no enseñar un Elo de antes del apagón como si
fuera el de ahora.
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

#: Clave reservada dentro del mismo JSON para el estado del propio almacén. Se
#: guarda aquí y no en un fichero aparte porque son 20 bytes que siempre viajan
#: juntos con los rangos: sin `ultima_pasada` no se puede decidir si un rango es
#: de fiar, así que separarlos sería poder desincronizarlos.
_CLAVE_META = "_meta"

#: Desde cuándo el bot no estaba mirando (marca de tiempo), o 0 si no hubo hueco.
#: Lo pone `_calcular_hueco()` al leer por primera vez tras un arranque.
_hueco_desde: float = 0.0
_hueco_calculado = False

_stats = {"escrituras": 0, "podadas_edad": 0, "podadas_tope": 0, "flushes": 0}


def _calcular_hueco(datos: dict[str, dict]) -> None:
    """Decide si el arranque dejó un hueco sin vigilancia.

    Se llama una sola vez por proceso, en la primera lectura. Si entre la última
    pasada anotada y ahora ha pasado más de `config.RANK_HUECO_MAX`, todo lo
    guardado antes de ese momento pudo quedar desfasado sin que nadie lo viera, y
    esas entradas se tratan con la ventana de tiempo en vez de con la regla de
    actividad. Es lo que evita enseñar un Elo de antes del apagón como el de
    ahora; el precio es volver a pedir esos rangos una vez.
    """
    global _hueco_desde, _hueco_calculado
    _hueco_calculado = True

    meta = datos.get(_CLAVE_META)
    if not isinstance(meta, dict):
        return
    try:
        ultima = float(meta.get("ultima_pasada") or 0)
    except (TypeError, ValueError):
        return
    if not ultima:
        return

    hueco = time.time() - ultima
    if hueco > config.RANK_HUECO_MAX:
        _hueco_desde = ultima
        log.info(
            "Hueco de %.0f min sin vigilancia: los rangos guardados antes se "
            "vuelven a pedir (la regla de actividad no puede responder por ellos).",
            hueco / 60,
        )


# ---------------------------------------------------------------------- #
# Carga
# ---------------------------------------------------------------------- #

def _cargar() -> dict[str, dict]:
    """Contenido del fichero, releído solo si cambió en disco."""
    global _ranks, _mtime, _hueco_calculado

    try:
        mtime = os.path.getmtime(RANKED_DATA_FILE)
    except OSError:
        if _ranks is None:
            _ranks = {}
        _hueco_calculado = True  # sin fichero no hay nada que calcular
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
            _hueco_calculado = True
            return _ranks
        if not isinstance(datos, dict):
            datos = {}
        _ranks = datos
        _mtime = mtime
        # Una sola vez por proceso: decide si el arranque dejó un hueco sin
        # vigilancia y, por tanto, qué rangos no se pueden dar por buenos.
        if not _hueco_calculado:
            _calcular_hueco(datos)
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
    """Rango si sirve como "el de ahora". `None` si no.

    Dos reglas, y la primera manda:

    1. **Por actividad.** Si el rango se guardó *después* de la última vez que se
       vio a esta cuenta en partida, es exacto: no ha jugado desde entonces, así
       que no ha cambiado. Da igual su edad. Es lo que hace que una cuenta que no
       juega desde hace días no gaste ni una petición.
    2. **Por tiempo.** Si se guardó *antes* de esa marca, jugó y sus LP cambiaron:
       solo vale si es más reciente que `max_edad` (30 min por defecto en
       `config`). Y si no hay marca de actividad (nunca se le ha visto jugar, o el
       bot estuvo apagado: ver `_hueco_desde`), también se cae a esta regla, que
       es la red de seguridad.

    El orden importa: invertirlo haría que una cuenta que lleva una semana sin
    jugar se considerara caducada cada 30 minutos.
    """
    entrada = obtener_crudo(puuid)
    if entrada is None or not entrada.get("timestamp"):
        return None

    if _es_exacta(entrada):
        return entrada

    limite = config.RANK_CACHE_MAX_AGE if max_edad is None else max_edad
    return entrada if edad(entrada) < limite else None


def _es_exacta(entrada: dict) -> bool:
    """¿El rango es de después de su último partido observado?

    Se exige que la marca de actividad exista y que el rango sea posterior a
    ella. Con `en_partida` ausente (nunca se le vio jugar) devuelve `False` a
    propósito: ahí no se sabe nada, y quien decide es la ventana de tiempo.
    """
    try:
        visto = float(entrada.get("en_partida") or 0)
        guardado = float(entrada.get("timestamp") or 0)
    except (TypeError, ValueError):
        return False
    if not visto or not guardado:
        return False
    if _hueco_desde and guardado < _hueco_desde:
        # Se guardó antes de un apagón: pudo jugar sin que nadie lo viera.
        return False
    return guardado >= visto


def marcar_en_partida(puuid: str) -> bool:
    """Anota que a esta cuenta se la ha visto **en partida** ahora mismo.

    No gasta ninguna petición: lo llama el tracker con lo que ya sabe de la
    pasada. Y no exige que haya un rango guardado: la marca vale por sí sola
    (invalida el rango que hubiera antes), así que la cuenta entra en el fichero
    aunque nunca se le haya pedido el Elo.
    """
    global _dirty
    if not puuid:
        return False
    with _lock:
        datos = _cargar()
        entrada = datos.setdefault(puuid, {})
        anterior = float(entrada.get("en_partida") or 0)
        ahora = time.time()
        # No se reescribe en cada pasada de los 30 s: con que esté una vez por
        # partida basta, y así el fichero no se ensucia.
        if anterior and ahora - anterior < 60:
            return False
        entrada["en_partida"] = int(ahora)
        _dirty = True
    return True


def marcar_pasada() -> None:
    """Anota que se acaba de completar una pasada del tracker.

    Es lo que permite detectar los apagones: al arrancar se compara esta marca
    con la hora actual y, si el hueco es grande, las entradas anteriores se
    tratan con la ventana de tiempo en vez de con la regla de actividad.
    """
    global _dirty
    with _lock:
        datos = _cargar()
        datos[_CLAVE_META] = {"ultima_pasada": int(time.time())}
        _dirty = True


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
        # La marca de actividad se conserva: es del tracker y no la trae el
        # rango. Perderla aquí dejaría la cuenta sin la única señal que dice si
        # este dato sigue valiendo mañana.
        if isinstance(anterior, dict) and anterior.get("en_partida"):
            entrada["en_partida"] = anterior["en_partida"]
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


def _marca(entrada: dict) -> float:
    """Marca de tiempo más reciente de la entrada: el rango o la actividad.

    Hace falta porque una entrada puede tener **solo** `en_partida`: el tracker
    anota que ha visto jugar a una cuenta antes de que nadie le haya pedido el
    Elo. Esa entrada no tiene `timestamp`, así que `edad()` diría "infinito" y la
    poda la borraría en el primer volcado, dejando al bot sin la señal.
    """
    for clave in ("timestamp", "en_partida"):
        try:
            valor = float(entrada.get(clave) or 0)
        except (TypeError, ValueError):
            continue
        if valor:
            return valor
    return 0.0


def _podar(datos: dict[str, dict]) -> dict[str, dict]:
    """Quita lo caducado y recorta al tope, conservando lo más reciente.

    La clave `_meta` (el estado del propio almacén) no se poda nunca: no es un
    rango, y borrarla dejaría al bot sin poder detectar el siguiente apagón.
    """
    limite = config.RANK_DATA_MAX_AGE_DAYS * 86400

    meta = datos.get(_CLAVE_META)
    rangos = {p: e for p, e in datos.items() if p != _CLAVE_META}

    vivos = {p: e for p, e in rangos.items() if (time.time() - _marca(e)) < limite}
    _stats["podadas_edad"] += len(rangos) - len(vivos)

    tope = config.RANK_DATA_MAX_ENTRIES
    if tope > 0 and len(vivos) > tope:
        ordenadas = sorted(vivos.items(), key=lambda par: _marca(par[1]), reverse=True)
        _stats["podadas_tope"] += len(vivos) - tope
        vivos = dict(ordenadas[:tope])

    if meta is not None:
        vivos[_CLAVE_META] = meta
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

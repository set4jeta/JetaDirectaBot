"""Registro en disco de los avisos que el bot ha publicado.

Por qué hace falta
------------------
El bot detecta partidas y las anuncia, pero **no dejaba constancia de ninguna**.
`active_game_cache` es memoria del proceso (se va con el reinicio) y
`announced_games.json` guarda solo `{canal: {id_partida: hora}}` con dos horas de
vida, que sirve para no repetir un aviso y para nada más: no dice de quién era la
partida, ni con qué campeón, ni cuándo.

Eso deja tres cosas sin poder hacer:

* La web no puede publicar "los últimos avisos", que es literalmente lo que se
  quería enseñar: si esto te interesa, en tu Discord te llega solo.
* No hay forma de responder "¿cuántos avisos mandó el bot esta semana?" sin
  leerse el log de Render, que se rota.
* No se puede comprobar que el tracker está avisando de verdad y no solo
  "funcionando": un bot que no falla y no avisa se ve igual que uno que avisa.

Formato: JSONL, una línea por aviso
-----------------------------------
Un objeto JSON por línea, y no un JSON con una lista dentro, por un motivo
concreto: **se puede añadir una línea sin leer ni reescribir el fichero**. Con una
lista, cada aviso obligaría a cargar el histórico completo, añadir y volcarlo, que
es exactamente el problema que ya costó caro en `ranked_data.json` (cada
`save_rank_data` reescribía 316 kB). Y si el proceso muere a mitad de línea —Render
manda SIGTERM en cada despliegue— se pierde esa línea, no el fichero.

Qué NO se guarda, a propósito
-----------------------------
Ni `channel_id`, ni `guild_id`, ni `user_id`. Nada de quién lo recibió.

No es por ahorrar espacio: este fichero está pensado para que lo lea el generador
de la web y acabe publicado, así que guardar identificadores de servidores o de
usuarios sería publicar quién usa el bot y dónde. Lo que se guarda es la partida,
que es información pública de un jugador profesional: su nombre, su equipo y su
cuenta ya salen en las páginas de liga.

Tampoco se guarda cuánta gente lo recibió. Un contador de destinatarios por aviso
es un dato de negocio que no se necesita aquí y que, agregado, dibuja el tamaño de
cada servidor.

Dónde vive el fichero
---------------------
Junto a los demás datos del tracker. En Render el disco es efímero, así que el
histórico vive lo que vive el contenedor: es un registro para leer, no un archivo
histórico garantizado. El generador de la web lo trata como todo lo demás —si el
dato no está, la sección no se pinta— así que un fichero ausente no rompe nada.
"""

from __future__ import annotations

import json
import os
import time

from utils.logger import get_logger

log = get_logger("tracking.avisos_log")

RUTA = os.path.join(os.path.dirname(__file__), "avisos.jsonl")

#: Avisos que se conservan. 500 son varias semanas de actividad real y unos
#: 120 kB; la web solo enseña los últimos. El recorte no se hace en cada
#: escritura (ver `_recortar`).
MAX_LINEAS = 500

#: Cada cuántas escrituras se comprueba el tamaño. Recortar obliga a leer el
#: fichero entero, así que hacerlo en cada aviso anularía la ventaja de haber
#: elegido un formato que se puede ampliar sin leerlo.
CADA = 50

_escrituras = 0


def _campeon_de(match, puuid: str) -> str:
    """Campeón que lleva la cuenta seguida en esa partida, o cadena vacía."""
    participante = match.get_participant_by_puuid(puuid)
    return getattr(participante, "champion_name", "") or ""


def _rango_de(ranked_map: dict, puuid: str) -> str:
    """El rango tal y como lo devuelve la caché, en texto corto.

    Se guarda ya formateado y no el diccionario entero porque lo que interesa es
    lo que se enseñó, y porque el formato de `ranked_map` es un detalle interno
    que no debería viajar a un fichero que se publica.
    """
    datos = ranked_map.get(puuid) or {}
    tier = str(datos.get("tier") or "").strip()
    if not tier or tier.lower() in ("desconocido", "unranked"):
        return ""
    division = str(datos.get("division") or datos.get("rank") or "").strip()
    lp = datos.get("lp", datos.get("leaguePoints"))
    partes = [tier]
    if division and tier.upper() not in ("MASTER", "GRANDMASTER", "CHALLENGER"):
        partes.append(division)
    texto = " ".join(partes)
    return f"{texto} ({lp} LP)" if isinstance(lp, int) else texto


def registrar(match, account, player, liga: str, ranked_map: dict) -> bool:
    """Anota un aviso publicado. Devuelve si se escribió.

    Se llama **después** de enviar y solo si algún envío salió bien: el registro
    es de avisos publicados, no de partidas detectadas. Una partida que se detecta
    y no se anuncia (nadie sigue esa liga) no es un aviso.

    Nunca levanta. Está en el camino de la notificación, y que falle una
    escritura en disco no puede impedir que el aviso siguiente se envíe: el
    registro es un extra, el aviso es el producto.
    """
    global _escrituras
    try:
        rid = getattr(account, "riot_id", None) or {}
        cuenta = f"{rid.get('game_name', '')}#{rid.get('tag_line', '')}".strip("#")
        entrada = {
            "ts": int(time.time()),
            "partida": str(getattr(match, "game_id", "") or ""),
            "jugador": getattr(player, "name", None) or rid.get("game_name") or "",
            "equipo": (getattr(player, "team", "") or "").upper(),
            "liga": liga or "",
            "cuenta": cuenta,
            "campeon": _campeon_de(match, getattr(account, "puuid", "")),
            "rango": _rango_de(ranked_map, getattr(account, "puuid", "")),
            "cola": getattr(match, "game_queue", None),
            "modo": getattr(match, "game_mode", None) or "",
            "servidor": (getattr(match, "platform", None) or "").upper(),
        }
        with open(RUTA, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entrada, ensure_ascii=False) + "\n")
        _escrituras += 1
        if _escrituras % CADA == 0:
            _recortar()
        return True
    except Exception as exc:  # noqa: BLE001 — nunca romper el envío por el registro
        log.debug("No se pudo registrar el aviso: %s", exc)
        return False


def _recortar() -> None:
    """Deja el fichero en `MAX_LINEAS`, escribiendo de forma atómica.

    `.tmp` + `os.replace` como en `utils/safe_json.py`: si el proceso muere a
    mitad del recorte, el fichero original sigue entero. Un histórico truncado
    por un despliegue sería peor que uno demasiado largo.
    """
    try:
        with open(RUTA, encoding="utf-8") as fh:
            lineas = fh.readlines()
    except OSError:
        return
    if len(lineas) <= MAX_LINEAS:
        return
    tmp = RUTA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.writelines(lineas[-MAX_LINEAS:])
    os.replace(tmp, RUTA)
    log.debug("avisos.jsonl recortado a %d líneas", MAX_LINEAS)


def leer(tope: int = 50) -> list[dict]:
    """Los últimos avisos, del más reciente al más antiguo.

    Salta las líneas que no sean JSON válido en vez de fallar: una línea a medias
    por un SIGTERM en pleno volcado es un caso esperado, y perder el histórico
    entero por un byte suelto no tiene sentido.

    Está aquí y no solo en el generador de la web para que el bot pueda enseñar
    lo mismo (un `/ultimos` es el uso obvio) sin duplicar el parseo.
    """
    try:
        with open(RUTA, encoding="utf-8") as fh:
            lineas = fh.readlines()
    except OSError:
        return []
    salida = []
    for linea in reversed(lineas):
        linea = linea.strip()
        if not linea:
            continue
        try:
            dato = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(dato, dict):
            salida.append(dato)
        if len(salida) >= tope:
            break
    return salida

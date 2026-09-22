"""Escritura de JSON con red de seguridad.

Motivo de que este módulo exista
--------------------------------
`accounts_from_teams.py` y `accounts_from_leaderboard.py` sacan los jugadores de
dpm.lol y luego hacían, literalmente:

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(nuevos, f, ...)

Sin comprobar nada. Eso significa que **el día que dpm.lol recompile su CSS**
(los nombres se buscan con un selector de clases de Tailwind:
`span.font-semibold.text-bm.lg:text-bxl`) el scraper devuelve `[]`, y esa lista
vacía **sobrescribe los rosters buenos**. El bot no se cae: se queda mudo, que es
peor, porque no hay ningún síntoma hasta que alguien pregunta por un jugador.

Lo mismo si dpm.lol responde 403, o si cambia el nombre de un campo del JSON, o
si la red se corta a mitad de la paginación del leaderboard: en todos esos casos
el resultado es "menos datos de los que ya tenía", y escribirlo es destruir
información a cambio de nada.

Reglas que aplica `guardar_lista_json`
-------------------------------------
1. **Nunca escribe una lista vacía** si ya había datos. Un 0 nunca es una
   actualización legítima: si de verdad no queda nadie, se borra el fichero a
   mano.
2. **Nunca escribe un encogimiento brusco.** Por debajo de `min_ratio` (70 % por
   defecto) del recuento anterior se rechaza. Un traspaso normal de la LEC mueve
   1 o 2 jugadores de 46; perder 15 es un fallo de scraping, no un mercado
   loco.
3. **Escritura atómica.** Se escribe en `<fichero>.tmp` y se hace `os.replace`,
   que en el mismo volumen es atómico. Si el proceso muere a mitad del volcado
   (y este bot recibe SIGTERM de Render en cada despliegue), el fichero original
   sigue intacto en vez de quedarse truncado.
4. **Copia de seguridad** en `<fichero>.bak` antes de sustituir, para poder
   volver atrás si el contenido es válido en tamaño pero malo en contenido.

El precedente ya estaba en el propio repo: `apis/dpm_api.py::fetch_infoplayers_eu`
se niega a sobrescribir cuando recibe 0 jugadores y usa `.tmp` + `os.replace`.
Esto solo generaliza esa idea y la hace obligatoria en los dos sitios donde
faltaba.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any, Callable, Sequence

from utils.logger import get_logger

log = get_logger(__name__)

#: Fracción del recuento anterior por debajo de la cual se rechaza la escritura.
DEFAULT_MIN_RATIO = 0.7


class EscrituraRechazada(RuntimeError):
    """La nueva lista no pasó las comprobaciones y no se escribió nada."""


def _contar_anteriores(ruta: str) -> int:
    """Cuántos elementos tiene el JSON que ya está en disco.

    Un fichero corrupto cuenta como 0 para que la primera escritura buena pueda
    repararlo: si no, un JSON roto bloquearía las actualizaciones para siempre.
    """
    if not os.path.exists(ruta):
        return 0
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            previo = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("%s no se pudo leer (%s); se trata como vacío.", ruta, exc)
        return 0
    return len(previo) if isinstance(previo, (list, dict)) else 0


def guardar_lista_json(
    ruta: str,
    datos: Sequence[Any],
    *,
    etiqueta: str,
    min_ratio: float = DEFAULT_MIN_RATIO,
    permitir_vacio: bool = False,
    hacer_backup: bool = True,
) -> bool:
    """Escribe `datos` en `ruta` solo si parecen una actualización sana.

    Devuelve True si escribió, False si lo rechazó. **No lanza excepción** en el
    caso de rechazo: la tarea de fondo que llama a esto tiene que seguir viva y
    reintentar en la siguiente vuelta, no morirse.
    """
    nuevos = len(datos)
    anteriores = _contar_anteriores(ruta)

    if nuevos == 0 and not permitir_vacio:
        if anteriores == 0:
            log.warning(
                "%s: 0 elementos y no había nada previo. No se crea el fichero.",
                etiqueta,
            )
            return False
        log.error(
            "%s: la fuente devolvió 0 elementos y en disco hay %d. "
            "NO se sobrescribe: se conservan los datos buenos. "
            "Revisa si dpm.lol cambió el HTML o está respondiendo 403.",
            etiqueta,
            anteriores,
        )
        return False

    if anteriores > 0 and nuevos < anteriores * min_ratio and not (nuevos == 0 and permitir_vacio):
        # El caso `nuevos == 0 and permitir_vacio` ya pasó la comprobación de
        # arriba a propósito (alguien pidió vaciar el fichero), así que aquí no
        # se vuelve a bloquear: si no, `permitir_vacio` no serviría de nada.
        log.error(
            "%s: encogimiento sospechoso, %d elementos frente a %d anteriores "
            "(mínimo aceptable %d, el %.0f %%). NO se sobrescribe.",
            etiqueta,
            nuevos,
            anteriores,
            int(anteriores * min_ratio),
            min_ratio * 100,
        )
        return False

    tmp = f"{ruta}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)

        if hacer_backup and os.path.exists(ruta):
            try:
                shutil.copy2(ruta, f"{ruta}.bak")
            except OSError as exc:
                # Un backup fallido no debe impedir la actualización buena.
                log.warning("%s: no se pudo hacer copia de seguridad: %s", etiqueta, exc)

        os.replace(tmp, ruta)
    except (OSError, TypeError, ValueError) as exc:
        # `TypeError`/`ValueError`: un objeto no serializable revienta a mitad
        # del volcado. Sin capturarlo, la excepción sube a la tarea de fondo y
        # la mata, y deja el `.tmp` tirado en disco.
        log.exception("%s: fallo escribiendo %s: %s", etiqueta, ruta, exc)
        _borrar_silencioso(tmp)
        return False

    if nuevos == anteriores:
        log.info("%s: %d elementos guardados (sin cambio de recuento).", etiqueta, nuevos)
    else:
        log.info(
            "%s: %d elementos guardados (antes %d, %+d).",
            etiqueta,
            nuevos,
            anteriores,
            nuevos - anteriores,
        )
    return True


def _borrar_silencioso(ruta: str) -> None:
    try:
        os.remove(ruta)
    except OSError:
        pass


def guardar_json_atomico(ruta: str, datos: Any, *, etiqueta: str) -> bool:
    """Escribe cualquier JSON sin poder truncar el que ya está en disco.

    Es `guardar_lista_json` **sin** las guardas de recuento, para las cachés:
    ahí un recuento menor sí es legítimo (una caché se poda, un mapa pierde
    claves caducadas), así que bloquear el encogimiento estorbaría. Lo que se
    conserva es lo único que nunca sobra: `tmp` + `os.replace`.

    Por qué importa aunque el contenido sea recuperable: `open(ruta, "w")`
    **trunca el destino antes** de saber si el volcado cabe. El 03-09-2026 el
    disco de desarrollo llegó a 0 MB libres y dejó `tracked_matches.json` y
    `announced_games.json` en 0 bytes; el segundo, además, se leía con
    `json.load` a pelo desde `ActiveGameTracker.__init__`, así que el fichero
    vacío no habría costado un aviso: habría impedido arrancar el tracker.

    Devuelve True si escribió. No lanza: el llamador es casi siempre una tarea
    de fondo que tiene que seguir viva.

    Se captura `TypeError` además de `OSError` porque un objeto no serializable
    (un `datetime` sin convertir en un `TrackedMatch`, el caso que el
    `except TypeError` original de `storage.py` ya cubría) revienta **a mitad**
    del volcado, con el fichero temporal abierto. Sin capturarlo, la excepción
    sube hasta la tarea de fondo y la mata, y encima deja el `.tmp` en disco.
    """
    tmp = f"{ruta}.tmp"
    try:
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
        return True
    except (OSError, TypeError, ValueError) as exc:
        log.error(
            "%s: no se pudo escribir %s (%s). Se conserva el fichero anterior.",
            etiqueta, ruta, exc,
        )
        _borrar_silencioso(tmp)
        return False


def cargar_lista_json(ruta: str, defecto: Callable[[], Any] = list) -> Any:
    """Lee un JSON de lista tolerando que no exista o esté corrupto."""
    if not os.path.exists(ruta):
        return defecto()
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("%s ilegible (%s); se usa el valor por defecto.", ruta, exc)
        return defecto()

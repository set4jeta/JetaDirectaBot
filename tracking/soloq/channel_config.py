"""A qué canales van los avisos de SoloQ de cada servidor.

Qué cambió y por qué
--------------------
Antes esto era `{guild_id: channel_id}`: **un canal por servidor**. Y a la vez
`/premium` vendía "3 canales de avisos" en el plan Pro y 10 en el Elite, o sea
que el plan de pago prometía algo que el bot no sabía hacer. De las dos formas
de arreglarlo —quitar el cupo o implementarlo— se eligió implementarlo, porque
rutar el mismo aviso a varios canales es justo lo que piden los servidores
grandes (un canal por región, o uno público y otro de staff) y es lo que los
bots comparables ponen detrás de su muro de pago sin cobrar por el aviso en sí.

Formato en disco
----------------
`notify_config.json` guardaba un entero por servidor y ahora guarda una lista:

    {"922599273160409108": [922599273160409111, 1234...]}

Se **leen los dos formatos**. Un entero suelto se normaliza a lista de uno, así
que la configuración que ya existía sigue valiendo sin migrar nada a mano; la
primera escritura la deja en el formato nuevo. Sin esto, el servidor del usuario
se habría quedado sin canal de avisos al actualizar.

Sobre el cupo del plan
----------------------
El recorte se aplica **al leer**, no al guardar (`plans.recortar`): si un
servidor baja de plan no se le borra la configuración, solo se le dejan de usar
los canales que exceden su cupo. Si vuelve a subir, siguen ahí. Borrar al bajar
de plan sería irreversible y castigaría a quien deje de pagar con perder su
configuración.
"""

from __future__ import annotations

import json
import os

from tracking.soloq.plans import cabe, limite, recortar
from utils.logger import get_logger

log = get_logger("tracking.channel_config")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "notify_config.json")


def _cargar_bruto() -> dict[str, list[int]]:
    """Lo que hay en disco, normalizado a `{guild_id_str: [channel_id, ...]}`.

    No aplica cupos: esto es el fichero, no lo que se usa. La diferencia importa
    porque al guardar hay que conservar lo que el servidor tenía configurado
    aunque su plan actual no lo permita.
    """
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            datos = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        # Un JSON roto no puede impedir que el bot arranque: se sigue sin
        # canales, que es visible en `/health` y en el arranque, en vez de
        # reventar la tarea de partidas.
        log.warning("notify_config.json ilegible (%s): se sigue sin canales", exc)
        return {}

    if not isinstance(datos, dict):
        return {}

    salida: dict[str, list[int]] = {}
    for clave, valor in datos.items():
        if isinstance(valor, int):
            salida[str(clave)] = [valor]          # formato viejo
        elif isinstance(valor, list):
            salida[str(clave)] = [int(v) for v in valor if isinstance(v, int)]
    return salida


def _guardar(datos: dict[str, list[int]]) -> None:
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


# ---------------------------------------------------------------------- #
# Lectura
# ---------------------------------------------------------------------- #

def canales_de(guild_id: int | str) -> list[int]:
    """Canales de avisos de un servidor, ya recortados a su cupo."""
    guardados = _cargar_bruto().get(str(guild_id), [])
    return recortar(guild_id, "canales", guardados)


def canales_guardados(guild_id: int | str) -> list[int]:
    """Todo lo que el servidor tiene configurado, ignorando el cupo.

    Se usa para poder decirle "tienes 4 configurados pero tu plan usa 1": sin
    esto, un servidor que baja de plan vería desaparecer canales sin explicación.
    """
    return list(_cargar_bruto().get(str(guild_id), []))


def todos_los_canales() -> dict[int, list[int]]:
    """`{guild_id: [channel_id, ...]}` de todos los servidores, con cupo aplicado.

    Es lo que usa la pasada del tracker. Aplica el cupo aquí y no en el envío
    para que el bucle de notificación no tenga que saber nada de planes.
    """
    salida: dict[int, list[int]] = {}
    for clave, canales in _cargar_bruto().items():
        try:
            guild_id = int(clave)
        except (TypeError, ValueError):
            continue
        permitidos = recortar(guild_id, "canales", canales)
        if permitidos:
            salida[guild_id] = permitidos
    return salida


# ---------------------------------------------------------------------- #
# Escritura
# ---------------------------------------------------------------------- #

def agregar_canal(guild_id: int | str, channel_id: int) -> tuple[str, int]:
    """Añade un canal de avisos. Devuelve `(resultado, cupo)`.

    `resultado` es una de tres cadenas, para que quien llame decida el texto:

    * `"añadido"`  — se guardó;
    * `"repetido"` — ya estaba;
    * `"cupo"`     — el plan no da para más.

    Se devuelve el cupo junto al resultado porque el mensaje de error lo
    necesita y sacarlo con otra llamada obligaría a leer el plan dos veces.
    """
    tope = limite(guild_id, "canales")
    datos = _cargar_bruto()
    actuales = datos.get(str(guild_id), [])

    if channel_id in actuales:
        return "repetido", tope
    if not cabe(guild_id, "canales", len(actuales)):
        return "cupo", tope

    datos[str(guild_id)] = actuales + [channel_id]
    _guardar(datos)
    log.info("Servidor %s: canal de avisos %s añadido (%d/%d)",
             guild_id, channel_id, len(actuales) + 1, tope)
    return "añadido", tope


def quitar_canal(guild_id: int | str, channel_id: int) -> bool:
    """Quita un canal concreto. `False` si no estaba."""
    datos = _cargar_bruto()
    actuales = datos.get(str(guild_id), [])
    if channel_id not in actuales:
        return False

    restantes = [c for c in actuales if c != channel_id]
    if restantes:
        datos[str(guild_id)] = restantes
    else:
        datos.pop(str(guild_id), None)
    _guardar(datos)
    log.info("Servidor %s: canal %s quitado (quedan %d)", guild_id, channel_id, len(restantes))
    return True


def quitar_todos(guild_id: int | str) -> int:
    """Deja al servidor sin avisos. Devuelve cuántos canales había."""
    datos = _cargar_bruto()
    habia = len(datos.pop(str(guild_id), []))
    if habia:
        _guardar(datos)
        log.info("Servidor %s: avisos de SoloQ desactivados (%d canal/es)", guild_id, habia)
    return habia


# ---------------------------------------------------------------------- #
# Compatibilidad
# ---------------------------------------------------------------------- #

def load_channel_ids() -> dict[int, int]:
    """`{guild_id: primer_canal}`. **Obsoleto**, solo para scripts antiguos.

    El bot usa `todos_los_canales()`. Esto se queda porque devolver medio dato
    es mejor que romper un script suelto, pero cualquier código que decida a
    quién avisar tiene que usar la función nueva o solo avisará al primer canal.
    """
    return {gid: canales[0] for gid, canales in todos_los_canales().items() if canales}

"""Cuánto ancho de banda de salida lleva gastado el bot este mes.

Por qué existe
--------------
El 29-09-2026 Render **suspendió el workspace** del bot y estuvo caído 3 días.
El motivo no fue un fallo del código: Render bajó en abril de 2026 el ancho de
banda incluido en el plan Hobby **de 100 GB a 5 GB**, y el bot venía gastando
más de 5. El dueño se enteró cuando ya estaba suspendido, y esa es la parte que
esta utilidad arregla: **no había forma de ver cuánto llevaba consumido**.

La causa del consumo se arregló aparte (los avisos ya no adjuntan imágenes: ver
`ui/player_image_utils.py`). Esto es la red de seguridad para que, si algún día
vuelve a subir —más servidores, más avisos, otra función que adjunte algo—, se
vea en `/health` **antes** de que el proveedor corte el servicio.

Cómo cuenta
-----------
Son **dos partidas** y se guardan por separado porque sirven para cosas
distintas:

* `bytes` — lo que se manda a Discord: el JSON del embed, los adjuntos y una
  envoltura por mensaje. Es una estimación (no mide el handshake ni las tramas
  del WebSocket, que son constantes y pequeñas) y es la que decide si se puede
  seguir adjuntando el `.bat`.
* `sondeo` — los bytes de las respuestas de la API de Riot, medidos de verdad
  sobre cada petición. Es la partida grande: en octubre los avisos fueron
  1,4 MB y el mes cerró en 5 445 MB.

Durante un tiempo este módulo decía que el sondeo no había que contarlo «porque
Render factura solo la salida». La medición lo desmintió: el consumo por hora
cuadra con el número de peticiones a Riot —22 MB/h con ~919 cuentas cada 240 s
son 15 pasadas × 1,47 MB— y no con los mensajes, que llevaban congelados en
1,4 MB desde el 20-10. Cómo lo llame el proveedor da igual; lo que se gasta es
lo que se mide. Desde el 01-11-2026 `total_bytes()` es la cifra que manda.

Lo que **no** cuenta: las descargas de dpm.lol (rosters, logos). Van por
`cloudscraper`/`curl_cffi`, son de frecuencia baja y están acotadas por la tarea
diaria; contarlas exigiría instrumentar un tercero y ensuciaría la medida que
sí importa.

Cuando se pasa del presupuesto
------------------------------
No se deja de avisar: se deja de **adjuntar el `.bat`**. El aviso —que es el
producto— sigue saliendo entero; lo único que se pierde es el atajo para
espectar, y se avisa en `/health`. Prefiero esa degradación a que el proveedor
corte el bot entero, que es lo que pasó y es mucho peor.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from utils.logger import get_logger

log = get_logger("utils.egress")

#: Dónde se guarda el acumulado. Va en `tracking/soloq/` y está en la lista de
#: `core/estado_remoto.ARCHIVOS`, así que sobrevive a reinicios y despliegues:
#: sin eso el contador volvería a cero en cada uno y no valdría para nada.
#:
#: Se puede desviar con `EGRESS_RUTA`, y **eso es para las pruebas, no un adorno**:
#: `test_salida_red` comprueba que el acumulado sobrevive a recargar el módulo, y
#: al recargarlo esta constante se vuelve a evaluar. Si la prueba la hubiera
#: desviado cambiando el atributo, la recarga lo desharía y la prueba escribiría
#: en el contador de verdad — que es justo el fichero que existe para no volver a
#: quedarse sin ancho de banda sin enterarse.
RUTA = os.environ.get("EGRESS_RUTA") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tracking", "soloq", "egress.json")

#: Presupuesto mensual en MB. **Por debajo de los 5 GB de Render a propósito**:
#: el margen es lo que evita que un pico de última hora provoque la suspensión
#: que ya pasó. Se puede subir con `EGRESS_PRESUPUESTO_MB` si algún día se paga
#: por más ancho de banda.
#:
#: 4 800 y no 4 000 (cambiado el 01-11-2026): la cadencia del barrido ahora se
#: calcula **para gastar exactamente esto a lo largo del mes** (ver
#: `tracking/soloq/cadencia.py`), así que el presupuesto dejó de ser un umbral de
#: alarma y pasó a ser el objetivo que se reparte. Con 4 000 se dejaban 1 GB sin
#: usar —o sea, avisos más lentos de lo necesario— por un margen que no hacía
#: falta: los 200 MB que quedan son el 4 %, y la cadencia se autocorrige cada
#: pasada, así que un desvío se compensa solo en las siguientes vueltas.
PRESUPUESTO_MB_DEFECTO = 4800

#: Lo que Discord añade a cada mensaje por fuera del embed (envoltura JSON,
#: nonce, referencias). Es una constante medida a ojo sobre envíos reales; para
#: una estimación de tendencia es suficiente.
ENVOLTURA_BYTES = 400

#: A partir de aquí se avisa en el log, y al llegar al 100 % se deja de adjuntar.
AVISO_50 = 0.5
AVISO_80 = 0.8

#: Estado en memoria. `None` = todavía no se ha leído del disco.
_estado: dict[str, Any] | None = None

#: Bytes de **sondeo** (API de Riot, dpm.lol) que aún no se han volcado al
#: contador. Se acumulan en memoria a propósito: el barrido hace cientos de
#: peticiones por pasada y escribir el JSON en cada una costaría más que la
#: propia petición. Se vuelcan al cerrar la pasada (`volcar_sondeo`).
_pendiente_sondeo = 0

#: `registrar_sondeo` se llama desde el loop de asyncio y desde los hilos de
#: scraping, así que el acumulador necesita candado.
_lock = threading.Lock()


def _mes_actual() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def presupuesto_bytes() -> int:
    """El presupuesto del mes, en bytes. Se lee en caliente para respetar el `.env`."""
    try:
        mb = int(os.getenv("EGRESS_PRESUPUESTO_MB", "") or PRESUPUESTO_MB_DEFECTO)
    except ValueError:
        mb = PRESUPUESTO_MB_DEFECTO
    return max(1, mb) * 1024 * 1024


def _cargar() -> dict[str, Any]:
    """Lee el acumulado del disco, reiniciándolo si el mes cambió.

    Si el fichero está corrupto se empieza de cero **y se sigue**: un contador
    ilegible no puede impedir que el bot arranque ni que mande avisos.
    """
    global _estado
    mes = _mes_actual()

    if _estado is not None:
        if _estado.get("mes") == mes:
            return _estado
        # El proceso sobrevive al cambio de mes —el bot corre semanas seguidas—
        # y `_estado` está en memoria, así que sin esta comprobación el
        # acumulado del mes viejo se quedaría como «el de este mes» hasta el
        # próximo reinicio. Desde el 01-11-2026 eso ya no es solo un contador
        # feo en `/health`: la cadencia lee `total_bytes()` para repartir el
        # presupuesto, así que vería el mes agotado desde el día 1 y se pasaría
        # el mes entero a 3 600 s. Justo lo que se quería evitar.
        log.info(
            "Cambio de mes (%s -> %s): el contador de salida vuelve a cero",
            _estado.get("mes"), mes,
        )
        _estado = None

    datos: dict[str, Any] = {
        "mes": mes, "bytes": 0, "mensajes": 0, "adjuntos": 0, "sondeo": 0,
    }
    try:
        with open(RUTA, encoding="utf-8") as fh:
            guardado = json.load(fh)
        if isinstance(guardado, dict) and guardado.get("mes") == mes:
            datos.update({k: int(guardado.get(k, 0) or 0)
                          for k in ("bytes", "mensajes", "adjuntos", "sondeo")})
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("Contador de salida ilegible (%s); se empieza de cero", exc)

    _estado = datos
    return _estado


def _guardar(datos: dict[str, Any]) -> None:
    """Escribe el acumulado sin poder tumbar el envío de un aviso.

    Un fallo de disco aquí no puede costar un aviso: la cuenta es para vigilar,
    no para funcionar.
    """
    try:
        os.makedirs(os.path.dirname(RUTA), exist_ok=True)
        tmp = RUTA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False)
        os.replace(tmp, RUTA)
    except OSError as exc:
        log.debug("No se pudo guardar el contador de salida: %s", exc)


def estimar(embed: Any = None, files: Any = None) -> int:
    """Bytes de salida que costará enviar ese embed con esos adjuntos.

    Cuenta el JSON del embed, los ficheros y la envoltura. Es la misma cuenta
    que hace `registrar`, expuesta aparte para poder comprobarla en las pruebas
    sin escribir nada en disco.
    """
    total = ENVOLTURA_BYTES
    if embed is not None:
        try:
            crudo = json.dumps(embed.to_dict(), ensure_ascii=False)
            total += len(crudo.encode("utf-8"))
        except (AttributeError, TypeError, ValueError):
            # Un embed raro cuenta como uno normal en vez de reventar el aviso.
            total += 2000
    for f in files or []:
        # Acepta las dos formas que hay en el código: un `nextcord.File` (con la
        # ruta dentro de `f.fp.name`) y una tupla `(ruta, nombre)`, que es como
        # `active_game_checker` guarda los adjuntos para poder reenviarlos. Si
        # hubiera que convertir en cada llamante, alguno se olvidaría y ese
        # envío no se contaría.
        if isinstance(f, tuple):
            ruta = f[0]
        else:
            ruta = getattr(getattr(f, "fp", None), "name", "") or ""
        try:
            total += os.path.getsize(ruta)
        except (OSError, TypeError):
            # No se puede saber el tamaño: se cuenta una imagen normal, que es
            # lo que se adjuntaba cuando esto se escribió. Preferible a contar 0
            # y quedarse corto en la estimación.
            total += 2048
    return total


def registrar(embed: Any = None, files: Any = None, destinatarios: int = 1) -> int:
    """Suma al acumulado del mes el coste de un envío y avisa si toca.

    `destinatarios` existe porque el mismo embed se manda a varios canales y a
    varias personas: cada envío es una subida distinta y Discord no deduplica
    nada. Ese detalle es justo lo que se pasó por alto y lo que agotó los 5 GB.
    """
    datos = _cargar()
    bytes_envio = estimar(embed, files) * max(1, destinatarios)
    datos["bytes"] += bytes_envio
    datos["mensajes"] += max(1, destinatarios)
    if files:
        datos["adjuntos"] += max(1, destinatarios)
    _guardar(datos)

    _avisar_si_toca(datos)
    return bytes_envio


# ---------------------------------------------------------------------- #
# El sondeo: lo que de verdad gasta el ancho de banda
# ---------------------------------------------------------------------- #
#
# Hasta el 01-11-2026 este módulo solo contaba lo que se mandaba a Discord, y por
# eso no servía de alarma: el contador llevaba congelado en 417 mensajes (1,4 MB)
# desde el 20-10 mientras el mes cerraba en 5 445 MB. La diferencia eran las
# peticiones a la API de Riot del barrido, que son el gasto real y no estaban
# contadas en ningún sitio.
#
# Se cuentan **aquí y no en el cliente de Riot** para que haya un solo número y
# una sola fuente de verdad: `total_bytes()` es lo que se compara con el
# presupuesto, y es de donde sale la cadencia (`tracking/soloq/cadencia.py`).

def registrar_sondeo(bytes_recibidos: int) -> None:
    """Suma bytes de una respuesta de la API al acumulador del mes.

    **No toca el disco**: esto se llama cientos de veces por pasada. El volcado
    lo hace `volcar_sondeo()` al terminar el barrido.
    """
    global _pendiente_sondeo
    if bytes_recibidos <= 0:
        return
    with _lock:
        _pendiente_sondeo += int(bytes_recibidos)


def volcar_sondeo() -> int:
    """Pasa al contador persistente lo acumulado. Devuelve los bytes volcados."""
    global _pendiente_sondeo
    with _lock:
        pendiente = _pendiente_sondeo
        _pendiente_sondeo = 0
    if pendiente <= 0:
        return 0

    datos = _cargar()
    datos["sondeo"] = int(datos.get("sondeo", 0) or 0) + pendiente
    _guardar(datos)
    _avisar_si_toca(datos)
    return pendiente


def sondeo_bytes() -> int:
    """Bytes de sondeo del mes, incluidos los que aún están sin volcar."""
    with _lock:
        pendiente = _pendiente_sondeo
    return int(_cargar().get("sondeo", 0) or 0) + pendiente


def total_bytes() -> int:
    """Todo lo que se ha gastado este mes: Discord **y** sondeo.

    Es la cifra que importa para el límite del proveedor, y la que usa la
    cadencia. `bytes` sigue siendo solo Discord porque es lo que decide si se
    puede seguir adjuntando el `.bat`.
    """
    return int(_cargar().get("bytes", 0) or 0) + sondeo_bytes()


def _avisar_si_toca(datos: dict[str, Any]) -> None:
    """Deja en el log el porcentaje, al cruzar los umbrales.

    Solo al cruzar, no en cada aviso: un aviso repetido cada 30 segundos deja de
    leerse, y entonces no sirve de nada el día que importa.
    """
    total = presupuesto_bytes()
    # Se mide sobre el **total** (Discord + sondeo) y no sobre los mensajes: el
    # sondeo es la partida grande, así que un aviso que lo ignore no avisa de
    # nada. Es justo el fallo que dejó el contador en 1,4 MB con el mes agotado.
    gastado = int(datos.get("bytes", 0) or 0) + sondeo_bytes()
    proporcion = gastado / total
    marca = f"aviso_{int(proporcion * 100 // 20) * 20}"
    if proporcion < AVISO_50 or datos.get("_ultima_marca") == marca:
        return
    datos["_ultima_marca"] = marca
    _guardar(datos)

    mb = gastado / 1024 / 1024
    tope = total / 1024 / 1024
    sondeo_mb = sondeo_bytes() / 1024 / 1024
    if proporcion >= 1:
        log.error(
            "SALIDA DE RED AGOTADA: %.0f de %.0f MB este mes (%.0f MB son sondeo "
            "de la API). Se dejan de adjuntar ficheros en los avisos (los avisos "
            "siguen saliendo) y la cadencia del barrido se estira sola. Revisa el "
            "panel de Render.",
            mb, tope, sondeo_mb,
        )
    elif proporcion >= AVISO_80:
        log.warning(
            "Salida de red al %.0f %% (%.0f de %.0f MB este mes; %.0f MB de "
            "sondeo).", proporcion * 100, mb, tope, sondeo_mb,
        )
    else:
        log.info(
            "Salida de red al %.0f %% (%.0f de %.0f MB este mes; %.0f MB de "
            "sondeo).", proporcion * 100, mb, tope, sondeo_mb,
        )


def puede_adjuntar(extra_bytes: int = 0) -> bool:
    """¿Queda presupuesto para seguir adjuntando ficheros este mes?

    Ante la duda devuelve `True`: es mejor pasarse un poco que quitarle a todo el
    mundo el `.bat` de espectar por un contador roto.
    """
    datos = _cargar()
    return datos["bytes"] + extra_bytes < presupuesto_bytes()


def estado() -> dict[str, Any]:
    """Los números del mes, para `/health`, para la cadencia y para el arranque.

    `mb` sigue siendo **solo Discord** porque es lo que decide si se puede
    adjuntar el `.bat`, y hay pruebas y llamantes que dependen de eso. Lo que hay
    que mirar para el límite del proveedor es `total_mb`.
    """
    datos = _cargar()
    total = presupuesto_bytes()
    sondeo = sondeo_bytes()
    discord = int(datos.get("bytes", 0) or 0)
    gastado = discord + sondeo
    return {
        "mes": datos["mes"],
        "mb": discord / 1024 / 1024,
        "sondeo_mb": sondeo / 1024 / 1024,
        "total_mb": gastado / 1024 / 1024,
        "tope_mb": total / 1024 / 1024,
        # El porcentaje que importa es el del total; `porcentaje` se mantiene
        # apuntando a Discord por la misma razón que `mb`.
        "porcentaje": (discord / total) * 100,
        "porcentaje_total": (gastado / total) * 100,
        "mensajes": datos["mensajes"],
        "adjuntos": datos["adjuntos"],
    }


def reiniciar() -> None:
    """Pone el contador a cero. Para las pruebas."""
    global _estado, _pendiente_sondeo
    _estado = {
        "mes": _mes_actual(), "bytes": 0, "mensajes": 0, "adjuntos": 0, "sondeo": 0,
    }
    with _lock:
        _pendiente_sondeo = 0

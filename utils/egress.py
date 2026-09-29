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
Es una **estimación**, y conviene saber de qué: el tamaño del JSON del embed más
el de los ficheros adjuntos más una envoltura por mensaje. No mide el handshake
de Discord ni las tramas del WebSocket, que son constantes y pequeñas. Sirve
para ver la tendencia y para cortar a tiempo, no para cuadrar la factura al
byte.

Lo que **no** cuenta: el tráfico de **entrada** (las descargas de la API de
Riot, los logos de dpm.lol). Render factura solo la salida, así que contarlo
asustaría sin motivo y haría tomar malas decisiones.

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
from datetime import datetime, timezone
from typing import Any

from utils.logger import get_logger

log = get_logger("utils.egress")

#: Dónde se guarda el acumulado. Va en `tracking/soloq/` y está en la lista de
#: `core/estado_remoto.ARCHIVOS`, así que sobrevive a reinicios y despliegues:
#: sin eso el contador volvería a cero en cada uno y no valdría para nada.
RUTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tracking", "soloq", "egress.json")

#: Presupuesto mensual en MB. **Por debajo de los 5 GB de Render a propósito**:
#: el margen es lo que evita que un pico de última hora provoque la suspensión
#: que ya pasó. Se puede subir con `EGRESS_PRESUPUESTO_MB` si algún día se paga
#: por más ancho de banda.
PRESUPUESTO_MB_DEFECTO = 4000

#: Lo que Discord añade a cada mensaje por fuera del embed (envoltura JSON,
#: nonce, referencias). Es una constante medida a ojo sobre envíos reales; para
#: una estimación de tendencia es suficiente.
ENVOLTURA_BYTES = 400

#: A partir de aquí se avisa en el log, y al llegar al 100 % se deja de adjuntar.
AVISO_50 = 0.5
AVISO_80 = 0.8

#: Estado en memoria. `None` = todavía no se ha leído del disco.
_estado: dict[str, Any] | None = None


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
    if _estado is not None:
        return _estado

    mes = _mes_actual()
    datos: dict[str, Any] = {"mes": mes, "bytes": 0, "mensajes": 0, "adjuntos": 0}
    try:
        with open(RUTA, encoding="utf-8") as fh:
            guardado = json.load(fh)
        if isinstance(guardado, dict) and guardado.get("mes") == mes:
            datos.update({k: int(guardado.get(k, 0) or 0)
                          for k in ("bytes", "mensajes", "adjuntos")})
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


def _avisar_si_toca(datos: dict[str, Any]) -> None:
    """Deja en el log el porcentaje, al cruzar los umbrales.

    Solo al cruzar, no en cada aviso: un aviso repetido cada 30 segundos deja de
    leerse, y entonces no sirve de nada el día que importa.
    """
    total = presupuesto_bytes()
    proporcion = datos["bytes"] / total
    marca = f"aviso_{int(proporcion * 100 // 20) * 20}"
    if proporcion < AVISO_50 or datos.get("_ultima_marca") == marca:
        return
    datos["_ultima_marca"] = marca
    _guardar(datos)

    mb = datos["bytes"] / 1024 / 1024
    tope = total / 1024 / 1024
    if proporcion >= 1:
        log.error(
            "SALIDA DE RED AGOTADA: %.0f de %.0f MB este mes. Se dejan de "
            "adjuntar ficheros en los avisos (los avisos siguen saliendo). "
            "Revisa el panel de Render.", mb, tope,
        )
    elif proporcion >= AVISO_80:
        log.warning("Salida de red al %.0f %% (%.0f de %.0f MB este mes).",
                    proporcion * 100, mb, tope)
    else:
        log.info("Salida de red al %.0f %% (%.0f de %.0f MB este mes).",
                 proporcion * 100, mb, tope)


def puede_adjuntar(extra_bytes: int = 0) -> bool:
    """¿Queda presupuesto para seguir adjuntando ficheros este mes?

    Ante la duda devuelve `True`: es mejor pasarse un poco que quitarle a todo el
    mundo el `.bat` de espectar por un contador roto.
    """
    datos = _cargar()
    return datos["bytes"] + extra_bytes < presupuesto_bytes()


def estado() -> dict[str, Any]:
    """Los números del mes, para `/health` y para el log de arranque."""
    datos = _cargar()
    total = presupuesto_bytes()
    return {
        "mes": datos["mes"],
        "mb": datos["bytes"] / 1024 / 1024,
        "tope_mb": total / 1024 / 1024,
        "porcentaje": (datos["bytes"] / total) * 100,
        "mensajes": datos["mensajes"],
        "adjuntos": datos["adjuntos"],
    }


def reiniciar() -> None:
    """Pone el contador a cero. Para las pruebas."""
    global _estado
    _estado = {"mes": _mes_actual(), "bytes": 0, "mensajes": 0, "adjuntos": 0}

"""Estado de salud de las fuentes de datos del bot.

Por qué hace falta
------------------
El bot vive de tres fuentes externas y ninguna avisa cuando deja de
funcionar:

* **Riot API** — partidas en curso y Elo.
* **dpm.lol** — plantillas de los equipos, leaderboards, historial, pickrates.
* **lolesports** — calendario y partidos profesionales.

Si dpm.lol cambia el formato o Cloudflare empieza a bloquear, el bot **sigue
respondiendo**: usa lo último que tenga en disco. Eso es lo correcto —mejor
datos de ayer que un error— pero significa que una avería puede durar días sin
que nadie se entere. El usuario lo dijo tal cual: *"ojo con eso no me vayas a
estar tomando data y despues se rompa"*.

Este módulo es un registro en memoria: cada tarea apunta si su última pasada fue
bien o mal. Con eso, `/health` puede decir "las plantillas se actualizaron hace
2 días" en vez de callarse.

Deliberadamente **no persiste**. Al reiniciar se vacía, y eso es lo que se
quiere: lo que interesa es si las fuentes van *ahora*, no un historial.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from utils.logger import get_logger

log = get_logger("core.salud")

#: Clave de traducción del nombre legible de cada fuente, en el orden en que se
#: muestran. Antes era el nombre en español directamente; se pasa por i18n
#: porque `/health` es público y lo lee cualquiera del servidor. `dpm.lol`,
#: `lolesports` y `Riot` son nombres propios y no se traducen.
FUENTES = {
    "riot": "salud.fuente_riot",
    "pasada": "salud.fuente_pasada",
    "cuentas": "salud.fuente_cuentas",
    "leaderboard": "salud.fuente_leaderboard",
    "historial": "salud.fuente_historial",
    "pickrates": "salud.fuente_pickrates",
    "esports": "salud.fuente_esports",
}


def nombre_fuente(clave: str, idioma: str | None = None) -> str:
    """Nombre legible de una fuente. Si no se conoce, la propia clave."""
    from utils.i18n import t

    entrada = FUENTES.get(clave)
    return t(entrada, idioma) if entrada else clave


@dataclass
class Estado:
    """Lo que se sabe de una fuente."""

    ok: bool | None = None          # None = todavía no se ha intentado
    detalle: str = ""
    ultimo_ok: float | None = None
    ultimo_fallo: float | None = None
    fallos_seguidos: int = 0
    intentos: int = 0

    def edad_ok(self) -> float | None:
        """Segundos desde el último éxito, o None si nunca hubo uno."""
        return None if self.ultimo_ok is None else time.time() - self.ultimo_ok


_estados: dict[str, Estado] = {}


def registrar(fuente: str, ok: bool, detalle: str = "") -> None:
    """Apunta el resultado de una pasada.

    Se llama desde las tareas de fondo y desde los comandos que consultan una
    fuente directamente. No lanza nunca: un fallo aquí no debe tumbar a quien lo
    llama.
    """
    try:
        estado = _estados.setdefault(fuente, Estado())
        estado.ok = ok
        estado.detalle = detalle
        estado.intentos += 1
        ahora = time.time()
        if ok:
            estado.ultimo_ok = ahora
            # Solo se avisa de la recuperación si de verdad estaba caída, para
            # no llenar el log de "vuelve a funcionar" cada media hora.
            if estado.fallos_seguidos >= 3:
                log.info(
                    "%s vuelve a funcionar tras %d fallos.",
                    nombre_fuente(fuente), estado.fallos_seguidos,
                )
            estado.fallos_seguidos = 0
        else:
            estado.ultimo_fallo = ahora
            estado.fallos_seguidos += 1
            # Tres seguidos ya no es mala suerte: es una avería.
            if estado.fallos_seguidos == 3:
                log.warning(
                    "%s ha fallado 3 veces seguidas (%s). Se seguirán usando los "
                    "datos guardados.",
                    nombre_fuente(fuente), detalle or "sin detalle",
                )
    except Exception:  # pragma: no cover - el registro nunca debe estorbar
        log.debug("No se pudo registrar la salud de %s", fuente)


def estado_de(fuente: str) -> Estado:
    return _estados.get(fuente, Estado())


def todo() -> dict[str, Estado]:
    """Todas las fuentes conocidas, incluidas las que aún no se han probado."""
    return {clave: _estados.get(clave, Estado()) for clave in FUENTES}


def hay_averias(idioma: str | None = None) -> list[str]:
    """Fuentes con 3 o más fallos seguidos, ya con su nombre legible."""
    return [
        nombre_fuente(c, idioma)
        for c, e in _estados.items()
        if e.fallos_seguidos >= 3
    ]


# ---------------------------------------------------------------------- #
# Presentación
# ---------------------------------------------------------------------- #

def _humano(segundos: float, idioma: str | None = None) -> str:
    from utils.i18n import t

    if segundos < 60:
        return t("salud.hace_segundos", idioma, n=int(segundos))
    if segundos < 3600:
        return t("salud.hace_minutos", idioma, n=int(segundos // 60))
    if segundos < 86400:
        return t("salud.hace_horas", idioma, n=int(segundos // 3600))
    return t("salud.hace_dias", idioma, n=int(segundos // 86400))


def icono(estado: Estado) -> str:
    if estado.ok is None:
        return "⚪"
    if estado.ok:
        return "🟢"
    return "🔴" if estado.fallos_seguidos >= 3 else "🟡"


def linea(clave: str, estado: Estado, idioma: str | None = None) -> str:
    """Una línea de `/health`, ya redactada."""
    from utils.i18n import t

    nombre = nombre_fuente(clave, idioma)
    if estado.ok is None:
        return t("salud.sin_comprobar", idioma, nombre=nombre)

    edad = estado.edad_ok()
    cuando = _humano(edad, idioma) if edad is not None else t("salud.nunca", idioma)

    if estado.ok:
        return t("salud.al_dia", idioma, nombre=nombre, cuando=cuando)

    # El detalle lo escribe la tarea que registró el fallo, así que va en
    # español: es un dato de operador que se cuela en una superficie pública.
    detalle = f" · {estado.detalle}" if estado.detalle else ""
    return t(
        "salud.con_fallos", idioma,
        icono=icono(estado), nombre=nombre,
        fallos=estado.fallos_seguidos, detalle=detalle, cuando=cuando,
    )

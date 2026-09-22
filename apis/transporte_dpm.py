# apis/transporte_dpm.py
"""Cliente HTTP para dpm.lol, con **dos** transportes y respaldo automático.

Por qué dos
-----------
dpm.lol está detrás de Cloudflare, y **desde una IP de datacenter no deja pasar
con cloudscraper**. Medido en el servicio de Render (22-09-2026), con los logs
delante:

    ERROR | accounts_from_leaderboard | El leaderboard devolvió 0 cuentas
    ERROR | leagues                    | La liga 'lec' no devolvió leaderboard
    INFO  | historial_warm             | Historial precalentado: 0/352 cuentas (352 fallos)

Desde una IP doméstica sí pasa, y por eso el fallo no se ve en local: es un
problema de **accesibilidad**, no de velocidad.

`curl_cffi` imita la huella TLS/JA3 y HTTP/2 de un Chrome real, que es justo lo
que mira Cloudflare, y sí pasa desde el datacenter.

Lo que ya se había medido, y por qué no bastaba
-----------------------------------------------
Antes se midió curl_cffi contra cloudscraper para ver si convenía cambiar el
transporte, y dio **empate** (una liga entera: 16,7/15,4/14,6 s contra
15,9/14,7/15,5 s). Pero eso medía **latencia desde casa**, donde los dos pasan.
Lo que no se había medido es si el segundo **llega**, y ahí está la diferencia.

Por qué respaldo y no reemplazo
-------------------------------
Porque cloudscraper **funciona hoy** en la mayoría de los sitios y no añade una
dependencia dura: si curl_cffi no está instalado, esto se comporta exactamente
como antes. Y si algún día cloudscraper deja de pasar también desde casa, el
respaldo ya está puesto.

Cuándo se cambia de transporte
------------------------------
1. Si la petición lanza una excepción.
2. Si el estado no es 200.
3. Si el cuerpo parece un **desafío de Cloudflare** (eso es lo que llega en vez
   del HTML o del JSON cuando bloquea).
4. Si quien llama dice que el cuerpo **no le sirve** (`valido`): un 200 con el
   HTML correcto pero sin los datos dentro, que es el caso de "0 jugadores".
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

import cloudscraper

from utils.logger import get_logger

log = get_logger("apis.transporte_dpm")

TIMEOUT_POR_DEFECTO = 25.0

#: Señales de que Cloudflare ha contestado con un desafío en vez del contenido.
#: Si aparece alguna, el cuerpo no sirve aunque el estado sea 200.
_SENALES_DESAFIO = (
    "just a moment",
    "attention required",
    "cf-chl",
    "cf_chl_opt",
    "checking your browser",
    "enable javascript and cookies",
)

_lock = threading.Lock()
_scraper = None
_sesion_cffi: Any = None
_cffi_disponible: bool | None = None

#: Cuántas veces ha hecho falta el respaldo desde que arrancó el proceso. Sirve
#: para verlo en el log sin tener que rebuscar entre líneas.
_veces_respaldo = 0


class Respuesta:
    """Lo mínimo que necesitan los que llaman: estado, texto y JSON."""

    __slots__ = ("status", "text", "transporte")

    def __init__(self, status: int, text: str, transporte: str) -> None:
        self.status = status
        self.text = text
        self.transporte = transporte

    def json(self) -> Any:
        import json

        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


def _cliente_cloudscraper():
    global _scraper
    with _lock:
        if _scraper is None:
            # `delay=10` es la espera entre reintentos del desafío de Cloudflare.
            _scraper = cloudscraper.create_scraper(
                browser={"custom": "Chrome"}, delay=10
            )
        return _scraper


def _cliente_cffi():
    """La sesión de curl_cffi, o `None` si no está instalada.

    Se comprueba **una sola vez**: si no está, no tiene sentido volver a intentar
    el import en cada petición.
    """
    global _sesion_cffi, _cffi_disponible
    with _lock:
        if _cffi_disponible is False:
            return None
        if _sesion_cffi is None:
            try:
                from curl_cffi import requests as _cffi

                _sesion_cffi = _cffi.Session(impersonate="chrome")
                _cffi_disponible = True
                log.info("dpm.lol: respaldo con curl_cffi disponible.")
            except Exception as exc:
                _cffi_disponible = False
                log.info("dpm.lol: sin curl_cffi (%s); solo cloudscraper.", exc)
                return None
        return _sesion_cffi


def _parece_desafio(texto: str) -> bool:
    bajo = (texto or "")[:4000].lower()
    return any(s in bajo for s in _SENALES_DESAFIO)


def _pedir_una(url: str, timeout: float, transporte: str) -> Respuesta | None:
    """Una petición con un transporte concreto. `None` si ni se pudo intentar."""
    try:
        if transporte == "curl_cffi":
            sesion = _cliente_cffi()
            if sesion is None:
                return None
            resp = sesion.get(url, impersonate="chrome", timeout=timeout)
        else:
            resp = _cliente_cloudscraper().get(url, timeout=timeout)
    except Exception as exc:
        log.debug("dpm.lol (%s) falló en %s: %s", transporte, url, exc)
        return None

    texto = getattr(resp, "text", "") or ""
    return Respuesta(int(getattr(resp, "status_code", 0) or 0), texto, transporte)


def _sirve(resp: Respuesta | None, valido: Callable[[str], bool] | None) -> bool:
    if resp is None or resp.status != 200:
        return False
    if not resp.text:
        return False
    if _parece_desafio(resp.text):
        return False
    if valido is not None:
        try:
            return bool(valido(resp.text))
        except Exception:
            return False
    return True


def pedir(
    url: str,
    timeout: float = TIMEOUT_POR_DEFECTO,
    valido: Callable[[str], bool] | None = None,
) -> Respuesta | None:
    """GET con **curl_cffi** y, si no sirve, con cloudscraper.

    Orden invertido el 22-09-2026 (antes iba cloudscraper primero). El motivo está
    medido en los logs de Render: cloudscraper recibe **403 de Cloudflare en todas
    las peticiones** desde la IP del datacenter, así que como principal solo servía
    para gastar el doble de peticiones (la que falla y la que sirve), tardar el
    doble y agotar el pool de conexiones del scraper — de ahí los
    `Connection pool is full, discarding connection: dpm.lol`.

    curl_cffi pasa siempre, y desde casa también. Se queda de respaldo por si algún
    día es al revés: es una librería más nueva y no está de más tener dos caminos.
    """
    principal = _pedir_una(url, timeout, "curl_cffi")
    if _sirve(principal, valido):
        return principal

    respaldo = _pedir_una(url, timeout, "cloudscraper")
    if _sirve(respaldo, valido):
        with _lock:
            global _veces_respaldo
            _veces_respaldo += 1
            veces = _veces_respaldo
        if veces <= 5 or veces % 50 == 0:
            log.warning(
                "dpm.lol: curl_cffi no sirvió (estado %s); respondió cloudscraper "
                "(van %d respaldos).",
                principal.status if principal else "sin respuesta", veces,
            )
        return respaldo

    return respaldo or principal


def resumen() -> str:
    """Para el log de arranque: qué transportes hay y cuántas veces hizo falta el respaldo."""
    cffi = "sí" if _cliente_cffi() is not None else "no instalado"
    return f"curl_cffi ({cffi}) + cloudscraper de respaldo · respaldos usados: {_veces_respaldo}"

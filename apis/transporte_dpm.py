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

import os
import threading
import time
from typing import Any, Callable
from urllib.parse import quote

import cloudscraper

from utils.logger import get_logger

log = get_logger("apis.transporte_dpm")

TIMEOUT_POR_DEFECTO = 25.0

#: Relay propio en un Worker de Cloudflare (ver `infra/relay-dpm/`). Vacío = no
#: se usa. Existe porque dpm.lol contesta **403 a las IPs de datacenter** y la
#: red de Cloudflare es la única que está dentro de esa protección: desde Render
#: el bloqueo es del 100 %, desde un runner de GitHub de 5 de cada 6, y desde una
#: IP doméstica ninguna.
#:
#: Con esto configurado se prueba **primero** el relay: desde Render los otros
#: dos caminos van a fallar siempre, así que intentarlos antes es gastar dos
#: peticiones y una espera de reintento por cada ficha.
RELAY_URL = (os.getenv("DPM_RELAY_URL") or "").strip().rstrip("/")
RELAY_CLAVE = (os.getenv("DPM_RELAY_SECRET") or "").strip()

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

#: Fallos del relay desde que arrancó el proceso, y el último motivo. Van
#: aparte del contador de bloqueos porque un relay roto **no** es un bloqueo de
#: dpm.lol: el bot sigue funcionando por el camino de siempre y lo único que se
#: pierde es la ventaja. Pero sin decirlo, un relay mal configurado es
#: indistinguible de no tenerlo.
_veces_fallo_relay = 0
_ultimo_fallo_relay = ""

#: Cuántos fallos **seguidos** del relay hacen falta para ponerlo en cuarentena,
#: y cuánto dura. El relay se probó el 01-11-2026 y dpm.lol contestaba al Worker
#: la página de desafío de Cloudflare («Just a moment…») en el 100 % de las
#: peticiones: las subpeticiones de un Worker salen por un pool de IPs compartido
#: que también está marcado. Sin cuarentena, cada ficha de cada liga pagaba un
#: viaje al relay para nada — medido, 1 800 fallos en una hora.
#:
#: La cuarentena es larga a propósito: lo que puede cambiar es la reputación de
#: ese pool, y eso se mueve en horas, no en minutos. Y no es permanente: si dpm
#: afloja, la primera petición tras la cuarentena vuelve a entrar sola.
CUARENTENA_RELAY = 1800.0
FALLOS_PARA_CUARENTENA = 3

_relay_fallos_seguidos = 0
_relay_en_cuarentena_hasta = 0.0


def relay_en_cuarentena() -> bool:
    """¿Está el relay apartado por fallar seguido?"""
    return _relay_en_cuarentena_hasta > 0 and time.time() < _relay_en_cuarentena_hasta


def _anotar_fallo_relay(motivo: str) -> None:
    """Deja constancia de un fallo del relay, sin inundar el log.

    Las tres primeras veces se cuentan enteras (es cuando se está montando y hay
    que ver el motivo); después, una de cada 200, que basta para saber que sigue
    roto sin llenar la consola de Render. Al tercer fallo **seguido** el relay
    entra en cuarentena y deja de intentarse, que es lo que evita que un relay
    inútil encarezca cada petición del bot.
    """
    global _veces_fallo_relay, _ultimo_fallo_relay
    global _relay_fallos_seguidos, _relay_en_cuarentena_hasta
    with _lock:
        _veces_fallo_relay += 1
        veces = _veces_fallo_relay
        _ultimo_fallo_relay = motivo
        _relay_fallos_seguidos += 1
        if _relay_fallos_seguidos >= FALLOS_PARA_CUARENTENA and not relay_en_cuarentena():
            _relay_en_cuarentena_hasta = time.time() + CUARENTENA_RELAY
            cuarentena = True
        else:
            cuarentena = False
    if cuarentena:
        log.warning(
            "dpm.lol: el relay lleva %d fallos seguidos (%s). En cuarentena %.0f "
            "minutos: se sigue por curl_cffi/cloudscraper y se reintenta el relay "
            "después.",
            _relay_fallos_seguidos, motivo, CUARENTENA_RELAY / 60,
        )
    elif veces <= 3 or veces % 200 == 0:
        log.warning(
            "dpm.lol: el relay falló (%s). Se sigue por curl_cffi/cloudscraper "
            "(van %d fallo(s) del relay).", motivo, veces,
        )


def _anotar_relay_bueno() -> None:
    """Un 200 del relay rompe la racha y levanta la cuarentena."""
    global _relay_fallos_seguidos, _relay_en_cuarentena_hasta
    with _lock:
        _relay_fallos_seguidos = 0
        _relay_en_cuarentena_hasta = 0.0

#: Cuándo se vio el último **bloqueo de Cloudflare** (los dos transportes
#: rechazados a la vez) y cuántas veces ha pasado. Existe porque el 01-11-2026 el
#: sintoma era indistinguible de un fallo de código: 403 en las ocho plataformas,
#: cero cuentas, y ni una línea diciendo «me están bloqueando».
_ultimo_bloqueo = 0.0
_bloqueos = 0

#: Cuándo se sirvió bien la última petición. Va con `_ultimo_bloqueo` porque
#: **un 403 suelto no es un muro**: desde los runners de GitHub, dpm.lol contesta
#: 403 a ~16 % de las peticiones y sirve el resto (medido el 01-11-2026, 8 de 49
#: fichas necesitaron reintento). Mirar solo el último bloqueo hacía que el
#: refresco de rosters se plantara tras la primera petición fallida y diera por
#: bloqueadas las 20 ligas que quedaban.
_ultimo_ok = 0.0

#: Cuánto se considera que un bloqueo sigue vigente. Durante ese rato no se
#: insiste: desde la misma IP, todas las peticiones van a fallar igual, y cada
#: intento cuesta una conexión y una espera de reintento.
BLOQUEO_VIGENTE = 600.0


def bloqueado_recientemente(segundos: float = BLOQUEO_VIGENTE) -> bool:
    """¿Está la IP **bloqueada de verdad** ahora mismo?

    Lo consultan los que hacen **muchas** peticiones seguidas (el leaderboard de
    ocho plataformas, la rotación de rosters) para no encadenar fallos idénticos.

    Y «de verdad» es lo que separa este método de «hubo un 403 hace un rato»:
    solo cuenta como bloqueo si **la última respuesta fue mala**. Si después del
    último 403 hubo alguna buena, lo que hubo fue un tropezón de Cloudflare y hay
    que seguir. La diferencia no es teórica: desde Render la IP está bloqueada al
    100 % (ninguna respuesta buena, `True` siempre), y desde un runner de GitHub
    el 16 % de las peticiones recibe 403 y el resto pasa (`False`, seguir). Antes
    de esto, el refresco de rosters en el runner se plantaba en la primera liga y
    daba por bloqueadas las otras 20.
    """
    if not (_ultimo_bloqueo > 0 and (time.time() - _ultimo_bloqueo) < segundos):
        return False
    return _ultimo_bloqueo > _ultimo_ok



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


def _pedir_por_relay(url: str, timeout: float) -> Respuesta | None:
    """La misma petición, pero saliendo por el Worker de Cloudflare.

    `None` si no hay relay configurado o si ni se pudo intentar. **No** anota
    bloqueo: que falle el relay no dice nada de dpm.lol.
    """
    if not RELAY_URL:
        return None
    if relay_en_cuarentena():
        return None

    import requests  # ya es dependencia del proyecto; se importa aquí para no
    # cargarla en los procesos que solo usan curl_cffi.

    cabeceras = {"x-relay-key": RELAY_CLAVE} if RELAY_CLAVE else {}
    try:
        resp = requests.get(
            f"{RELAY_URL}/?u={quote(url, safe='')}",
            headers=cabeceras,
            timeout=timeout,
        )
    except Exception as exc:
        # A `warning` y no a `debug`: si el relay está mal configurado, el bot
        # sigue funcionando por el camino de siempre y el único síntoma es «hay
        # 403 otra vez». Sin esta línea en el log de Render no hay forma de
        # distinguir «el relay no está puesto» de «el relay está roto».
        _anotar_fallo_relay(f"no se pudo llamar ({type(exc).__name__}: {exc})")
        return None

    if resp.status_code != 200:
        cuerpo = (resp.text or "").strip()[:80]
        if cuerpo == "forbidden":
            _anotar_fallo_relay("la clave no coincide (el Worker contesta 'forbidden')")
        elif "just a moment" in (resp.text or "").lower():
            _anotar_fallo_relay("dpm.lol contesta el desafío de Cloudflare al Worker")
        else:
            _anotar_fallo_relay(f"HTTP {resp.status_code} {cuerpo}".strip())
    else:
        _anotar_relay_bueno()
    return Respuesta(resp.status_code, resp.text or "", "relay")


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

    Y si hay `DPM_RELAY_URL` configurado, el **relay va primero**. No es un atajo
    cosmético: desde el 01-11-2026 dpm.lol contesta 403 a la IP de Render en el
    100 % de las peticiones, así que intentar curl_cffi antes son dos peticiones
    perdidas y una espera de reintento por cada ficha, y con 50 fichas por liga
    eso se nota. Si el relay falla, se sigue con los locales de siempre.
    """
    if RELAY_URL:
        por_relay = _pedir_por_relay(url, timeout)
        if _sirve(por_relay, valido):
            _anotar_buena()
            return por_relay

    principal = _pedir_una(url, timeout, "curl_cffi")
    if _sirve(principal, valido):
        _anotar_buena()
        return principal

    respaldo = _pedir_una(url, timeout, "cloudscraper")
    if _sirve(respaldo, valido):
        _anotar_buena()
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

    _anotar_bloqueo(url, principal, respaldo)
    return respaldo or principal


def _anotar_buena() -> None:
    """Apunta que dpm.lol **sí** nos atendió. Ver `_ultimo_ok`."""
    global _ultimo_ok
    _ultimo_ok = time.time()


def _anotar_bloqueo(url: str, principal: Respuesta | None, respaldo: Respuesta | None) -> None:
    """Apunta un bloqueo cuando **los dos** transportes fueron rechazados.

    Distinguir «Cloudflare nos cierra la puerta» de «el código está mal» es la
    mitad del diagnóstico. Desde el 01-11-2026 la IP de Render recibe 403 con
    curl_cffi y cloudscraper a la vez, y eso no se arregla escribiendo código:
    hay que saber que es eso y no un selector roto.
    """
    global _ultimo_bloqueo, _bloqueos

    estados = [
        r.status if r is not None else 0 for r in (principal, respaldo)
    ]
    desafio = any(
        r is not None and r.status == 200 and _parece_desafio(r.text)
        for r in (principal, respaldo)
    )
    # 403 (y el 503 de "Under Attack") es como Cloudflare dice «no» a una IP que
    # no le gusta, con los dos transportes. Un 500 no: ese sí es del servidor.
    if not desafio and not any(e in (403, 503) for e in estados):
        return

    with _lock:
        primero = _bloqueos == 0
        _bloqueos += 1
        _ultimo_bloqueo = time.time()
        veces = _bloqueos
    if primero:
        log.error(
            "dpm.lol está BLOQUEANDO esta IP (estados %s; %d bloqueo(s)). "
            "No es un fallo del cliente: desde una IP de datacenter Cloudflare "
            "contesta 403 aunque se imite la huella de Chrome. Los datos no se "
            "pueden bajar desde aquí; el censo que ya está en disco se sigue "
            "usando. Ver DESPLIEGUE.md §8.",
            "/".join(str(e) for e in estados), veces,
        )
    elif veces % 25 == 0:
        log.warning("dpm.lol sigue bloqueando esta IP (%d bloqueos).", veces)


def resumen() -> str:
    """Para el log de arranque: qué transportes hay y cuántas veces hizo falta el respaldo.

    El relay va **el primero** en la frase porque es el que se usa primero. Sin
    esta línea, un `DPM_RELAY_URL` vacío y uno que no llega se ven igual en el
    log: los dos acaban en 403 desde Render, que es justo la confusión que costó
    una tarde.
    """
    cffi = "sí" if _cliente_cffi() is not None else "no instalado"
    relay = RELAY_URL or "sin configurar"
    if RELAY_URL and not RELAY_CLAVE:
        relay += " (SIN CLAVE: dpm.lol contestará 'forbidden')"
    texto = (
        f"relay ({relay}) -> curl_cffi ({cffi}) + cloudscraper de respaldo · "
        f"respaldos usados: {_veces_respaldo}"
    )
    if _veces_fallo_relay:
        texto += f" · fallos del relay: {_veces_fallo_relay} (último: {_ultimo_fallo_relay})"
    if relay_en_cuarentena():
        faltan = max(0.0, _relay_en_cuarentena_hasta - time.time())
        texto += f" · RELAY EN CUARENTENA {faltan / 60:.0f} min más"
    if _bloqueos:
        texto += f" · BLOQUEOS de Cloudflare: {_bloqueos}"
    return texto

# core/disparar_rosters.py
"""Le pide a GitHub que refresque los rosters, porque el bot no puede.

Por qué existe
--------------
Desde el 01-11-2026 dpm.lol contesta 403 a la IP de Render (reputación de IP:
desde una IP doméstica pasa, desde el datacenter no). Los rosters solo se pueden
bajar desde fuera, y el único sitio fuera que tenemos es un runner de GitHub.

El bot, en cambio, es el único que sabe **cuándo** el censo se está quedando
viejo: lo lleva en disco y lo compara con el reloj. Así que en vez de que un
tercero adivine la cadencia, el bot pide la pasada cuando hace falta.

Por qué no basta el `schedule` del workflow
-------------------------------------------
Medido el 01-11-2026 sobre el historial entero del repo: 21 ejecuciones, **todas**
por `push` o lanzadas a mano, y **cero** con evento `schedule`. El `cron:` del
workflow no ha disparado ni una vez, así que la vía "cada hora" no existía de
verdad y el censo solo se refrescaba cuando alguien subía código. Esto no depende
de ese cron: es una petición explícita por la API.

Qué hace falta
--------------
El `GITHUB_TOKEN` de siempre, **el mismo que ya escribe la rama de estado**. Se
manda un `repository_dispatch`, que GitHub acepta con `Contents: write`.

Se probó antes con `workflow_dispatch`, que es lo natural para lanzar un workflow
a mano, y **no vale**: exige el permiso `Actions: Read and write` y con el token
del bot contesta 403 `Resource not accessible by personal access token`. El
`repository_dispatch` hace lo mismo con el permiso que ya tenemos, así que no hay
nada que configurar ni que tocar en la pantalla de GitHub.

Sin token esto solo escribe un aviso en el log: no rompe nada.

Qué NO hace
-----------
No scrapea, no publica y no toca la rama de estado. Solo pide la pasada; el
runner es quien scrapea y publica, y el bot se baja el resultado en su ciclo de
siempre (`sincronizar_censo_remoto`).
"""

from __future__ import annotations

import json
import os
import time

import aiohttp

import config
from utils.logger import get_logger

log = get_logger(__name__)

#: El workflow que hace el scraping desde el runner.
WORKFLOW = "refrescar-rosters.yml"

#: El `event_type` que escucha el workflow (`on.repository_dispatch.types`).
EVENTO = "refrescar-rosters"

#: Dos peticiones seguidas no sirven de nada: el runner tarda un par de minutos
#: en publicar, y mientras tanto el censo sigue viejo. Sin esto, un ciclo corto
#: pediría la pasada en cada vuelta y llenaría el historial de Actions de
#: ejecuciones que se saltan solas por el freno del script.
MINUTOS_ENTRE_PEDIDOS = float(os.getenv("ROSTERS_MINUTOS_ENTRE_PEDIDOS", "30"))

_ultimo_pedido = 0.0
#: Para no repetir el mismo aviso cada vuelta cuando falta el permiso.
_avisado_sin_permiso = False


def disponible() -> bool:
    """`True` si hay con qué pedirlo (token y repo configurados)."""
    return bool(config.GITHUB_TOKEN and config.GITHUB_REPO)


def edad_horas() -> float | None:
    """Horas desde que se escribió el censo que hay en disco, o `None` si no hay.

    Se lee `escrito_en`, que lo pone quien lo publica (el workflow o el PC), no la
    fecha del fichero: al arrancar en un host con disco efímero el fichero se
    acaba de crear y su fecha diría "recién hecho" aunque el contenido sea de
    hace tres días.
    """
    from core import estado_remoto

    ruta = config.BASE_DIR / estado_remoto.CENSO
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        log.warning("El censo de disco no se pudo leer; se cuenta como viejo.")
        return None

    escrito = datos.get("escrito_en")
    if not escrito:
        return None
    try:
        # `datetime.fromisoformat` acepta el `+00:00` que escribe el workflow.
        from datetime import datetime, timezone

        cuando = datetime.fromisoformat(escrito)
        if cuando.tzinfo is None:
            cuando = cuando.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - cuando).total_seconds() / 3600.0
    except Exception:
        log.warning("`escrito_en` del censo no es una fecha: %r", escrito)
        return None


async def pedir(motivo: str) -> bool:
    """Pide una pasada del workflow. `True` si GitHub la aceptó.

    No lanza: si falla, el bot sigue barriendo con el censo que tenga.
    """
    global _ultimo_pedido, _avisado_sin_permiso

    if not disponible():
        return False

    ahora = time.time()
    if _ultimo_pedido and ahora - _ultimo_pedido < MINUTOS_ENTRE_PEDIDOS * 60:
        log.debug(
            "Rosters: ya se pidió una pasada hace %.0f min; no se repite.",
            (ahora - _ultimo_pedido) / 60,
        )
        return False

    url = f"https://api.github.com/repos/{config.GITHUB_REPO}/dispatches"
    cabeceras = {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with aiohttp.ClientSession() as sesion:
            async with sesion.post(
                url,
                headers=cabeceras,
                json={"event_type": EVENTO},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                estado = resp.status
                if estado == 204:
                    _ultimo_pedido = ahora
                    _avisado_sin_permiso = False
                    log.info("Rosters: pasada pedida a GitHub (%s).", motivo)
                    return True
                cuerpo = (await resp.text())[:200]
    except Exception as exc:
        # Sin red no hay nada que hacer, y no es un problema del bot.
        log.warning("Rosters: no se pudo pedir la pasada a GitHub: %s", exc)
        return False

    if estado == 403:
        # El token sirve para escribir la rama de estado pero no para esto: le
        # falta `Contents: write` (o el repo es de otra cuenta). Es el fallo que
        # se ve cuando el token es de solo lectura.
        if not _avisado_sin_permiso:
            _avisado_sin_permiso = True
            log.warning(
                "Rosters: el token de GitHub no puede lanzar el evento (403). "
                "Necesita 'Contents: Read and write' sobre el repo; mientras "
                "tanto el censo solo se refresca al subir código."
            )
        else:
            log.debug("Rosters: sigue sin permiso para lanzar el evento (403).")
        return False

    log.warning("Rosters: GitHub rechazó la petición (HTTP %s): %s", estado, cuerpo)
    return False

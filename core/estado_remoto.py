# core/estado_remoto.py
"""Guarda el estado del bot en una rama de GitHub, y lo recupera al arrancar.

Por qué existe
--------------
El estado que el bot escribe en marcha —a quién sigue cada persona, qué canales
reciben avisos, qué planes se han dado a mano, qué partidas ya se avisaron— son
ficheros dentro del proyecto. En un host con **disco efímero** (el plan gratuito
de Render) cada reinicio los borra: las suscripciones de la gente desaparecen sin
ningún error, y el síntoma es "el bot dejó de avisarme y no sé por qué". Pasó de
verdad el 22-09-2026, y costó un rato encontrarlo.

Con esto el bot sube esos ficheros a una **rama aparte** del repositorio y los
recupera al arrancar.

Por qué una rama aparte y no `main`
-----------------------------------
Porque subir a `main` dispara el despliegue automático del host, y eso sería un
bucle: subir estado → redesplegar → reiniciar → volver a subir. En una rama que
nadie despliega, el estado viaja sin tocar la aplicación. Además el historial de
`main` no se llena de commits de estado.

Qué NO se sube
--------------
Los ficheros grandes y reconstruibles: `accounts_from_teams.json` (2,5 MB de
rosters), `accounts.json` (la escalera) y `ranked_data.json`. Subirlos daría
commits de megas cada pocas horas, y los tres se pueden volver a bajar solos (la
siembra de rosters, la escalera semanal y `rank_warm`). Lo que se sube es lo que
**no se puede reconstruir**: lo que la gente pidió.

Sin `GITHUB_TOKEN` configurado esto no hace nada y el bot funciona igual — solo
que el estado se pierde al reiniciar, que es como estaba antes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import aiohttp

import config
from utils.logger import get_logger

log = get_logger("core.estado_remoto")

BASE_DIR = Path(__file__).resolve().parent.parent

#: Los ficheros que se guardan fuera, en orden. Son pequeños (unos pocos kB en
#: total) y **no se pueden reconstruir**: si se pierden, se pierde lo que pidió
#: la gente.
ARCHIVOS: tuple[str, ...] = (
    "tracking/soloq/users_config.json",
    "tracking/soloq/announced_games.json",
    "tracking/soloq/notify_config.json",
    "tracking/soloq/plans_users.json",
)

API = "https://api.github.com"

#: `sha1` del último contenido subido, por fichero. Evita subir lo que no cambió:
#: sin esto serían commits cada 5 minutos aunque nadie hubiera hecho nada.
_ultimo_subido: dict[str, str] = {}


def activo() -> bool:
    return bool(config.GITHUB_TOKEN and config.GITHUB_REPO)


def _cabeceras() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _sha(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


async def _api(sesion, metodo: str, ruta: str, **kwargs):
    """Una llamada a la API de GitHub. Devuelve `(estado, json_o_None)`."""
    url = ruta if ruta.startswith("http") else f"{API}{ruta}"
    try:
        async with sesion.request(metodo, url, headers=_cabeceras(), **kwargs) as resp:
            if resp.status == 204:
                return resp.status, None
            try:
                return resp.status, await resp.json()
            except Exception:
                return resp.status, None
    except Exception as exc:
        log.warning("GitHub: fallo de red en %s %s: %s", metodo, ruta, exc)
        return 0, None


async def _asegurar_rama(sesion) -> bool:
    """Crea la rama de estado si no existe. `True` si está lista."""
    ruta = f"/repos/{config.GITHUB_REPO}/git/ref/heads/{config.GITHUB_RAMA_ESTADO}"
    estado, _ = await _api(sesion, "GET", ruta)
    if estado == 200:
        return True

    # No existe: se crea apuntando a donde esté la rama por defecto.
    estado, datos = await _api(sesion, "GET", f"/repos/{config.GITHUB_REPO}")
    if estado != 200 or not datos:
        return False
    por_defecto = datos.get("default_branch") or "main"

    estado, datos = await _api(
        sesion, "GET", f"/repos/{config.GITHUB_REPO}/git/ref/heads/{por_defecto}"
    )
    if estado != 200 or not datos:
        return False
    sha = (datos.get("object") or {}).get("sha")
    if not sha:
        return False

    estado, _ = await _api(
        sesion,
        "POST",
        f"/repos/{config.GITHUB_REPO}/git/refs",
        json={"ref": f"refs/heads/{config.GITHUB_RAMA_ESTADO}", "sha": sha},
    )
    if estado in (200, 201):
        log.info("GitHub: rama '%s' creada para el estado.", config.GITHUB_RAMA_ESTADO)
        return True
    log.warning("GitHub: no se pudo crear la rama '%s' (HTTP %s).", config.GITHUB_RAMA_ESTADO, estado)
    return False


def _escribir(ruta: Path, texto: str) -> None:
    """Escritura atómica, como el resto del proyecto."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ruta)


async def restaurar() -> int:
    """Baja el estado de la rama y lo deja en disco. Devuelve cuántos ficheros.

    Se llama **al arrancar, antes de que empiecen las tareas**: si el estado se
    restaurara después, una pasada del tracker podría avisar de algo ya avisado
    (el registro de avisos es uno de los ficheros) o perderse una suscripción
    recién recuperada.

    El remoto **manda**: es la copia más reciente de lo que pidió la gente,
    mientras que la del repo es la que se desplegó, que puede ser de hace días.
    Si un fichero no está en la rama, se deja el local tal cual.
    """
    if not activo():
        log.debug("Estado remoto desactivado (sin GITHUB_TOKEN).")
        return 0

    restaurados = 0
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as sesion:
        for relativo in ARCHIVOS:
            ruta = f"/repos/{config.GITHUB_REPO}/contents/{relativo}"
            estado, datos = await _api(
                sesion, "GET", ruta, params={"ref": config.GITHUB_RAMA_ESTADO}
            )
            if estado == 404:
                continue
            if estado != 200 or not isinstance(datos, dict):
                log.warning("GitHub: no se pudo leer %s (HTTP %s).", relativo, estado)
                continue
            contenido = datos.get("content")
            if not contenido:
                continue
            try:
                texto = base64.b64decode(contenido).decode("utf-8")
            except Exception:
                log.warning("GitHub: %s no se pudo decodificar; se ignora.", relativo)
                continue

            destino = BASE_DIR / relativo
            if destino.exists():
                try:
                    if destino.read_text(encoding="utf-8") == texto:
                        _ultimo_subido[relativo] = _sha(texto)
                        continue
                except OSError:
                    pass
            try:
                _escribir(destino, texto)
                _ultimo_subido[relativo] = _sha(texto)
                restaurados += 1
            except OSError as exc:
                log.warning("GitHub: no se pudo escribir %s: %s", relativo, exc)

    if restaurados:
        log.info("Estado restaurado de GitHub: %d fichero(s).", restaurados)
    else:
        log.info("Estado en GitHub al día (nada que restaurar).")
    return restaurados


async def guardar(forzar: bool = False) -> int:
    """Sube los ficheros de estado que hayan cambiado. Devuelve cuántos subió."""
    if not activo():
        return 0

    subidos = 0
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as sesion:
        if not await _asegurar_rama(sesion):
            return 0

        for relativo in ARCHIVOS:
            origen = BASE_DIR / relativo
            if not origen.exists():
                continue
            try:
                texto = origen.read_text(encoding="utf-8")
            except OSError:
                continue

            huella = _sha(texto)
            if not forzar and _ultimo_subido.get(relativo) == huella:
                continue

            # El `sha` del remoto es obligatorio para actualizar un fichero que ya
            # existe: sin él GitHub contesta 422.
            ruta = f"/repos/{config.GITHUB_REPO}/contents/{relativo}"
            estado, datos = await _api(
                sesion, "GET", ruta, params={"ref": config.GITHUB_RAMA_ESTADO}
            )
            cuerpo = {
                "message": f"Estado del bot: {relativo}",
                "content": base64.b64encode(texto.encode("utf-8")).decode("ascii"),
                "branch": config.GITHUB_RAMA_ESTADO,
            }
            if estado == 200 and isinstance(datos, dict) and datos.get("sha"):
                cuerpo["sha"] = datos["sha"]

            estado, _ = await _api(sesion, "PUT", ruta, json=cuerpo)
            if estado in (200, 201):
                _ultimo_subido[relativo] = huella
                subidos += 1
            else:
                log.warning("GitHub: no se pudo subir %s (HTTP %s).", relativo, estado)

    if subidos:
        log.info("Estado subido a GitHub: %d fichero(s).", subidos)
    return subidos


def resumen() -> str:
    """Para el log de arranque y `/health`."""
    if not activo():
        return "desactivado (sin GITHUB_TOKEN)"
    return f"{config.GITHUB_REPO}@{config.GITHUB_RAMA_ESTADO} cada {config.ESTADO_SINCRONIZAR_INTERVALO}s"

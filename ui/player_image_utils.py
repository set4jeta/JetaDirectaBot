#ui/player_image_utils.py
"""La foto de un jugador, como URL pública para que la traiga Discord.

Por qué una URL y no un adjunto
-------------------------------
Antes el bot subía el fichero a Discord en cada envío y **a cada destinatario**:
un mismo aviso reenviado a tres servidores con dos canales cada uno son seis
subidas de la misma foto. Eso agotó los 5 GB de salida del plan gratuito de
Render y tumbó el bot tres días (ver `DESPLIEGUE.md` §8). Con una URL, los bytes
los sirve dpm.lol y por Render solo viaja el enlace.

El fallo que arregla el estado de tres valores
----------------------------------------------
Hasta el 01-11-2026, para saber si un jugador tenía foto el bot **la descargaba**
desde Render. Y dpm.lol contesta 403 a la IP de Render (es el mismo bloqueo que
dejó sin rosters al bot, ver `apis/transporte_dpm.py`), así que la descarga
fallaba y el bot concluía «este jugador no tiene foto» → mandaba
`nopicture.webp`, la silueta por defecto.

El síntoma era raro de leer: los jugadores que ya estaban en
`assets/player_images/` (62 ficheros en el repo) salían con su foto, porque se
resolvían del disco sin tocar la red, y **todos los demás** salían con el
muñeco. En Worlds se notaba más porque casi ninguno está en ese puñado: JackieLove
o Inspired salían sin cara aunque su equipo y su nombre se vieran en el embed, y
su foto existe (`https://dpm.lol/esport/players/inspired.webp` contesta 200).

La lección: un 403 **no** es un 404. Que no podamos comprobar algo no significa
que no exista. Ahora la comprobación tiene tres respuestas y solo una de ellas
lleva al muñeco:

* `True`  — hay foto (está en disco, o dpm la sirvió).
* `False` — dpm contestó **404**: de verdad no hay foto.
* `None`  — no se pudo comprobar (403 del desafío, timeout, 5xx). Se usa la URL
  igualmente: la descarga la hará **Discord**, que no está bloqueado. Si no
  existe, Discord simplemente no pinta nada, que es lo que hacía antes.
"""

import os
import requests

PLAYER_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "player_images")
os.makedirs(PLAYER_IMG_DIR, exist_ok=True)

from typing import Optional

#: Dónde viven las fotos. Es la misma fuente de la que se descargaba el fichero,
#: así que la URL y la caché local son la misma imagen.
BASE_JUGADORES = "https://dpm.lol/esport/players/"
SIN_IMAGEN = "nopicture.webp"


#: Memoria del proceso: `nombre -> True/False/None` (ver el docstring de arriba).
#:
#: Sin esto, cada aviso volvería a abrir el fichero y a validarlo con PIL, y eso
#: ocurría **en cada aviso**. Importa porque Render da 0,1 CPU y esto corre dentro
#: del bucle de avisos.
_estado: dict[str, Optional[bool]] = {}


def _slug(player_name: str) -> str:
    """El nombre del fichero que usa dpm.lol: `Broken Blade` → `brokenblade`.

    Se quitan espacios, apóstrofos y puntos, y se pasa a minúsculas. Comprobado
    contra dpm.lol: `caps.webp`, `hanssama.webp`, `inspired.webp` y
    `brokenblade.webp` contestan 200 con ese criterio.
    """
    return player_name.lower().replace(" ", "").replace("'", "").replace(".", "")


def _dpm_bloqueado() -> bool:
    """¿Sabemos que dpm.lol nos está contestando 403 ahora mismo?

    Si es que sí, ni se intenta la descarga: se tardaría un timeout por jugador y
    el resultado sería el mismo. Se importa aquí y no arriba para no atar el
    módulo de imágenes al transporte en el arranque.
    """
    try:
        from apis import transporte_dpm

        return transporte_dpm.bloqueado_recientemente()
    except Exception:
        return False


def _estado_foto(player_name: str) -> Optional[bool]:
    """Comprueba la foto **una vez por jugador y arranque**. Ver el módulo."""
    from PIL import Image
    from io import BytesIO

    slug = _slug(player_name)
    if not slug:
        return False

    local_path = os.path.join(PLAYER_IMG_DIR, f"{slug}.webp")

    # Si ya existe local y es válida, úsala
    if os.path.exists(local_path):
        try:
            with Image.open(local_path) as img:
                img.verify()  # Verifica que sea una imagen válida
            return True
        except Exception:
            print(f"[IMG] Imagen local corrupta o inválida: {local_path}")
            os.remove(local_path)  # Eliminar la imagen corrupta

    # Con dpm bloqueándonos la descarga no dice nada de si hay foto o no.
    if _dpm_bloqueado():
        return None

    url = f"{BASE_JUGADORES}{slug}.webp"
    try:
        resp = requests.get(url, timeout=5)
    except Exception as e:
        print(f"[IMG] Error al intentar descargar imagen de {url}: {e}")
        return None

    # El único «no hay foto» de verdad. Un 403 es el desafío de Cloudflare, y un
    # 5xx es un mal día de dpm: en los dos casos la foto puede existir.
    if resp.status_code == 404:
        return False
    if resp.status_code != 200:
        print(f"[IMG] dpm contestó {resp.status_code} a {url}; no se concluye nada")
        return None

    try:
        Image.open(BytesIO(resp.content)).verify()
    except Exception:
        print(f"[IMG] Imagen descargada no es válida: {url}")
        return None

    with open(local_path, "wb") as f:
        f.write(resp.content)
    return True


def url_imagen_jugador(player_name: str) -> str:
    """La URL **pública** de la foto del jugador, para que la traiga Discord.

    Nunca devuelve una ruta local, y por eso el tipo es `str` y no `Optional`:
    un `None` aquí volvería a dejar al llamante eligiendo entre subir o no poner
    imagen, que es justo la decisión que se quiere quitar de en medio.

    Solo se devuelve el marcador `nopicture.webp` cuando **dpm ha dicho que no hay
    foto** (404). Si no se pudo comprobar, se devuelve la URL del jugador igual:
    es lo que hace que un jugador recién fichado salga con su cara en vez de con
    el muñeco.
    """
    slug = _slug(player_name)
    if not slug:
        return f"{BASE_JUGADORES}{SIN_IMAGEN}"

    if player_name not in _estado:
        _estado[player_name] = _estado_foto(player_name)

    if _estado[player_name] is False:
        return f"{BASE_JUGADORES}{SIN_IMAGEN}"
    return f"{BASE_JUGADORES}{slug}.webp"


def get_player_image_path(player_name: str) -> Optional[str]:
    """La ruta **local** de la foto, o `nopicture.webp` si no la hay.

    Se conserva por compatibilidad (lo usa `scripts/test_salida_red.py`), pero el
    embed ya **no** pasa por aquí: `url_imagen_jugador` no necesita tener el
    fichero en disco para saber qué URL mandar. Devuelve `None` solo cuando el
    nombre está vacío.
    """
    slug = _slug(player_name)
    if not slug:
        return None
    if player_name not in _estado:
        _estado[player_name] = _estado_foto(player_name)
    if _estado[player_name] is False:
        return os.path.join(PLAYER_IMG_DIR, SIN_IMAGEN)
    local = os.path.join(PLAYER_IMG_DIR, f"{slug}.webp")
    return local if os.path.exists(local) else os.path.join(PLAYER_IMG_DIR, SIN_IMAGEN)

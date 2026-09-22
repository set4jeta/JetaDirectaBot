# tracking/soloq/cuentas_sueltas.py
"""Seguir una cuenta concreta a partir de su Riot ID (`/track Nombre#TAG`).

Qué hace falta para poder avisar de una cuenta
----------------------------------------------
Dos cosas, y la API solo da una:

1. El **PUUID** — sale de `account-v1/by-riot-id`. Esa búsqueda es **global**
   (comprobado en vivo: `europe`, `americas` y `asia` devuelven el mismo PUUID),
   así que una sola llamada basta y no hay que saber la región de antemano.
2. La **plataforma** (`euw1`, `kr`, `na1`…) — **no la dice ningún endpoint**.
   `spectator-v5`, que es con lo que se mira si alguien está en partida, es por
   plataforma; y `account-v1/region/by-puuid` devuelve el **clúster** (`europe`,
   `americas`, `asia`), que acota pero no resuelve: dentro de `europe` caben
   `euw1`, `eun1`, `tr1` y `ru`.

Así que la plataforma se **averigua probando**: `summoner-v4/by-puuid` devuelve
200 solo en la plataforma donde existe esa cuenta y 404 en las demás. El coste es
una petición por plataforma candidata, **una sola vez** al suscribirse: después el
PUUID y la plataforma quedan guardados y la pasada solo gasta la de siempre.

El atajo de región
------------------
Escribir `eu`, `na`, `kr`… acota los candidatos y ahorra peticiones: con `eu` se
prueban dos antes de acertar (o una, si es `euw`), en vez de las siete de
`europe`. Si el usuario no escribe nada, se usa el clúster que devuelve Riot; y si
eso también falla, se prueban todas las que conoce el bot.

Por qué el jugador se guarda con `league="manual"`
--------------------------------------------------
Porque `active_game_checker` usa la liga para decidir qué **canales** reciben el
aviso (`if liga_jugador not in ligas_de(guild_id): continue`). Una cuenta suelta
no pertenece a ninguna liga, y "manual" no está en el catálogo, así que ningún
canal la recibe: solo le llega por DM a quien la pidió. Sin eso, la partida de un
streamer acabaría anunciada en el canal de la LEC por el respaldo de `_liga_de`.
"""

from __future__ import annotations

import asyncio

# Se importa por el efecto secundario: `config` es quien hace `load_dotenv`, y
# `RiotClient` lee `RIOT_API_KEY` del entorno directamente. En el bot siempre está
# cargado (`main.py` importa config lo primero), pero este módulo se usa también
# desde scripts sueltos, y sin esto el fallo es un `RuntimeError` de "clave no
# definida" que parece un problema de la clave y es de orden de imports.
import config  # noqa: F401
from apis.riot_client import PLATAFORMAS, RiotApiError, get_riot_client
from models.bootcamp_player import Account, BootcampPlayer
from utils.logger import get_logger

log = get_logger("tracking.cuentas_sueltas")

#: Liga ficticia de las cuentas sueltas. Ver el docstring del módulo: sirve para
#: que **ningún canal** las reciba y que solo lleguen por DM a quien las pidió.
LIGA_MANUAL = "manual"

#: Atajos que puede escribir el usuario -> plataformas, en orden de probabilidad.
#: En orden importa: `eu` prueba primero `euw1`, que es donde está la mayoría.
ATAJOS: dict[str, tuple[str, ...]] = {
    "eu": ("euw1", "eun1", "tr1", "ru"),
    "euw": ("euw1",),
    "euw1": ("euw1",),
    "eune": ("eun1",),
    "eun1": ("eun1",),
    "na": ("na1",),
    "na1": ("na1",),
    "kr": ("kr",),
    "br": ("br1",),
    "lan": ("la1",),
    "las": ("la2",),
    "oce": ("oc1",),
    "jp": ("jp1",),
    "sea": ("sg2", "th2", "ph2", "vn2", "tw2"),
    "tr": ("tr1",),
    "ru": ("ru",),
}

#: Plataformas de cada clúster de Riot, en orden de probabilidad.
POR_CLUSTER: dict[str, tuple[str, ...]] = {
    "europe": ("euw1", "eun1", "tr1", "ru"),
    "americas": ("na1", "br1", "la1", "la2", "oc1"),
    "asia": ("kr", "jp1", "sg2", "tw2", "vn2", "th2", "ph2"),
}

#: Todas las que conoce el bot, por si ni el atajo ni el clúster aciertan.
TODAS: tuple[str, ...] = tuple(sorted(PLATAFORMAS))

#: Cuántas plataformas se prueban a la vez. Son pocas y cada una es una petición
#: barata, así que se pueden lanzar juntas: esperar de una en una haría que
#: `/track` tardara segundos sin motivo.
MAX_SONDAS = 6


def partir_riot_id(texto: str) -> tuple[str, str] | None:
    """`"Nombre#TAG"` -> `("Nombre", "TAG")`. `None` si no tiene la forma.

    Se parte por el **último** `#` porque un nombre puede llevarlo dentro; el tag
    es lo que va después y no puede tener otro.
    """
    limpio = (texto or "").strip()
    if "#" not in limpio:
        return None
    nombre, _, tag = limpio.rpartition("#")
    nombre, tag = nombre.strip(), tag.strip()
    if not nombre or not tag:
        return None
    return (nombre, tag)


def candidatas(atajo: str = "", cluster: str | None = None) -> tuple[str, ...]:
    """Plataformas que hay que probar, en orden, según lo que se sepa."""
    clave = (atajo or "").strip().lower()
    if clave in ATAJOS:
        return ATAJOS[clave]
    if cluster:
        por_cluster = POR_CLUSTER.get(cluster.strip().lower())
        if por_cluster:
            return por_cluster
    return TODAS


async def resolver(texto: str, atajo: str = "") -> tuple[BootcampPlayer | None, str]:
    """Riot ID -> jugador listo para guardar. Devuelve `(jugador, error)`.

    `error` es una clave del catálogo de textos (`avisos.cuenta_*`) y solo tiene
    valor cuando el jugador es `None`. Se devuelven las dos cosas en vez de
    levantar porque el comando tiene que **decir qué ha fallado**: "esa cuenta no
    existe" y "no he podido hablar con Riot" son problemas distintos y el usuario
    solo puede arreglar el primero.
    """
    partes = partir_riot_id(texto)
    if partes is None:
        return None, "avisos.cuenta_formato"
    game_name, tag_line = partes

    try:
        client = await get_riot_client()
    except Exception:
        log.exception("No se pudo obtener el cliente de Riot.")
        return None, "avisos.cuenta_sin_cliente"

    try:
        puuid = await client.get_puuid(game_name, tag_line)
    except RiotApiError as exc:
        log.warning("Riot falló resolviendo %s#%s: %s", game_name, tag_line, exc)
        return None, "avisos.cuenta_sin_respuesta"
    except Exception:
        log.exception("Error inesperado resolviendo %s#%s", game_name, tag_line)
        return None, "avisos.cuenta_sin_respuesta"

    if not puuid:
        return None, "avisos.cuenta_no_existe"

    # Sin atajo, que Riot diga al menos el clúster: ahorra la mitad de las sondas.
    cluster = None
    if not (atajo or "").strip():
        try:
            cluster = await client.get_region_by_puuid(puuid)
        except Exception:
            log.debug("No se pudo averiguar el clúster de %s#%s", game_name, tag_line)

    plataformas = candidatas(atajo, cluster)
    plataforma = await _buscar_plataforma(client, puuid, plataformas)
    if plataforma is None:
        return None, "avisos.cuenta_sin_plataforma"

    player = BootcampPlayer(
        name=game_name, team="", role="", league=LIGA_MANUAL
    )
    player.accounts = [
        Account(
            game_name=game_name,
            tag_line=tag_line,
            puuid=puuid,
            platform=plataforma,
        )
    ]
    log.info(
        "Cuenta suelta resuelta: %s#%s -> %s (%s)",
        game_name, tag_line, plataforma, puuid[:8],
    )
    return player, ""


async def _buscar_plataforma(client, puuid: str, plataformas: tuple[str, ...]) -> str | None:
    """La primera plataforma donde existe esa cuenta, o `None`.

    Se prueban a la vez por tandas: `summoner-v4/by-puuid` contesta 404 en las
    que no son, así que la respuesta correcta es la que devuelve datos.
    """
    semaforo = asyncio.Semaphore(MAX_SONDAS)

    async def sonda(plataforma: str) -> str | None:
        async with semaforo:
            try:
                summoner = await client.get_summoner(puuid, plataforma)
            except Exception:
                return None
            return plataforma if summoner else None

    for resultado in await asyncio.gather(*(sonda(p) for p in plataformas)):
        if resultado:
            return resultado
    return None

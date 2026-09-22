"""Comprueba que cada cuenta se consulta en SU servidor, no en euw1.

Por qué existe
--------------

`DEFAULT_PLATFORM` es `euw1`, y todos los métodos del cliente lo tienen como
valor por defecto. Eso convierte un argumento olvidado en un fallo **silencioso**:
la petición sale, Riot contesta 404 porque el PUUID no es de esa región, y el bot
lo interpreta como "no está en partida" o "no tiene rango". No hay excepción, no
hay log de error, y la única señal es que un jugador coreano aparece sin Elo.

De las 172 cuentas seguidas hoy, 48 están fuera de EUW (31 KR, 13 NA1, 4 BR1).
Es decir: el 28 % de las cuentas se estaba consultando en el servidor incorrecto.

Cómo se comprueba
-----------------

Se inyecta un cliente falso en el singleton de `apis.riot_client` que **apunta la
plataforma de cada llamada** en vez de salir a la red. Luego se ejecutan los
caminos reales del bot (los mismos que usan `/team`, `/match`, el tracker y el
precalentado de rangos) y se exige que la plataforma anotada sea la de la cuenta.

No se prueba `get_active_game` del tracker: `active_game_checker` ya lo pasaba y
tiene su propia prueba en `test_tracker_sweep.py`. Aquí están los caminos que
faltaban.

Uso:  python scripts/test_plataformas.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apis import riot_client as rc  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    if condicion:
        print(f"  OK    {etiqueta}{f' ({extra})' if extra else ''}")
    else:
        print(f"  FALLA {etiqueta}{f' ({extra})' if extra else ''}")
        fallos.append(etiqueta)


# --------------------------------------------------------------------- #
# Cliente falso
# --------------------------------------------------------------------- #

class ClienteEspia:
    """Anota `(metodo, puuid, plataforma)` de cada llamada. No sale a la red."""

    def __init__(self) -> None:
        self.llamadas: list[tuple[str, str, str]] = []

    def _anotar(self, metodo: str, puuid: str, platform: str) -> None:
        self.llamadas.append((metodo, puuid, platform))

    async def get_active_game(self, puuid, platform=rc.DEFAULT_PLATFORM):
        self._anotar("active-game", puuid, platform)
        return None

    async def get_league_entries(self, puuid, platform=rc.DEFAULT_PLATFORM):
        self._anotar("league-entries", puuid, platform)
        # Una respuesta válida: así el camino sigue hasta el final y se prueba
        # también el guardado, no solo la URL.
        return [{
            "queueType": "RANKED_SOLO_5x5",
            "tier": "CHALLENGER", "rank": "I", "leaguePoints": 900,
        }]

    async def get_soloq_rank(self, puuid, platform=rc.DEFAULT_PLATFORM):
        entradas = await self.get_league_entries(puuid, platform)
        return entradas[0] if entradas else None

    def plataforma_de(self, puuid: str) -> str | None:
        for _metodo, p, plat in self.llamadas:
            if p == puuid:
                return plat
        return None


def instalar_espia() -> ClienteEspia:
    """Sustituye el singleton del cliente. Devuelve el espía."""
    espia = ClienteEspia()
    rc._client = espia  # get_riot_client() devuelve este objeto tal cual
    return espia


# --------------------------------------------------------------------- #
# Datos
# --------------------------------------------------------------------- #

class Cuenta:
    def __init__(self, puuid: str, platform: str | None, nombre: str = "X"):
        self.puuid = puuid
        self.platform = platform
        self.riot_id = {"game_name": nombre, "tag_line": "TAG"}
        self.stale = False
        self.rank = {}


class Jugador:
    def __init__(self, nombre: str, cuentas: list[Cuenta]):
        self.name = nombre
        self.accounts = cuentas
        self.team = "T1"
        self.role = "Mid"
        self.league = "lck"


#: Las cuatro formas en que llega una plataforma y su forma canónica.
CASOS = [
    ("puuid-kr", "KR", "kr"),          # dpm.lol en mayúsculas
    ("puuid-na", "NA1", "na1"),
    ("puuid-br", "BR1", "br1"),
    ("puuid-euw", "EUW1", "euw1"),
    ("puuid-corto", "NA", "na1"),      # sin el sufijo numérico
    ("puuid-vacio", None, "euw1"),     # desconocida -> por defecto
]


def _limpiar_cache_rangos() -> None:
    """La caché en memoria haría que la segunda prueba no llame a la API."""
    from core import ranked_cache

    ranked_cache.RANKED_CACHE.clear()


# --------------------------------------------------------------------- #
# 1 · normalizar_plataforma
# --------------------------------------------------------------------- #

def prueba_normalizar() -> None:
    print("\n=== normalizar_plataforma ===")
    for _puuid, cruda, esperada in CASOS:
        obtenida = rc.normalizar_plataforma(cruda)
        ok(obtenida == esperada, f"{cruda!r} -> {esperada}", obtenida)

    ok(rc.normalizar_plataforma("marte") == rc.DEFAULT_PLATFORM,
       "una plataforma inventada cae al valor por defecto")
    ok(rc.normalizar_plataforma("  kr  ") == "kr", "se toleran espacios")


# --------------------------------------------------------------------- #
# 2 · ranked_cache (lo usan /team, el tracker y el embed)
# --------------------------------------------------------------------- #

async def prueba_ranked_cache() -> None:
    print("\n=== core.ranked_cache.get_rank_data_or_cache ===")
    from core.ranked_cache import get_rank_data_or_cache

    espia = instalar_espia()
    _limpiar_cache_rangos()

    for puuid, cruda, esperada in CASOS:
        rango = await get_rank_data_or_cache(puuid, platform=cruda)
        ok(espia.plataforma_de(puuid) == esperada,
           f"{cruda!r} consulta en {esperada}", str(espia.plataforma_de(puuid)))
        ok(rango.get("tier") == "Challenger", f"{cruda!r} devuelve el rango parseado")

    # La caché no debe partirse por plataforma: el PUUID ya identifica la cuenta.
    # Se comprueba antes de limpiarla, con la entrada que acaba de escribirse.
    antes = len(espia.llamadas)
    await get_rank_data_or_cache("puuid-kr", platform="KR")
    ok(len(espia.llamadas) == antes, "un acierto de caché no vuelve a preguntar",
       f"{len(espia.llamadas) - antes} peticiones de más")

    # Sin plataforma el comportamiento no cambia: sigue siendo euw1. Lo que se
    # comprueba es que no revienta, porque hay llamadores antiguos.
    _limpiar_cache_rangos()
    await get_rank_data_or_cache("puuid-sin-arg")
    ok(espia.plataforma_de("puuid-sin-arg") == rc.DEFAULT_PLATFORM,
       "sin argumento sigue funcionando (compatibilidad)")


# --------------------------------------------------------------------- #
# 3 · rank_warm (el precalentado de rangos)
# --------------------------------------------------------------------- #

async def prueba_rank_warm() -> None:
    print("\n=== tracking.soloq.rank_warm ===")
    from tracking.soloq import rank_warm

    espia = instalar_espia()

    # `cuentas_seguidas` lee del disco: se sustituye la carga por datos propios
    # para que la prueba no dependa del fichero real.
    import tracking.soloq.accounts_io as accounts_io

    stale = Cuenta("puuid-stale", "KR")
    stale.stale = True
    # La lista se construye UNA vez: con un lambda que crea objetos nuevos en
    # cada llamada, marcar `stale` fuera afectaría a una copia desechada.
    jugadores = [
        Jugador("Faker", [Cuenta("puuid-kr", "KR")]),
        Jugador("Doublelift", [Cuenta("puuid-na", "NA1"), Cuenta("puuid-euw", "EUW1")]),
        Jugador("Fantasma", [stale]),
    ]

    original = accounts_io.load_tracked_accounts
    accounts_io.load_tracked_accounts = lambda: jugadores

    try:
        cuentas = rank_warm.cuentas_seguidas()
        ok(all(isinstance(c, tuple) and len(c) == 2 for c in cuentas),
           "cuentas_seguidas devuelve pares (puuid, plataforma)")
        ok(dict(cuentas) == {"puuid-kr": "kr", "puuid-na": "na1", "puuid-euw": "euw1"},
           "con la plataforma normalizada y sin las stale", str(dict(cuentas)))

        resumen = await rank_warm.refrescar(cuentas)
        ok(resumen["ok"] == 3, "las 3 se refrescan", str(resumen["ok"]))
        ok(espia.plataforma_de("puuid-kr") == "kr", "la coreana se pide en kr")
        ok(espia.plataforma_de("puuid-na") == "na1", "la americana en na1")
        ok(espia.plataforma_de("puuid-euw") == "euw1", "la europea en euw1")
        ok(not any(p == "puuid-stale" for _m, p, _pl in espia.llamadas),
           "la cuenta stale no gasta ninguna petición")

        # Los scripts de mantenimiento pasan `list[str]`: no debe romperse ni
        # desmontar la cadena carácter a carácter.
        espia.llamadas.clear()
        resumen = await rank_warm.refrescar(["puuid-suelto"])
        ok(resumen["total"] == 1, "una lista de PUUIDs sueltos sigue valiendo",
           str(resumen["total"]))
        ok(espia.plataforma_de("puuid-suelto") == rc.DEFAULT_PLATFORM,
           "y usa el servidor por defecto")
    finally:
        accounts_io.load_tracked_accounts = original


# --------------------------------------------------------------------- #
# 4 · SoloQMatch.load_ranks (el embed de `/match`)
# --------------------------------------------------------------------- #

async def prueba_load_ranks() -> None:
    print("\n=== models.soloq_match.load_ranks ===")
    from models.soloq_match import SoloQMatch

    espia = instalar_espia()
    _limpiar_cache_rangos()

    partida = SoloQMatch.from_riot_game_data({
        "gameId": 1,
        "platformId": "KR",
        "gameMode": "CLASSIC",
        "queueId": 420,
        "gameLength": 600,
        "participants": [
            {"puuid": "kr-1", "championId": 1, "teamId": 100},
            {"puuid": "kr-2", "championId": 2, "teamId": 200},
        ],
    })

    ok(partida.platform == "KR", "la partida sabe en qué servidor se juega",
       str(partida.platform))

    await partida.load_ranks()
    ok(espia.plataforma_de("kr-1") == "kr", "el participante 1 se pide en kr",
       str(espia.plataforma_de("kr-1")))
    ok(espia.plataforma_de("kr-2") == "kr", "el participante 2 también")

    # Una partida sin `platformId` (caché antigua) no debe reventar.
    _limpiar_cache_rangos()
    sin_plataforma = SoloQMatch.from_riot_game_data({
        "gameId": 2,
        "participants": [{"puuid": "x-1", "championId": 1, "teamId": 100}],
    })
    ok(sin_plataforma.platform is None, "sin platformId la propiedad es None")
    await sin_plataforma.load_ranks()
    ok(espia.plataforma_de("x-1") == rc.DEFAULT_PLATFORM,
       "y cae al servidor por defecto sin lanzar")


# --------------------------------------------------------------------- #
# 5 · /team
# --------------------------------------------------------------------- #

async def prueba_team() -> None:
    print("\n=== core.register_team_commands ===")
    from core.register_team_commands import _rank_de_cuenta

    espia = instalar_espia()
    _limpiar_cache_rangos()

    # `get_cached_rank` puede tener el PUUID en el histórico real y saltarse la
    # API. Se usan PUUIDs inventados que no pueden estar en `ranked_data.json`.
    cuenta = Cuenta("test-plat-kr-0001", "KR", "Faker")
    datos = await _rank_de_cuenta(cuenta, asyncio.Semaphore(2))
    ok(espia.plataforma_de("test-plat-kr-0001") == "kr",
       "/team pide el rango en el servidor de la cuenta",
       str(espia.plataforma_de("test-plat-kr-0001")))
    ok(datos and datos.get("tier") == "Challenger", "y lo devuelve")


# --------------------------------------------------------------------- #
# 6 · capa de compatibilidad y `/match`
# --------------------------------------------------------------------- #

async def prueba_riot_api_compat() -> None:
    print("\n=== apis.riot_api (capa de compatibilidad) ===")
    from apis import riot_api

    espia = instalar_espia()

    await riot_api.get_active_game("compat-kr", platform="KR")
    ok(espia.plataforma_de("compat-kr") == "kr", "get_active_game acepta platform")

    await riot_api.get_ranked_data("compat-na", platform="NA1")
    ok(espia.plataforma_de("compat-na") == "na1", "get_ranked_data acepta platform")

    await riot_api.get_soloq_rank("compat-br", platform="BR1")
    ok(espia.plataforma_de("compat-br") == "br1", "get_soloq_rank acepta platform")

    await riot_api.get_active_game("compat-viejo")
    ok(espia.plataforma_de("compat-viejo") == rc.DEFAULT_PLATFORM,
       "y sin el argumento siguen funcionando")

    print("\n=== core.register_player_commands (/match) ===")
    from core.register_player_commands import _partida_de_cuenta

    espia = instalar_espia()
    await _partida_de_cuenta(Cuenta("match-kr", "KR"), asyncio.Semaphore(2))
    ok(espia.plataforma_de("match-kr") == "kr",
       "/match consulta la partida en el servidor de la cuenta",
       str(espia.plataforma_de("match-kr")))


# --------------------------------------------------------------------- #
# 7 · cola de reintentos
# --------------------------------------------------------------------- #

async def prueba_retry_handler() -> None:
    print("\n=== core.retry_handler ===")
    from core import retry_handler

    espia = instalar_espia()
    retry_handler.RETRY_PUUIDS.clear()
    retry_handler.RETRY_WORKER_RUNNING = False

    retry_handler.add_to_retry_queue("retry-kr", "KR")
    retry_handler.add_to_retry_queue("retry-kr", "KR")
    ok(len(retry_handler.RETRY_PUUIDS) == 1, "no se duplica la misma cuenta",
       str(len(retry_handler.RETRY_PUUIDS)))

    await retry_handler.retry_worker()
    ok(retry_handler.RETRY_PUUIDS == [], "el trabajador VACÍA la cola y termina",
       str(retry_handler.RETRY_PUUIDS))
    ok(retry_handler.RETRY_WORKER_RUNNING is False, "y suelta la bandera al salir")
    ok(espia.plataforma_de("retry-kr") == "kr", "el reintento va al servidor correcto",
       str(espia.plataforma_de("retry-kr")))

    # Antes esto era un bucle infinito: `pop(0)` estaba fuera del while.
    ok(len([1 for m, p, _ in espia.llamadas if p == "retry-kr"]) == 1,
       "una cuenta que devuelve 404 se consulta UNA vez, no en bucle")


# --------------------------------------------------------------------- #

async def main() -> None:
    prueba_normalizar()
    await prueba_ranked_cache()
    await prueba_rank_warm()
    await prueba_load_ranks()
    await prueba_team()
    await prueba_riot_api_compat()
    await prueba_retry_handler()

    rc._client = None  # se deja el singleton como estaba

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)
    print("Todas las cuentas se consultan en su servidor.")


if __name__ == "__main__":
    asyncio.run(main())

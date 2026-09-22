"""Rosters de los equipos seguidos, desde dpm.lol.

Cómo saca los nombres (y por qué cambió)
----------------------------------------
Antes:

    soup.find_all("span", class_="font-semibold text-bm lg:text-bxl")

Funciona, pero `text-bm` y `lg:text-bxl` son clases generadas por Tailwind. El día
que dpm.lol recompile su CSS eso devuelve `[]`, y la versión anterior de `main()`
**escribía la lista vacía encima de los rosters buenos** sin comprobar nada. El bot
no se caía: se quedaba sin jugadores y sin ningún síntoma visible.

Ahora los nombres salen del **leaderboard de la liga** (ver más abajo), que
devuelve en una sola petición JSON limpio con `displayName` y `team`. Las dos
vías del scraping quedan como respaldo para `scripts/`, pero ya no están en el
camino normal del bot.

Y la escritura pasa por `utils.safe_json.guardar_lista_json`, que se niega a
guardar una lista vacía o un encogimiento brusco. Si la fuente falla, el fichero
anterior se queda intacto y el log lo dice en ERROR.

De equipos escritos a mano a ligas elegidas
-------------------------------------------
El bot seguía un set fijo:

    TRACKED_TEAMS = {"G2", "FNC", "VIT", "TH", "KC", "NAVI",
                     "GX", "BDS", "SK", "MKOI", "KOI", "LR"}

Medido el 2026-09-01 contra el leaderboard real de la LEC, los equipos son:
`FNC G2 GX KC MKOI NAVI SHFT SK TH VIT`. Es decir: **`BDS`, `KOI` y `LR` ya no
existen y ha entrado `SHFT`**. El bot llevaba tiempo intentando scrapear tres
equipos fantasma y perdiéndose uno real, sin que se cayera nada ni nadie lo
avisara.

Ahora la lista se deriva del leaderboard de cada liga, así que se corrige sola,
y cada servidor elige qué ligas seguir (`tracking/soloq/leagues.py`).

Sobre las plataformas (importante)
----------------------------------
Antes `main()` descartaba toda cuenta que no fuera `EUW1`/`EUN1`. Eso valía
cuando solo existía la LEC, pero medido en `/v1/pros` las cuentas están
repartidas entre servidores:

    LEC   -> EUW1 24, KR 4        (Vladi, Oscarinin y Stend tienen cuentas en KR)
    LCK   -> KR 8, NA1 1, EUW1 1
    LCS   -> NA1 9, KR 11, EUW1 4, BR1 1
    CBLOL -> BR1 6, KR 4, NA1 2, EUW1 1

Con el filtro europeo, seguir la LCK habría descartado **todas** sus cuentas.
Ya no se filtra por plataforma: cada cuenta guarda la suya y `spectator-v5` se
consulta contra ese servidor.
"""

from __future__ import annotations

import os
import time
from urllib.parse import quote

import cloudscraper
from bs4 import BeautifulSoup

from apis.dpm_payload import extraer_jugadores, resumen
from models.bootcamp_player import BootcampPlayer
from utils.logger import get_logger
from utils.safe_json import cargar_lista_json, guardar_lista_json

log = get_logger(__name__)

#: Se mantiene porque hay scripts que la usan, pero ya no filtra nada: ver el
#: docstring de módulo, las cuentas están repartidas entre EUW1, KR, NA1 y BR1.
EUROPE_PLATFORMS = {"EUW1", "EUN1"}
JSON_PATH = os.path.join(os.path.dirname(__file__), "accounts_from_teams.json")


def _ligas_en_uso() -> list[str]:
    """Ligas que sigue algún servidor.

    Se importa tarde porque `leagues.py` toca el disco al cargar la
    configuración, y este módulo también se usa desde scripts sueltos.
    """
    from tracking.soloq.leagues import ligas_en_uso

    return ligas_en_uso()

MAX_RETRIES = 3
TIMEOUT = 20

#: Selector heredado. Se mantiene solo como respaldo de la vía del payload.
SELECTOR_LEGACY = "font-semibold text-bm lg:text-bxl"

_scraper = None


def _get_scraper():
    """Un solo scraper reutilizado.

    La versión anterior creaba un `cloudscraper` nuevo **en cada reintento de cada
    jugador**: con 9 equipos y 5 jugadores por equipo eso son decenas de
    resoluciones del challenge de Cloudflare por pasada, todas idénticas.
    """
    global _scraper
    if _scraper is None:
        _scraper = cloudscraper.create_scraper(browser={"custom": "Chrome"}, delay=10)
    return _scraper


def safe_request(url: str):
    """GET con reintentos. Devuelve la respuesta o `None`."""
    scraper = _get_scraper()
    for intento in range(1, MAX_RETRIES + 1):
        try:
            resp = scraper.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            log.warning("Intento %d/%d falló para %s: %s", intento, MAX_RETRIES, url, exc)
            if intento < MAX_RETRIES:
                time.sleep(2)
    log.error("No se pudo acceder a %s tras %d intentos.", url, MAX_RETRIES)
    return None


def load_existing_players() -> list[BootcampPlayer]:
    return [BootcampPlayer.from_dict(p) for p in cargar_lista_json(JSON_PATH)]


def cargar_existentes_teams() -> list[dict]:
    return cargar_lista_json(JSON_PATH)


def _nombres_desde_payload(html: str) -> list[str]:
    """Vía preferente: el estado serializado de Next.js."""
    jugadores = extraer_jugadores(html)
    if not jugadores:
        return []
    log.debug("Payload: %s", resumen(jugadores))
    nombres = {
        (j.get("displayName") or j.get("gameName") or "").strip()
        for j in jugadores
    }
    return sorted(n for n in nombres if n)


def _nombres_desde_html(html: str) -> list[str]:
    """Respaldo: el selector de clases de Tailwind."""
    soup = BeautifulSoup(html, "html.parser")
    nombres = {
        s.get_text(strip=True)
        for s in soup.find_all("span", class_=SELECTOR_LEGACY)
    }
    return sorted(n for n in nombres if n)


def get_players_from_team(team: str) -> list[str]:
    """Nombres de los jugadores de un equipo. `[]` significa fallo, no equipo vacío."""
    url = f"https://dpm.lol/esport/soloq/teams/{team}"
    resp = safe_request(url)
    if resp is None:
        return []

    nombres = _nombres_desde_payload(resp.text)
    via = "payload"
    if not nombres:
        nombres = _nombres_desde_html(resp.text)
        via = "html (respaldo)"
        if nombres:
            log.warning(
                "%s: el payload no dio jugadores y hubo que usar el selector CSS. "
                "Revisa apis/dpm_payload.py, dpm.lol pudo cambiar la estructura.",
                team,
            )

    if not nombres:
        log.error(
            "%s: ni el payload ni el selector CSS dieron jugadores. "
            "Ejecuta scripts/probe_dpm_team_html.py %s para ver qué cambió.",
            team,
            team,
        )
        return []

    log.info("%s: %d jugadores vía %s -> %s", team, len(nombres), via, ", ".join(nombres))
    return nombres


def _jugador_de_pros(nombre: str, league: str) -> BootcampPlayer | None:
    """Ficha completa de un jugador vía `/v1/pros/<nombre>`.

    Devuelve `None` si dpm.lol no lo reconoce: es distinto de "este jugador
    tiene cero cuentas", así que quien llama puede contar los fallos aparte.
    """
    resp = safe_request(f"https://dpm.lol/v1/pros/{quote(nombre)}")
    if resp is None:
        return None
    try:
        data = resp.json()
    except ValueError as exc:
        log.warning("Respuesta no-JSON para %s: %s", nombre, exc)
        return None

    if not data or not data.get("players"):
        log.debug("%s: sin cuentas en /v1/pros.", nombre)
        return None

    return BootcampPlayer.from_pro_api(nombre, data, league=league)


def get_pro_players(ligas: list[str] | None = None) -> list[BootcampPlayer]:
    """Recorre las ligas en seguimiento y pide la ficha de cada jugador.

    Por liga se hace **una** petición al leaderboard, que da los nombres y el
    equipo de todos sus jugadores. Antes eran dos: la ficha del equipo y luego
    la de cada jugador, y la del equipo dependía de un selector de CSS.
    """
    from tracking.soloq.leagues import ligas_en_uso, roster_de_liga

    codigos = ligas or ligas_en_uso()
    todos: list[BootcampPlayer] = []
    ligas_fallidas: list[str] = []

    for codigo in codigos:
        roster = roster_de_liga(codigo)
        if roster.vacio:
            ligas_fallidas.append(codigo)
            continue

        # El leaderboard es un ranking de CUENTAS, no de personas: un pro con
        # tres cuentas en challenger sale tres veces (medido en la LEC: 82
        # entradas para ~52 nombres distintos). Sin deduplicar, se creaban
        # jugadores repetidos con las mismas cuentas y el tracker consultaba
        # el mismo PUUID hasta 4 veces por pasada.
        vistos: dict[str, str] = {}
        for nombre, team in roster.jugadores:
            vistos.setdefault(nombre, team)
        if len(vistos) < len(roster.jugadores):
            log.info(
                "Liga %s: %d entradas -> %d jugadores distintos (el leaderboard "
                "repite por cuenta).",
                codigo, len(roster.jugadores), len(vistos),
            )

        for nombre, team in vistos.items():
            try:
                jugador = _jugador_de_pros(nombre, codigo)
            except Exception:
                log.exception("Error construyendo el jugador %s.", nombre)
                continue
            if jugador is None:
                continue
            # El leaderboard es la fuente del equipo, no la ficha: la ficha
            # trae `team` de la cuenta concreta y puede venir vacío.
            if team:
                jugador.team = team
            todos.append(jugador)

        log.info("Liga %s: %d jugadores con ficha.", codigo, len(
            [p for p in todos if p.league == codigo]
        ))

    if ligas_fallidas:
        log.error(
            "Ligas sin datos en esta pasada: %s. No se tocará el JSON si el "
            "recuento total baja demasiado.",
            ", ".join(ligas_fallidas),
        )
    return todos


def main(ligas: list[str] | None = None) -> bool:
    """Refresca `accounts_from_teams.json`. Devuelve True si escribió."""
    codigos = ligas or _ligas_en_uso()
    log.info("Recopilando rosters de %d ligas: %s", len(codigos), ", ".join(codigos))
    players = get_pro_players(codigos)
    antiguos = cargar_existentes_teams()
    nuevos: list[dict] = []

    # Se indexa por (nombre, liga) y no solo por nombre: un jugador puede
    # aparecer en dos ligas (un suplente que juega en la liga principal y en la
    # regional) y entonces el nombre solo no distingue sus cuentas.
    indice_previo = {
        (p.get("name", "").lower(), p.get("league") or ""): p for p in antiguos
    }
    indice_sin_liga = {p.get("name", "").lower(): p for p in antiguos}

    for player in players:
        previo = indice_previo.get((player.name.lower(), player.league))
        if previo is None:
            # JSON anterior a las ligas: se casa por nombre sin más.
            previo = indice_sin_liga.get(player.name.lower())
        if not previo:
            log.info("Jugador nuevo: %s (%s · %s)", player.name, player.team, player.league)

        cuentas_nuevas = []
        for acc in player.accounts:
            # Ya no se filtra por plataforma. Antes solo se guardaban las
            # cuentas EUW1/EUN1, lo que dejaba fuera todas las de KR/NA/BR: con
            # LEC no se notaba, pero seguir la LCK así habría dado cero cuentas.
            # Cada cuenta guarda su plataforma y `spectator-v5` se consulta
            # contra la suya.
            if not (acc.platform or "").strip():
                log.debug(
                    "%s: cuenta %s sin plataforma, se descarta.",
                    player.name, acc.riot_id.get("game_name"),
                )
                continue

            # Conservamos el PUUID de Riot ya resuelto: volver a pedirlo costaría
            # una petición por cuenta y el PUUID no cambia al renombrarse.
            if previo:
                for acc_ant in previo.get("accounts", []):
                    riot_ant = acc_ant.get("riot_id") or {}
                    if (
                        acc.riot_id["game_name"].lower() == (riot_ant.get("game_name") or "").lower()
                        and acc.riot_id["tag_line"].lower() == (riot_ant.get("tag_line") or "").lower()
                        and acc_ant.get("puuid")
                    ):
                        acc.puuid = acc_ant["puuid"]
                        acc.stale = acc_ant.get("stale", False)
                        break
            cuentas_nuevas.append(acc)

        player.accounts = cuentas_nuevas
        if not player.accounts:
            log.debug("%s: sin cuentas utilizables, se omite.", player.name)
            continue
        nuevos.append(player.to_dict())

    return guardar_lista_json(
        JSON_PATH,
        nuevos,
        etiqueta="accounts_from_teams",
        # Una liga entera son ~10 de 80 jugadores: si falla una, no queremos
        # rechazar la actualización de las demás.
        min_ratio=0.8,
    )


def refrescar_ligas(codigos: list[str]) -> bool:
    """Refresca los rosters de estas ligas **sin tocar los de las demás**.

    Por qué existe, si ya está `main()`
    -----------------------------------
    `main()` **reemplaza** `accounts_from_teams.json` con lo que devuelvan las
    ligas que le pases: llamarlo con `["lck"]` borraría la LEC entera. Y llamarlo
    sin argumentos rehace todas las ligas en uso, que son minutos de scraping y
    cientos de peticiones.

    Esto hace lo que hace falta para tener **las 20 ligas descargadas** sin
    volver a bajarlas todas cada vez: quita del fichero los jugadores de las
    ligas que se van a refrescar, trae los nuevos y deja intacto el resto. Así la
    tarea de fondo puede ir liga por liga, de una en una, y en una vuelta del
    reloj están todas al día sin que ninguna tanda sea grande.

    Devuelve `True` si escribió. Nunca lanza hacia arriba: quien lo llama es una
    tarea de fondo o un comando, y un fallo de scraping no puede tumbar nada.
    """
    try:
        from tracking.soloq.leagues import resolver
    except Exception:
        log.exception("No se pudo importar el catálogo de ligas.")
        return False

    pedidas: list[str] = []
    for c in codigos:
        liga = resolver(c)
        if liga and liga.codigo not in pedidas:
            pedidas.append(liga.codigo)
    if not pedidas:
        return False

    existentes = cargar_existentes_teams()
    if not existentes:
        # Sin fichero previo esto es un alta completa: que lo haga `main()`, que
        # ya sabe de deduplicación, PUUIDs heredados y ligas sin datos.
        log.info("Sin fichero previo de equipos; se deja el alta completa a main().")
        return main(pedidas)

    try:
        jugadores = get_pro_players(pedidas)
    except Exception:
        log.exception("Fallo trayendo los rosters de %s.", ", ".join(pedidas))
        return False

    if not jugadores:
        # Un scraping que no devuelve nada (Cloudflare, cambio de HTML) no puede
        # borrar lo que ya había: se deja el fichero como estaba.
        log.warning(
            "Sin jugadores para %s; no se toca el fichero.", ", ".join(pedidas)
        )
        return False

    # Se quitan del fichero los jugadores de las ligas refrescadas y se vuelven a
    # poner con lo recién traído. Las demás ligas se copian tal cual.
    pedidas_set = set(pedidas)
    conservados = [
        p for p in existentes
        if (p.get("league") or "").lower() not in pedidas_set
    ]

    # Clave (nombre, liga) y no solo nombre: un suplente puede estar en la liga
    # principal y en la regional, y entonces el nombre no distingue sus cuentas.
    vistos = {
        (p.get("name", "").lower(), (p.get("league") or "").lower())
        for p in conservados
    }
    nuevos: list[dict] = []
    for jugador in jugadores:
        if not jugador.accounts:
            continue
        clave = (jugador.name.lower(), (jugador.league or "").lower())
        if clave in vistos:
            continue
        vistos.add(clave)
        nuevos.append(jugador.to_dict())

    if not nuevos:
        log.warning(
            "Los rosters de %s no trajeron ningún jugador utilizable; se deja el "
            "fichero como estaba.", ", ".join(pedidas),
        )
        return False

    combinado = conservados + nuevos
    log.info(
        "Rosters de %s refrescados: %d jugadores (antes %d en esas ligas, ahora "
        "%d; total %d).",
        ", ".join(pedidas),
        len(nuevos),
        len(existentes) - len(conservados),
        len(nuevos),
        len(combinado),
    )
    return guardar_lista_json(
        JSON_PATH, combinado, etiqueta="accounts_from_teams"
    )


if __name__ == "__main__":
    main()

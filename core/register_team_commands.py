"""Comando `!team` / `/team`: jugadores de un equipo con su mejor cuenta.

Qué se cambió
-------------

0. **Ahora también es `/team equipo:G2`.** El cuerpo es el mismo: se extrajo del
   decorador a `_cuerpo_team`, así que las dos formas responden idéntico. El
   argumento sigue admitiendo el tricode en cualquier capitalización.
- **Los textos pasan por `utils.i18n`.** El comando hablaba solo español, así
  que un servidor con `/lang en` recibía "Jugadores de G2" igual. El tricode, el
  nombre largo del equipo y el rango (tier y división) **no** se traducen: son
  nombres propios de Riot y de los equipos.
- Antes se usaba `p.accounts[0]`, la primera cuenta que apareciera en el JSON,
  sin mirar su Elo. Un pro podía salir con su cuenta secundaria de Diamante
  teniendo la principal en Challenger. Ahora se consultan todas las cuentas y
  se muestra la de mayor rango (ver `utils/rank_utils`).
- Se reutiliza el caché de rangos cuando está fresco y solo se llama a la API
  por las cuentas que no lo están, en paralelo y con límite. Con la tarea de
  fondo `refrescar_rangos` lo normal es que no haga falta ninguna petición.
- Se usa el cliente central de Riot en vez de abrir un `aiohttp.ClientSession`
  por comando: así se comparte el rate limiter y el pool de conexiones.
- El formateo de rangos estaba repetido cuatro veces; ahora es una función.
- La lista de jugadores se recarga si `accounts_from_teams.json` cambió: antes
  se leía una sola vez al importar el módulo, así que un equipo nuevo no
  aparecía hasta reiniciar el bot.
- Las peticiones de todo el equipo se lanzan juntas en vez de jugador por
  jugador: 5 jugadores en serie eran 5 esperas encadenadas.
- `await ctx.typing()` era un error latente: en nextcord 3.x `typing()` devuelve
  un gestor de contexto que **no es awaitable**, así que la línea habría
  lanzado `TypeError` en cuanto alguien usara el comando. Ahora el aviso lo da
  `Respuesta.esperando`.
- **Cada jugador sale una sola vez.** El roster guarda una entrada por
  (jugador, liga), así que quien juega su liga y además un evento internacional
  aparecía dos veces: `/team G2` listaba a Caps dos veces. Le pasaba a 11 de los
  168 equipos (G2, KC, T1, BLG, TES, HLE, FUR, DCG, LYON, TLAW y TSW). Lo cazó
  el dueño probando el comando, no una prueba.
- **Si el equipo no existe, propone el bueno.** `/team koi` respondía «no hay
  jugadores» y soltaba los 168 tricodes. Ahora busca parecidos por substring
  (sin acentos: «fenix» encuentra «Fénix») y por distancia de edición, así que
  «koi» propone **MKOI (Movistar KOI) y MKF (Movistar KOI Fénix)** —los dos
  equipos que son KOI— y «mko» o «g2e» también aciertan. Solo si no hay ningún
  parecido se enseña la lista completa.
- **«mejor de N» se explica y además es cierto.** El sufijo venía de la línea
  anterior y el dueño no lo entendía: «no entiendo, no tiene sentido eso». Es
  que el rango que se enseña es el de la **mejor cuenta del jugador**, no el de
  la primera del fichero, así que ahora dice «mejor de 4 cuentas». Y el número
  cuenta solo las cuentas **entre las que se eligió**: Myrwn tiene 4 cuentas
  seguidas pero 3 están `stale` (Riot ya no reconoce el nombre) y no traen
  rango, así que «mejor de 4» era contar de más. Con una sola cuenta con datos
  ya no se pone sufijo.
"""

from __future__ import annotations

import asyncio
import difflib
import unicodedata

from nextcord.ext import commands

import config
from core.dual_command import slash_texto
from core.rank_data import get_cached_rank, save_rank_data
from core.ranked_cache import get_rank_data_or_cache
from core.responder import Respuesta
from tracking.soloq.accounts_io import load_tracked_accounts
from utils.constants import TEAM_TRICODES
from utils.i18n import idioma_de, tr
from utils.logger import get_logger
from utils.rank_utils import es_rank_valido, formatear_rank, mejor_cuenta

log = get_logger("core.team")

ROLE_ORDER = ["Top", "Jungle", "Mid", "ADC", "Support"]


async def _rank_de_cuenta(account, semaforo: asyncio.Semaphore) -> dict | None:
    """Rango de una cuenta: del caché si está fresco, si no de la API."""
    cacheado = get_cached_rank(account)
    if es_rank_valido(cacheado):
        return cacheado

    if not getattr(account, "puuid", None) or getattr(account, "stale", False):
        return cacheado

    async with semaforo:
        try:
            datos = await get_rank_data_or_cache(
                account.puuid, platform=getattr(account, "platform", None)
            )
        except Exception as exc:
            log.debug("No se pudo obtener el rango de %s: %s", account.puuid[:12], exc)
            return cacheado

    if es_rank_valido(datos):
        account.rank = datos
        # Escritura diferida: el volcado a disco lo hace `rank_store`.
        save_rank_data(account)
        return datos

    return cacheado


async def _mejor_cuenta_de(player, semaforo: asyncio.Semaphore):
    """Devuelve (cuenta, rango, cuentas_comparadas) con la mejor cuenta.

    El tercer valor **no** es cuántas cuentas tiene el jugador, es entre cuántas
    se eligió de verdad. La diferencia importa y se vio con datos reales: Myrwn
    tiene 4 cuentas seguidas pero 3 están `stale` (Riot ya no reconoce el
    nombre), así que no aportan rango. Decir «mejor de 4 cuentas» cuando solo
    una tenía datos era contar de más, y el dueño lo notó: «no tiene sentido
    eso». Ahora, si solo una cuenta trae rango, no se dice nada: no hubo
    comparación que explicar.
    """
    cuentas = list(player.accounts)
    if not cuentas:
        return None, None, 0

    rangos = await asyncio.gather(
        *[_rank_de_cuenta(a, semaforo) for a in cuentas],
        return_exceptions=True,
    )

    pares = []
    for cuenta, rango in zip(cuentas, rangos):
        if isinstance(rango, Exception):
            log.debug("Fallo obteniendo rango: %s", rango)
            continue
        pares.append((cuenta, rango))

    comparadas = sum(1 for _c, r in pares if es_rank_valido(r))

    elegida = mejor_cuenta(pares)
    if elegida:
        return elegida[0], elegida[1], comparadas

    # Ninguna cuenta tiene rango válido: se muestra la primera para no dejar
    # al jugador fuera del listado.
    return cuentas[0], (pares[0][1] if pares else None), comparadas


def equipos_disponibles() -> list[str]:
    """Tricodes con jugadores registrados, en mayúsculas y sin repetir."""
    vistos = {
        (p.team or "").upper()
        for p in load_tracked_accounts()
        if p.team
    }
    return sorted(t for t in vistos if t)


def _plegar(texto: str) -> str:
    """Minúsculas y sin acentos, para poder comparar «fenix» con «Fénix»."""
    base = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def _etiqueta_equipo(tag: str) -> str:
    """`MKOI (Movistar KOI)` si el tricode tiene nombre largo, si no `MKOI`."""
    nombre = TEAM_TRICODES.get(tag.upper())
    return f"{tag.upper()} ({nombre})" if nombre else tag.upper()


def _cuentas_resueltas(jugador) -> int:
    """Cuentas con PUUID: cuanto más alto, más sirve la entrada para elegir."""
    return sum(
        1 for c in (jugador.accounts or [])
        if (c.puuid if not isinstance(c, dict) else c.get("puuid"))
    )


def sin_repetidos(jugadores: list) -> list:
    """Un jugador, una línea, aunque el roster lo liste en dos ligas.

    El fichero de rosters guarda una entrada por (jugador, liga): quien juega la
    LEC y además el MSI sale dos veces, y `/team G2` enseñaba a Caps dos veces.
    Afecta a 11 equipos de 168. Se conserva la entrada con más cuentas
    resueltas —la más útil para elegir la mejor cuenta— y a igualdad, la primera
    (el `dict` conserva el orden de inserción).
    """
    elegidas: dict[str, object] = {}
    for jugador in jugadores:
        clave = _plegar(jugador.name or "").strip()
        previo = elegidas.get(clave)
        if previo is None or _cuentas_resueltas(jugador) > _cuentas_resueltas(previo):
            elegidas[clave] = jugador
    return list(elegidas.values())


def sugerir_equipos(consulta: str, disponibles: list[str], tope: int = 3) -> list[str]:
    """Tricodes parecidos a lo escrito, para el «¿Quisiste decir…?».

    Tres maneras de parecerse, de más a menos fiable, y cada equipo se queda con
    la mejor que cumpla:

    1. lo escrito **está dentro** del tricode o del nombre largo: «koi» -> MKOI
       y MKF, porque los dos son «Movistar KOI (Fénix)». Cuanto menos sobra,
       más arriba: «koi» en «mkoi» (sobra 1 letra) va antes que «koi» en
       «movistar koi fénix»;
    2. el tricode o el nombre **está dentro** de lo escrito, que es el caso de
       quien escribe de más («g2esports», «mkoi.»);
    3. distancia de edición, para las erratas que no comparten trozo: «navy» ->
       NAVI. Con el corte en 0,7: «koi» y «EKO» se parecen 0,67 y **no** cuenta,
       que era el ruido que salía al proponer EKO para «koi».

    Con `tope` se acota para no volver a soltar una lista larga: el dueño se
    quejó justo de eso («me dijo no existe, equipos disponibles: y los puso
    todos»). Devuelve `[]` si no hay ningún parecido razonable.
    """
    q = _plegar(consulta).strip()
    if not q:
        return []

    #: Por debajo de esto, la "errata" es casualidad. 0,7 deja fuera «koi»/«EKO»
    #: (0,67) y «mko»/«mkf» (0,67) y deja dentro «navy»/«NAVI» (0,75).
    CORTE_ERRATA = 0.7

    puntuadas: list[tuple[float, str]] = []
    for tag in sorted({t.upper() for t in disponibles}):
        tricode = _plegar(tag)
        nombre = _plegar(TEAM_TRICODES.get(tag, ""))
        if q in tricode or (nombre and q in nombre):
            # Cuanto menos sobra del nombre del equipo, mejor encaje.
            objetivo = tricode if q in tricode else nombre
            puntuacion = 2.0 + len(q) / max(len(objetivo), 1)
        elif tricode in q or (nombre and nombre in q):
            puntuacion = 1.5
        else:
            # Erratas: contra el tricode y contra cada palabra del nombre largo,
            # porque «fenix» no se parece a «MKF» pero sí a «Fénix».
            objetivos = [tricode] + nombre.split()
            puntuacion = max(
                (difflib.SequenceMatcher(None, q, o).ratio() for o in objetivos if o),
                default=0.0,
            )
            if puntuacion < CORTE_ERRATA:
                continue
        puntuadas.append((puntuacion, tag))

    puntuadas.sort(key=lambda par: (-par[0], par[1]))
    return [tag for _puntuacion, tag in puntuadas[:tope]]


async def _cuerpo_team(res: Respuesta, team_tag: str) -> None:
    """Cuerpo compartido por `!team` y `/team`."""
    _ = tr(res.guild_id)
    idioma = idioma_de(res.guild_id)

    team_tag = (team_tag or "").lower().strip()
    if not team_tag:
        disponibles = equipos_disponibles()
        await res.error(
            _("team.falta_equipo") + "\n"
            + (_("team.equipos_con_jugadores", equipos=", ".join(disponibles))
               if disponibles else "")
        )
        return

    await res.esperando(_("team.consultando", equipo=team_tag.upper()))

    # Se recarga en cada uso: el fichero lo reescribe la tarea diaria.
    players = load_tracked_accounts()
    team_players = [p for p in players if p.team and p.team.lower() == team_tag]
    # El roster lista al jugador una vez por liga (su liga + MSI): sin esto,
    # `/team G2` enseñaba a Caps, BrokenBlade, Labrov, Hans Sama y SkewMond
    # dos veces cada uno.
    team_players = sin_repetidos(team_players)
    if not team_players:
        disponibles = equipos_disponibles()
        pistas = sugerir_equipos(team_tag, disponibles)
        if pistas:
            # Con un parecido claro no se suelta la lista entera de 168
            # tricodes: se propone el bueno y ya.
            detalle = _("team.quisiste_decir", equipos=", ".join(
                _etiqueta_equipo(t) for t in pistas
            ))
        elif disponibles:
            detalle = _("team.equipos_disponibles", equipos=", ".join(disponibles))
        else:
            detalle = ""
        await res.error(
            _("team.sin_jugadores", equipo=team_tag.upper())
            + (f"\n{detalle}" if detalle else "")
        )
        return

    team_players.sort(
        key=lambda p: ROLE_ORDER.index(p.role) if p.role in ROLE_ORDER else len(ROLE_ORDER)
    )

    # No se lanzan todas las peticiones a la vez: se acota la concurrencia
    # para no acercarse al límite de la API de Riot.
    semaforo = asyncio.Semaphore(config.TRACKER_CONCURRENCY)

    # Todos los jugadores en paralelo: en serie, cada uno esperaba su turno
    # aunque el semáforo tuviera huecos libres.
    resultados = await asyncio.gather(
        *[_mejor_cuenta_de(j, semaforo) for j in team_players],
        return_exceptions=True,
    )

    lineas: list[str] = []
    sin_datos = 0

    for jugador, resultado in zip(team_players, resultados):
        if isinstance(resultado, Exception):
            log.debug("Fallo con %s: %s", jugador.name, resultado)
            lineas.append(_("team.error_rango", jugador=jugador.name))
            sin_datos += 1
            continue

        cuenta, rango, comparadas = resultado
        if cuenta is None:
            lineas.append(_("team.sin_cuentas", jugador=jugador.name))
            continue

        game_name = cuenta.riot_id.get("game_name", "")
        tag_line = cuenta.riot_id.get("tag_line", "")
        cuenta_str = f"{game_name}#{tag_line}" if game_name else _("team.sin_cuenta")

        if not es_rank_valido(rango):
            sin_datos += 1

        # Solo se dice cuántas cuentas se compararon si de verdad hubo
        # comparación: con una sola cuenta con rango, el sufijo sobraba.
        extra = _("team.mejor_de", total=comparadas) if comparadas > 1 else ""
        lineas.append(
            f"**{jugador.name}** ({cuenta_str}) - "
            f"{formatear_rank(rango, idioma)}{extra}"
        )

    team_name_full = TEAM_TRICODES.get(team_tag.upper(), team_tag.upper())
    msg = (
        _("team.titulo", equipo=team_tag.upper(), nombre=team_name_full) + "\n\n"
        + "\n".join(lineas)
    )
    if sin_datos:
        msg += "\n\n" + _("team.aviso_sin_datos", n=sin_datos)

    await res.enviar_partido(msg)


def register_team_commands(bot: commands.Bot):
    slash_texto(
        bot,
        "cmd.team.name",
        "cmd.team.desc",
        _cuerpo_team,
        arg_nombre="cmd.team.arg",
        arg_desc="cmd.team.arg_desc",
    )

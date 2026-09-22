"""Comando `!live` / `/live`: quién está en partida ahora mismo.

Qué se cambió
-------------

0. **Ahora también es `/live`.** El cuerpo no se ha duplicado: `construir_mensaje`
   ya era independiente de Discord y el envío pasa por `core.responder`, así que
   las dos formas mandan exactamente el mismo texto. El gesto de "⏳ Buscando..."
   y luego editar ese mensaje se conserva en prefijo; en slash equivale al
   "pensando..." de `defer()`.

1. **Cuenta atrás del delay del espectador.** El cálculo del tiempo daba
   negativo durante los primeros minutos y se rotulaba igual: `⏱ -02:14 en
   partida`. Ahora esos casos dicen `⏳ -02:14 · se podrá ver en 3 min`. El
   reloj sale de `utils.game_clock`, el mismo que usa el embed de `!match`
   (ahí está documentada la medición del delay real).

2. **El rol es el de la partida, no el del equipo.** Se pintaba `player.role`,
   el rol del jugador en su equipo profesional, así que salía siempre el mismo
   aunque en SoloQ estuviera jugando otra línea. Ahora se deduce de los
   campeones con `utils.role_assigner`, igual que el embed. Esto cierra el punto
   del backlog *"hacer que en el comando !live ponga correctamente el Rol de la
   partida cuando hay jugadores en vivo"*.

3. **El KDA ya no se inventa.** Se mostraba `KDA {kills}/{deaths}/{assists}`
   leídos del participante de `spectator-v5`, pero **esa respuesta no trae esos
   campos**. Verificado contra la API: un participante solo tiene
   `puuid, teamId, spell1Id, spell2Id, championId, lastSelectedSkinIndex,
   profileIconId, riotId, bot, gameCustomizationObjects`. Es decir, el KDA que
   enseñaba era siempre `0/0/0`. Se ha quitado.

4. **Se descartan las partidas ya terminadas.** El bucle recorría
   `ACTIVE_GAME_CACHE` sin mirar la edad, y una entrada sobrevive ahí hasta que
   `limpiar_cache_partidas_viejas` la borra a los 90 minutos.

5. **El mensaje se parte si pasa de 2000 caracteres.** Era un fallo latente: con
   bastantes jugadores en partida a la vez, el `edit` habría fallado con un 400.
"""

from __future__ import annotations

import time

from nextcord.ext import commands

import config
from cache.champion_cache import CHAMPION_ID_TO_NAME
from core.dual_command import dual
from core.responder import Respuesta, partir
from models.soloq_match import SoloQMatch
from tracking.soloq.accounts_io import load_tracked_accounts
from tracking.soloq.active_game_cache import ACTIVE_GAME_CACHE
from utils.cache_utils import limpiar_cache_partidas_viejas
from utils.constants import normalizar_rol, rol_corto
from utils.game_clock import desde_cache
from utils.logger import get_logger
from utils.role_assigner import assign_roles

log = get_logger("core.live")

# Una partida de SoloQ no dura 90 minutos: si el reloj pasa de aquí, la entrada
# es de una partida acabada que aún no se ha limpiado de la caché.
MAX_DURACION = 90 * 60


def _roles_de_partida(match: SoloQMatch) -> dict[str, str]:
    """`{puuid: ROL}` deducido de los campeones de cada equipo.

    Se resuelve una vez por partida y no una vez por jugador: cuando hay varios
    jugadores seguidos en la misma partida, la asignación es la misma.

    No se le pasa `puuid_to_player` a `assign_roles` a propósito: eso sesgaría
    la asignación hacia el rol que el jugador ocupa en su equipo profesional, y
    lo que queremos saber es qué está jugando **en esta partida**.
    """
    try:
        participantes = assign_roles(list(match.participants), None)
    except Exception as exc:
        # Depende de numpy/scipy; si algo falla, mejor sin rol que sin comando.
        log.debug("No se pudo asignar roles de la partida %s: %s", match.game_id, exc)
        return {}
    return {
        p.puuid: normalizar_rol(p.role)
        for p in participantes
        if p.puuid and getattr(p, "role", None)
    }


def _partir(texto: str, limite: int = 1900) -> list[str]:
    """Parte por líneas para no pasar el límite de 2000 de Discord.

    Se mantiene el nombre porque `scripts/test_game_clock.py` lo usa; delega en
    `core.responder.partir`, que hace lo mismo para todos los comandos.
    """
    return partir(texto, limite)


def construir_mensaje(ahora: float | None = None, idioma: str | None = None) -> str:
    """Texto completo de `!live` a partir de la caché de partidas activas.

    Está fuera del cuerpo del comando a propósito: así se puede probar sin
    Discord (`scripts/test_game_clock.py`) y la prueba ejerce el código real en
    vez de una copia. El comando solo se encarga de enviar el resultado.

    `idioma` va segundo y por defecto en `None` (= español) para no romper a las
    pruebas, que llaman `construir_mensaje(AHORA)`.
    """
    from utils.i18n import t

    ahora = time.time() if ahora is None else ahora
    players = load_tracked_accounts()

    puuid_to_player = {}
    puuid_to_account = {}
    for player in players:
        for account in player.accounts:
            if account.puuid:
                puuid_to_player[account.puuid] = player
                puuid_to_account[account.puuid] = account

    filas: list[tuple[int, str]] = []
    ya_mostrados: set[tuple] = set()
    roles_por_partida: dict[object, dict[str, str]] = {}
    esperando = 0

    for puuid, cache_entry in list(ACTIVE_GAME_CACHE.items()):
        if not cache_entry or "active_game" not in cache_entry:
            continue

        player = puuid_to_player.get(puuid)
        account = puuid_to_account.get(puuid)
        if not player or not account:
            continue

        display_name = account.riot_id.get("game_name", "")
        tag_line = account.riot_id.get("tag_line", "")
        clave = (player.name, display_name, tag_line)
        if clave in ya_mostrados:
            continue
        ya_mostrados.add(clave)

        reloj = desde_cache(cache_entry, ahora)
        if reloj.transcurrido > MAX_DURACION:
            continue
        if not reloj.espectable:
            esperando += 1

        match = SoloQMatch.from_riot_game_data(cache_entry["active_game"])

        if match.game_id not in roles_por_partida:
            roles_por_partida[match.game_id] = _roles_de_partida(match)
        roles = roles_por_partida[match.game_id]

        champ_name = "?"
        for part in match.participants:
            if part.puuid == puuid:
                champ_name = part.champion_name or CHAMPION_ID_TO_NAME.get(
                    str(part.champion_id), "?"
                )
                break

        # El rol de la partida manda; si `assign_roles` no pudo resolverla se cae
        # al del equipo profesional, ya normalizado al mismo vocabulario.
        rol = rol_corto(roles.get(puuid) or player.role)
        tricode = (player.team or "").upper()
        equipo = f"{tricode} " if tricode else ""

        filas.append((
            reloj.transcurrido,
            f"👤 {equipo}{player.name} — {display_name}#{tag_line} "
            f"| {champ_name} ({rol}) | {reloj.texto_corto(idioma)}",
        ))

    if not filas:
        return t("live.nadie", idioma)

    # De más reciente a más avanzada: las que acaban de empezar son las que
    # interesa espectar, y así la cuenta atrás queda arriba.
    filas.sort(key=lambda par: par[0])
    mensaje = (
        t("live.titulo", idioma) + "\n\n"
        + "\n".join(linea for _t, linea in filas)
    )
    mensaje += "\n\n" + t("live.pie", idioma)

    if esperando:
        mensaje += "\n" + t(
            "live.esperando", idioma,
            n=esperando, minutos=config.SPECTATOR_DELAY // 60,
        )

    mensaje += "\n" + t(
        "live.aviso_retraso", idioma, segundos=config.CHECK_GAMES_INTERVAL
    )
    return mensaje


async def _cuerpo_live(res: Respuesta) -> None:
    """Cuerpo compartido por `!live` y `/live`."""
    from utils.i18n import idioma_de, t

    idioma = idioma_de(res.guild_id)
    await res.esperando(t("live.buscando", idioma))
    limpiar_cache_partidas_viejas()
    await res.enviar_partido(construir_mensaje(idioma=idioma))


def register_live_command(bot: commands.Bot):
    dual(
        bot,
        "live",
        "cmd.live.desc",
        _cuerpo_live,
    )

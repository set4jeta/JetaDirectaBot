"""Comandos de esports: `/esports` y `/schedule`.

Qué se cambió
-------------
0. **Ahora son dos, no cuatro.** Los del canal de esports
   (`setlivechannel` y `removelivechannel`) se unificaron con los de SoloQ en
   `/subscribe`, `/unsubscribe`, `/channels` y `/mute`, que viven juntos en
   `core/notification_config_commands.py`. Configurar canales es una sola cosa y
   tenerla partida en dos sitios duplicaba permisos, avisos y nombres.
   Y los nombres son de **una palabra**: `partida`/`next` eran medio en español y
   medio en inglés, y ahora son `esports` y `schedule`.
1. **Son slash.** Viven en un Cog porque comparten el `TrackerService` (y su
   `bg_task` de 30 s), así que no se podían pasar por `slash` directamente:
   nextcord exige `self` en los comandos declarados dentro de una clase. La
   solución es `slash_cog`, que registra contra el bot un cuerpo con el cog ya
   capturado en la clausura.
2. **`print` → logging.** Eran 12 llamadas, varias dentro del bucle de 30
   segundos, y `[DEBUG] match_id=... status=...` se imprimía por cada partido
   trackeado **cada vez que alguien usaba el comando**. Ahora es `log.debug`,
   así que solo sale con `LOG_LEVEL=DEBUG`.
3. **`bg_task` ya no avisa a grito pelado cuando un servidor no tiene canal.**
   Ese `print` salía cada 30 s por cada servidor sin configurar; ahora es debug.
4. **Se avisa una sola vez de los partidos ya empezados.** Igual que antes.
5. **Dos `IndexError` latentes tapados.** `match.teamsEventDetails[0]` y
   `match.trackedGames[0]` se indexaban sin comprobar que la lista tuviera algo.
   Con un partido a medio enriquecer eso reventaba el comando entero; en slash
   eso se ve como "la aplicación no responde".
6. **Traducidos.** Eran los últimos comandos íntegramente en español: 12 mensajes
   a pelo y las descripciones de la lista de Discord. Ahora pasan por
   `utils.i18n` como el resto, así que un servidor con `/language es` los recibe
   en español.
"""

from __future__ import annotations

import copy

import nextcord
from nextcord.ext import commands, tasks

from core import health as salud
from apis.dpm_api import LIGAS
from core.dual_command import slash_cog, slash_opciones_cog
from core.responder import Respuesta
from esports_extension.models.match import EventDetails, ScheduleEvent
from esports_extension.models.tracker import TrackedMatch, TrackedStatus
from esports_extension.services.embed_service import EmbedService
from esports_extension.services.storage import load_notification_channel
from tracking.soloq.channel_targets import (
    ESPORTS,
    acepta_esports,
    objetivos_de,
)
from esports_extension.utils.buttons import ScoreButtonView
from esports_extension.utils.time_utils import get_network_time
from utils.i18n import tr
from utils.logger import get_logger

log = get_logger("esports.commands")

#: Cuántos partidos se muestran de una vez en `/partida` y `/next`.
MAX_PARTIDOS = 3

#: Ventana de `/next`, en horas. El margen negativo deja ver un partido que
#: debería haber empezado ya y todavía figura como no iniciado.
VENTANA_HORAS = (-4, 12)


def _marcador(match: TrackedMatch) -> tuple[int, int]:
    """Victorias de cada equipo en la serie, 0-0 si aún no se sabe.

    Antes se hacía `match.teamsEventDetails[0].game_wins` directamente. Un
    partido detectado pero sin enriquecer todavía tiene la lista vacía, y eso
    era un `IndexError` que se llevaba por delante todo el comando.
    """
    equipos = getattr(match, "teamsEventDetails", None) or []
    if len(equipos) < 2:
        return 0, 0
    return getattr(equipos[0], "game_wins", 0) or 0, getattr(equipos[1], "game_wins", 0) or 0


async def _enviar_con_marcador(res: Respuesta, embed, match: TrackedMatch) -> None:
    """Manda el embed, con los botones de marcador si la serie ya va 1-0 o más.

    A 0-0 no se ponen: la vista solo sirve para revelar un resultado, y en el
    primer mapa no hay nada que revelar.
    """
    if embed is None:
        return
    azul, rojo = _marcador(match)
    if azul == 0 and rojo == 0:
        await res.send(embed=embed)
    else:
        await res.send(embed=embed, view=ScoreButtonView(azul, rojo))


class EsportsCommands(commands.Cog):
    """Estado compartido de esports: el tracker y su bucle de detección."""

    def __init__(self, bot: commands.Bot, tracker_service):
        self.bot = bot
        self.tracker = tracker_service

        if not self.bg_task.is_running():
            self.bg_task.start()

    def cog_unload(self) -> None:
        """Para el bucle al descargar el cog.

        Sin esto, un `reload` dejaba dos `bg_task` corriendo a la vez y cada
        partido se notificaba dos veces.
        """
        self.bg_task.cancel()

    # ------------------------------------------------------------------ #
    # Bucle de detección y notificación
    # ------------------------------------------------------------------ #

    @tasks.loop(seconds=30)
    async def bg_task(self):
        try:
            # Detecta una sola vez por ciclo, y luego reparte a los canales.
            await self.tracker.detect_live_matches()
        except Exception:
            log.exception("Error detectando partidos de esports.")
            # Este es el único sitio donde se ve si lolesports responde: el
            # comando `/partida` lee la memoria del tracker, así que seguiría
            # contestando con datos viejos aunque la API estuviera caída.
            salud.registrar("esports", False, "la API de lolesports falló")
            return

        salud.registrar(
            "esports", True, f"{len(self.tracker.tracked_matches)} partidos en memoria"
        )

        try:
            for guild in self.bot.guilds:
                channel_id = load_notification_channel(guild.id)
                if not channel_id:
                    # Antes esto era un print cada 30 s por cada servidor sin
                    # configurar: el ruido más constante de la consola.
                    log.debug(
                        "Servidor %s sin canal de esports (usa /subscribe type:esports).",
                        guild.id,
                    )
                    continue
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    log.warning(
                        "Canal %s del servidor %s no existe. ¿Se borró?",
                        channel_id,
                        guild.id,
                    )
                    continue
                # Un canal puede haber pedido algo concreto (`/subscribe esports
                # lck`). Sin objetivos se manda todo, que es como funcionaba
                # antes de que existieran los objetivos por canal.
                objetivos = objetivos_de(guild.id, channel_id).get(ESPORTS)
                acepta = None
                if objetivos:
                    def acepta(match, _objetivos=objetivos):  # noqa: ANN001
                        equipos = tuple(
                            valor
                            for equipo in (getattr(match, "teamsEventDetails", None) or [])
                            for valor in (
                                getattr(equipo, "code", "") or "",
                                getattr(equipo, "name", "") or "",
                            )
                            if valor
                        )
                        return acepta_esports(
                            _objetivos,
                            liga=getattr(match, "league_name", "") or "",
                            equipos=equipos,
                        )

                await self.tracker.notify_new_games(channel, acepta=acepta)
        except Exception:
            log.exception("Error repartiendo las notificaciones de esports.")

        # Y el mismo aviso, a quien lo haya pedido por su cuenta. Va **fuera** del
        # bucle de canales a propósito: la detección ya es global y el embed es el
        # mismo, así que esto se hace una vez por ciclo y no una por servidor.
        # Si falla, no puede llevarse por delante los avisos de los canales, que
        # son los que ya funcionaban.
        try:
            await self._avisar_partidos_por_dm()
        except Exception:
            log.exception("Error repartiendo los partidos de esports por DM.")

    async def _avisar_partidos_por_dm(self) -> None:
        """Manda los partidos oficiales a quien los sigue por privado.

        Los canales reciben todo lo que se detecta; esto es la otra mitad: la
        gente que pidió con `/track lec` o `/track t1` y no tiene por qué estar en
        un servidor con el canal configurado.

        El registro de "ya avisado" (`notified_games`) es el mismo que usan los
        canales y está indexado por `game_id`, así que los destinatarios se
        guardan con el prefijo `u` de `dm_notifier.clave_dedupe`: un id de usuario
        y uno de canal no coinciden nunca, pero así al abrir el JSON se ve qué es
        cada cosa. Sin ese registro, esta función —que corre cada 30 s— mandaría
        el mismo DM en cada vuelta.
        """
        from esports_extension.services.storage import (
            load_notified_games,
            save_notified_games,
        )
        from tracking.soloq.dm_notifier import (
            clave_dedupe,
            destinatarios_partidos,
            repartir,
        )

        notificados = load_notified_games()
        cambiado = False

        for match in list(self.tracker.tracked_matches.values()):
            equipos = [
                getattr(t, "code", "") for t in (match.teamsEventDetails or [])
            ]
            ids = destinatarios_partidos(match.slug, equipos)
            if not ids:
                continue

            for tracked_game in reversed(match.trackedGames):
                if tracked_game.state != "inProgress":
                    continue
                if not (tracked_game.live_blue_metadata and tracked_game.live_red_metadata):
                    continue

                ya = set(notificados.get(tracked_game.game_id, []))
                pendientes = [u for u in ids if clave_dedupe(u) not in ya]
                if not pendientes:
                    continue

                embed = await EmbedService.create_live_match_embed(
                    match, is_notification=True
                )
                if embed is None:
                    continue

                # El mismo embed para todos: los de esports no están traducidos
                # (a diferencia de los de SoloQ), así que no hay nada que cachear
                # por idioma y el objeto se puede reutilizar tal cual.
                entregados = await repartir(
                    self.bot, pendientes, lambda _idioma: {"embed": embed}
                )
                if entregados:
                    ya.update(clave_dedupe(u) for u in entregados)
                    notificados[tracked_game.game_id] = list(ya)
                    cambiado = True
                    log.info(
                        "Partido %s avisado por DM a %d persona(s).",
                        tracked_game.game_id, len(entregados),
                    )

        if cambiado:
            save_notified_games(notificados)

    @bg_task.before_loop
    async def _esperar_bot(self):
        """No arrancar hasta que el bot esté conectado.

        `notify_new_games` necesita `bot.get_channel`, que devuelve None hasta
        que la caché de Discord está poblada. La primera vuelta del bucle salía
        antes de eso y no notificaba nada.
        """
        await self.bot.wait_until_ready()


# ---------------------------------------------------------------------- #
# /partida
# ---------------------------------------------------------------------- #

def _liga_del_partido(match) -> str:
    """El nombre de liga del partido, normalizado para poder comparar.

    La API de esports de Riot da nombres como `LCK` o `LEC`, y a veces con
    patrocinador (`LCK CL`). Se compara en minúsculas y sin espacios sobrantes
    contra el nombre largo del catálogo y contra su código, porque exigir
    coincidencia exacta haría que el filtro no encontrase nunca nada y eso se ve
    igual que una avería.
    """
    return " ".join(str(getattr(match, "league_name", "") or "").lower().split())


def _pasa_el_filtro(match, liga: str) -> bool:
    """¿Este partido es de esa liga? `liga` viene como código (`lec`, `lck`)."""
    if not liga:
        return True
    codigo = liga.strip().lower()
    nombre = (LIGAS.get(codigo) or "").lower()
    etiqueta = " ".join(nombre.split(" · ")[0].lower().split())
    del_partido = _liga_del_partido(match)
    if not del_partido:
        return False
    return (
        del_partido == codigo
        or del_partido == etiqueta
        or del_partido.startswith(etiqueta + " ")
        or (etiqueta and etiqueta in del_partido)
    )


async def _cuerpo_partida(cog: EsportsCommands, res: Respuesta, valores: dict | None = None) -> None:
    _ = tr(res.guild_id)
    await res.esperando(_("esports.buscando"))

    # Copia para que el bucle de 30 s no cambie los objetos a media respuesta.
    snapshot = copy.deepcopy(list(cog.tracker.tracked_matches.values()))

    for match in snapshot:
        log.debug(
            "match_id=%s status=%s state=%s juegos=%d",
            match.match_id,
            match.status,
            match.state,
            len(match.trackedGames or []),
        )

    en_vivo = [
        m
        for m in snapshot
        if (m.status == TrackedStatus.DETECTED or m.status == "detected")
        and m.state == "inProgress"
    ]

    # El filtro de liga se aplica sobre lo que ya está en memoria: no cuesta una
    # sola llamada. Si el filtro deja la lista vacía se dice qué ligas sí tienen
    # partido, porque un vacío sin explicación se lee como avería.
    liga = ((valores or {}).get("league") or "").strip()
    if liga:
        ligas_disponibles = sorted({_liga_del_partido(m) for m in en_vivo if _liga_del_partido(m)})
        en_vivo = [m for m in en_vivo if _pasa_el_filtro(m, liga)]
        if not en_vivo:
            aviso = _("esports.sin_partidas_liga", liga=liga.upper())
            if ligas_disponibles:
                aviso += "\n" + _("esports.otras_ligas", ligas=", ".join(ligas_disponibles))
            await res.error(aviso)
            return

    if not en_vivo:
        await res.error(_("esports.sin_partidas"))
        return

    prioritarios = await cog.tracker._prioritize_matches(en_vivo)
    alguno = False

    for match in prioritarios[:MAX_PARTIDOS]:
        if await _mostrar_partido(res, match):
            alguno = True

    if not alguno:
        await res.error(_("esports.sin_partidas"))


async def _mostrar_partido(res: Respuesta, match: TrackedMatch) -> bool:
    """Manda el embed que corresponda al estado del partido. True si mandó algo.

    Cuatro estados, en el mismo orden de preferencia que antes: partida en
    curso > draft > esperando el siguiente mapa > esperando el primero.
    """
    juegos = match.trackedGames or []

    # 1. Partida en curso con jugadores: el caso bueno.
    for g in reversed(juegos):
        if g.state == "inProgress" and g.has_participants:
            embed = await EmbedService.create_live_match_embed(match, is_notification=False)
            if embed is None:
                break
            # El marcador se saca de los equipos de la serie, pero solo tiene
            # sentido si el juego trae las dos metadatas de equipo.
            completo = next(
                (
                    j
                    for j in reversed(juegos)
                    if j.state == "inProgress"
                    and j.live_blue_metadata
                    and j.live_red_metadata
                    and j.live_blue_metadata.participants
                    and j.live_red_metadata.participants
                ),
                None,
            )
            if completo and match.teamsEventDetails:
                azules = next(
                    (
                        t
                        for t in match.teamsEventDetails
                        if completo.live_blue_metadata
                        and t.id == completo.live_blue_metadata.team_id
                    ),
                    None,
                )
                rojos = next(
                    (
                        t
                        for t in match.teamsEventDetails
                        if completo.live_red_metadata
                        and t.id == completo.live_red_metadata.team_id
                    ),
                    None,
                )
                azul = azules.game_wins if azules else 0
                rojo = rojos.game_wins if rojos else 0
                if azul == 0 and rojo == 0:
                    await res.send(embed=embed)
                else:
                    await res.send(embed=embed, view=ScoreButtonView(azul, rojo))
            else:
                await res.send(embed=embed)
            return True

    # 2. Draft en curso: aún no hay jugadores en la Live API.
    for g in juegos:
        if (
            g.state in ("inProgress", "unstarted")
            and not g.has_participants
            and g.draft_in_progress
        ):
            embed = await EmbedService.create_draft_embed(match)
            if embed:
                await res.send(embed=embed)
                return True
            break

    # 3. Un mapa acabó y el siguiente todavía no ha empezado.
    for idx, g in enumerate(juegos[:-1]):
        siguiente = juegos[idx + 1]
        if (
            g.state == "completed"
            and siguiente.state in ("unstarted", "inProgress")
            and not siguiente.has_participants
            and not siguiente.draft_in_progress
        ):
            embed = await EmbedService.create_waiting_embed(match, siguiente.number)
            if embed:
                await _enviar_con_marcador(res, embed, match)
                return True
            break

    # 4. El primer mapa está marcado en curso pero no ha arrancado de verdad.
    if juegos:
        primero = juegos[0]
        if (
            primero.state == "inProgress"
            and not primero.has_participants
            and not primero.draft_in_progress
        ):
            embed = await EmbedService.create_waiting_embed(match, primero.number)
            if embed:
                await _enviar_con_marcador(res, embed, match)
                return True

    return False


# ---------------------------------------------------------------------- #
# /next
# ---------------------------------------------------------------------- #

async def _cuerpo_next(cog: EsportsCommands, res: Respuesta) -> None:
    _ = tr(res.guild_id)
    await res.esperando(_("esports.consultando_calendario"))

    try:
        ahora = await get_network_time()
        data = await cog.tracker.api_client.get_schedule()
    except Exception:
        log.exception("Fallo consultando el calendario de LoL Esports.")
        await res.error(_("esports.api_caida"))
        return

    if ahora is None:
        await res.error(_("esports.sin_hora"))
        return

    eventos = data.get("data", {}).get("schedule", {}).get("events", []) or []
    proximos: list[ScheduleEvent] = []

    for crudo in eventos:
        if not isinstance(crudo, dict):
            continue
        if not isinstance(crudo.get("match"), dict):
            # Eventos que no son partidos (shows, descansos) o mal formados.
            continue

        evento = ScheduleEvent(crudo)

        # Si el tracker ya lo tiene en curso o acabado, no es "próximo".
        trackeado = cog.tracker.tracked_matches.get(evento.match_id)
        if trackeado and (
            trackeado.state in ("inProgress", "completed")
            or trackeado.status == TrackedStatus.COMPLETED
        ):
            continue

        if (
            evento.type == "match"
            and evento.state == "unstarted"
            and evento.start_time is not None
        ):
            horas = (evento.start_time - ahora).total_seconds() / 3600
            if VENTANA_HORAS[0] <= horas <= VENTANA_HORAS[1]:
                proximos.append(evento)

    proximos.sort(key=lambda e: e.start_time)

    if not proximos:
        await res.error(_("esports.sin_proximos", horas=VENTANA_HORAS[1]))
        return

    enviados = 0
    for evento in proximos[:MAX_PARTIDOS]:
        try:
            crudo = await cog.tracker.api_client.get_event_details(evento.match_id)
            detalles = EventDetails(crudo.get("data", {}).get("event", {}))

            partido = TrackedMatch(detection_time=ahora, scheduleEvent_obj=evento)
            await partido.enrich_from_event_details(detalles)

            embed = await EmbedService.create_upcoming_embed(partido)
            if embed:
                await res.send(embed=embed)
                enviados += 1
        except Exception:
            log.exception("Error preparando el partido %s.", evento.match_id)
            continue

    if enviados == 0:
        # Antes, si los tres fallaban, el comando no decía absolutamente nada.
        await res.error(_("esports.fallo_proximos"))


# ---------------------------------------------------------------------- #
# Los canales de avisos (SoloQ y esports) se configuran con /subscribe,
# /unsubscribe, /channels y /mute, que viven juntos en
# `core/notification_config_commands.py`: configurar canales es una cosa, no
# dos, y tener la mitad aquí obligaba a mantener dos veces lo mismo. Se
# movieron el 22-09-2026.
# ---------------------------------------------------------------------- #

# ---------------------------------------------------------------------- #
# Registro
# ---------------------------------------------------------------------- #

async def setup(bot: commands.Bot) -> None:
    from esports_extension.services.api import APIClient
    from esports_extension.services.tracker_service import TrackerService

    cog = EsportsCommands(bot, TrackerService(APIClient()))
    bot.add_cog(cog)

    # Los cuerpos van fuera de la clase, así que hay que darles el cog. Se
    # captura en la clausura en vez de pasarlo por parámetro para que la firma
    # sea la que `slash` espera.
    # `league` es opcional y filtra sobre los partidos que el tracker ya tiene
    # en memoria: no genera ninguna llamada. La comparación es laxa a propósito
    # (ver `_liga_del_partido`), porque el nombre de la liga lo pone la API de
    # esports de Riot y no tiene por qué coincidir letra a letra con el nuestro.
    slash_opciones_cog(
        cog,
        bot,
        "cmd.esports.name",
        "cmd.esports.desc",
        lambda res, valores: _cuerpo_partida(cog, res, valores),
        opciones=(
            ("cmd.esports.arg", "cmd.esports.arg_desc",
             {nombre: codigo for codigo, nombre in LIGAS.items()}, ""),
        ),
    )
    slash_cog(
        cog,
        bot,
        "cmd.schedule.name",
        "cmd.schedule.desc",
        lambda res: _cuerpo_next(cog, res),
    )
    # Los dos comandos del canal de esports (`setlivechannel` y
    # `removelivechannel`) ya no están aquí: se unificaron con los de SoloQ en
    # `/subscribe`, `/unsubscribe`, `/channels` y `/mute`
    # (`core/notification_config_commands.py`), porque configurar canales es una
    # sola cosa y tenerla partida en dos sitios duplicaba permisos y avisos.

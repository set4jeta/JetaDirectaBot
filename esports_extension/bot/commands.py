"""Comandos de esports: `/partida`, `/next`, `/setlivechannel`, `/removelivechannel`.

Qué se cambió
-------------
1. **Los cuatro son ahora slash y prefijo a la vez.** Viven en un Cog porque
   comparten el `TrackerService` (y su `bg_task` de 30 s), así que no se podían
   pasar por `dual` directamente: nextcord exige `self` en los comandos
   declarados dentro de una clase. La solución es `dual_cog`, que registra
   contra el bot un cuerpo con el cog ya capturado en la clausura.
2. **`setlivechannel` y `removelivechannel` piden *Gestionar servidor*.** No
   comprobaban nada: cualquiera podía redirigir —o apagar— las notificaciones de
   esports de todo el servidor. Es el mismo agujero que tenía `!setchannel`.
3. **`print` → logging.** Eran 12 llamadas, varias dentro del bucle de 30
   segundos, y `[DEBUG] match_id=... status=...` se imprimía por cada partido
   trackeado **cada vez que alguien escribía `!partida`**. Ahora es `log.debug`,
   así que solo sale con `LOG_LEVEL=DEBUG`.
4. **`bg_task` ya no avisa a grito pelado cuando un servidor no tiene canal.**
   Ese `print` salía cada 30 s por cada servidor sin configurar; ahora es debug.
5. **Se avisa una sola vez de los partidos ya empezados.** Igual que antes.
6. **Dos `IndexError` latentes tapados.** `match.teamsEventDetails[0]` y
   `match.trackedGames[0]` se indexaban sin comprobar que la lista tuviera algo.
   Con un partido a medio enriquecer eso reventaba el comando entero; en slash
   eso se ve como "la aplicación no responde".
7. **Traducidos.** Eran los últimos cuatro comandos íntegramente en español: 12
   mensajes a pelo y las cuatro descripciones de la lista de Discord. Ahora
   pasan por `utils.i18n` como el resto, así que un servidor con `/lang en`
   recibe `/partida` y `/next` en inglés.
"""

from __future__ import annotations

import copy

import nextcord
from nextcord.ext import commands, tasks

from core import health as salud
from core.dual_command import PERMISO_ADMIN, dual_cog
from core.responder import Respuesta
from esports_extension.models.match import EventDetails, ScheduleEvent
from esports_extension.models.tracker import TrackedMatch, TrackedStatus
from esports_extension.services.embed_service import EmbedService
from esports_extension.services.storage import (
    load_notification_channel,
    remove_notification_channel,
    save_notification_channel,
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
                        "Servidor %s sin canal de esports (usa /setlivechannel).",
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
                await self.tracker.notify_new_games(channel)
        except Exception:
            log.exception("Error repartiendo las notificaciones de esports.")

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

async def _cuerpo_partida(cog: EsportsCommands, res: Respuesta) -> None:
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
# /setlivechannel · /removelivechannel
# ---------------------------------------------------------------------- #

async def _cuerpo_setlivechannel(cog: EsportsCommands, res: Respuesta) -> None:
    _ = tr(res.guild_id)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(_("esports.canal_solo_admin"))
        return

    canal = res.canal
    try:
        save_notification_channel(res.guild_id, canal.id)
    except OSError:
        log.exception("No se pudo guardar el canal de esports.")
        await res.error(_("esports.canal_fallo_guardar"))
        return

    aviso = ""
    if isinstance(canal, nextcord.TextChannel) and res.guild is not None:
        permisos = canal.permissions_for(res.guild.me)
        faltan = [
            nombre
            for nombre, tiene in (
                (_("permisos.enviar_mensajes"), permisos.send_messages),
                (_("permisos.insertar_enlaces"), permisos.embed_links),
                (_("permisos.adjuntar_archivos"), permisos.attach_files),
            )
            if not tiene
        ]
        if faltan:
            # La misma clave que usa `/setchannel`: es el mismo aviso y no tiene
            # sentido mantener dos redacciones del mismo problema.
            aviso = _(
                "setchannel.sin_permisos_canal",
                permisos=", ".join(f"**{p}**" for p in faltan),
            )

    mencion = (
        canal.mention
        if isinstance(canal, nextcord.TextChannel)
        else _("setchannel.este_canal")
    )
    await res.send(_("esports.canal_ok", canal=mencion, aviso=aviso))


async def _cuerpo_removelivechannel(cog: EsportsCommands, res: Respuesta) -> None:
    _ = tr(res.guild_id)

    if res.guild_id is None:
        await res.error(_("error.solo_en_servidor"))
        return
    if not res.es_admin():
        await res.error(_("error.solo_admin"))
        return

    try:
        remove_notification_channel(res.guild_id)
    except OSError:
        log.exception("No se pudo borrar el canal de esports.")
        await res.error(_("esports.canal_fallo_borrar"))
        return

    await res.send(_("esports.canal_desactivado"))


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
    # sea la que `dual` espera.
    dual_cog(
        cog,
        bot,
        "partida",
        "cmd.partida.desc",
        lambda res: _cuerpo_partida(cog, res),
    )
    dual_cog(
        cog,
        bot,
        "next",
        "cmd.next.desc",
        lambda res: _cuerpo_next(cog, res),
    )
    dual_cog(
        cog,
        bot,
        "setlivechannel",
        "cmd.setlivechannel.desc",
        lambda res: _cuerpo_setlivechannel(cog, res),
        permiso=PERMISO_ADMIN,
    )
    dual_cog(
        cog,
        bot,
        "removelivechannel",
        "cmd.removelivechannel.desc",
        lambda res: _cuerpo_removelivechannel(cog, res),
        permiso=PERMISO_ADMIN,
    )

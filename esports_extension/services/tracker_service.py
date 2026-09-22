
from datetime import datetime
from typing import List
from esports_extension.models.match import ScheduleEvent, EventDetails   # Asegúrate de que tu api.py esté en models/
from esports_extension.models.live import LiveStats
from esports_extension.models.tracker import TrackedMatch, TrackedStatus
from esports_extension.services.api import APIClient, LolEsportsError
from esports_extension.utils.time_utils import get_network_time
from esports_extension.services.storage import save_tracked_matches, load_tracked_matches, cleanup_completed_matches_in_memory # Asegúrate de que tu api.py esté en services/
from esports_extension.services.embed_service import EmbedService
from esports_extension.services.chat_winner_detector import analyze_chat_and_update_wins
from esports_extension.services.storage import load_notified_games, save_notified_games

from esports_extension.utils.buttons import ScoreButtonView

from utils.logger import get_logger

log = get_logger("esports.tracker")
   



        
            


class TrackerService:
    def __init__(self, api_client: APIClient):
        
        
        
        self.api_client = api_client
        self.tracked_matches = {
            m.match_id: m for m in load_tracked_matches("tracked_matches.json")
        }
        
        self.SLUG_PRIORITY = (
    "worlds", "first_stand", "msi", "lck", "lpl", "lec", "lta_cross", "lta_n", "lta_s", "emea_masters",
    "lcs", "lck_challengers_league", "nacl", "superliga", "nlc", "lfl", "north_regional_league",
    "south_regional_league", "primeleague", "tcl", "lcp", "vcs", "ljl-japan", "pcs", "cd",
    "arabian_league", "lla", "cblol-brazil", "lco", "lit", "hitpoint_masters", "esports_balkan_league",
    "hellenic_legends_league", "rift_legends", "roadoflegends", "tft_esports", "duelo_de_reyes",
    "wqs", "lcl"
)


    async def detect_live_matches(self) -> List[TrackedMatch]:
        start_time = datetime.now()  # Marca el inicio
        now = await get_network_time()
        if now is not None:
            log.debug(f"Network time: {now.isoformat()}")
        else:
            log.debug("Network time: None")
        data = await self.api_client.get_schedule()
        
        raw_events = data.get("data", {}).get("schedule", {}).get("events", [])

        live_matches = []

        for raw_event in raw_events:
            if not raw_event or not isinstance(raw_event, dict):
                continue  # Salta eventos nulos o mal formateados

            # Salta eventos sin match o con match=None
            if "match" not in raw_event or raw_event.get("match") is None:
                log.debug("Evento sin match o match=None: %s", raw_event)
                continue
            elif not isinstance(raw_event.get("match"), dict):
                log.debug("Evento con match no dict: %s", raw_event)
                continue

            evento = ScheduleEvent(raw_event)

            if evento.type != "match":
                continue

            hora = await evento.hora_de_inicio()
            if hora is None or not (-8 <= hora <= 8):
                continue

            #if evento.state not in ("inProgress", "completed"):
                #continue

            if evento.match_id in self.tracked_matches:
                tracked = self.tracked_matches[evento.match_id]
                await tracked.update_last_checked() 
            else:
                log.debug(f"[👀] Partido en vivo detectado: {evento.league_name} (match_id: {evento.match_id})")
                log.debug(f"[📌] Estado cambiado a DETECTED")
                tracked = await TrackedMatch.from_schedule_event(evento)

            
            log.debug(f"[📥] Obteniendo EventDetails para match_id: {evento.match_id}")
            try:
                event_data = await self.api_client.get_event_details(evento.match_id)
            except Exception as e:
                log.error(f"Error API: {str(e)}")
                continue
            
            await tracked.enrich_from_event_details(EventDetails(event_data.get("data", {}).get("event", {})))
            log.debug(f"[TRACKER] Procesando match_id={evento.match_id}, estado={evento.state}, best_of={evento.best_of_count}")
            # Buscar algún juego inProgress dentro de EventDetails
            for tracked_game in tracked.trackedGames:
                if tracked_game.state not in ("inProgress", "unstarted"):
                    if tracked_game.state == "completed":
                        await self._completar_por_frames(tracked, tracked_game)
                    continue

                log.debug(
                    "[🎮] Juego activo: game_id=%s state=%s",
                    tracked_game.game_id, tracked_game.state,
                )

                # UNA sola petición por juego y por vuelta.
                #
                # Antes había dos: una sin `startingTime` y otra, unas líneas más
                # abajo, con `ahora - 37s`. La segunda pedía **los mismos datos**
                # y encima el feed la rechazaba siempre con 400 (exige que la
                # ventana termine hace 600 s o más; ver `api.get_livestats`). Eso
                # es lo que llenaba la consola de
                # "ERROR | esports.tracker | Error al obtener LiveStats: Error 400".
                try:
                    crudo = await self.api_client.get_livestats(tracked_game.game_id)
                except LolEsportsError as e:
                    if e.status == 204:
                        # La partida existe pero aún no manda datos: es el estado
                        # normal antes del inicio, no una avería.
                        log.debug(
                            "[🟡] game_id=%s sin datos todavía (204).", tracked_game.game_id
                        )
                        tracked_game.draft_in_progress = False
                        tracked_game.has_participants = False
                    elif e.status == 404:
                        # El feed ya no sirve esta partida: normalmente ha
                        # terminado y el marcador oficial tarda en actualizarse.
                        # Esta rama existía desde siempre y **nunca se ejecutaba**,
                        # porque el error que llegaba no llevaba `status`.
                        log.debug(
                            "[TRACKER] 404 en game_id=%s -> ganador por chat.",
                            tracked_game.game_id,
                        )
                        winner_code = await analyze_chat_and_update_wins(tracked.eventDetails)  # type: ignore
                        if winner_code:
                            log.debug(f"[🏆] Ganador detectado por chat: {winner_code}")
                    else:
                        log.error("Error al obtener LiveStats: %s", e)
                    continue
                except Exception as e:
                    log.error("Error al obtener LiveStats: %s", e)
                    continue

                await tracked_game.enrich_from_live_stats(LiveStats(crudo))

                if not tracked_game.live_blue_metadata or not tracked_game.live_red_metadata:
                    log.warning(f"No hay metadata disponible para game {tracked_game.number}")

                # El feed contesta 200: la partida ha empezado (o está en draft),
                # así que un "unstarted" del calendario está desactualizado.
                if tracked_game.state == "unstarted":
                    log.debug(
                        "[⚡] Forzando inProgress por LiveStats: game_id=%s",
                        tracked_game.game_id,
                    )
                    tracked_game.state = "inProgress"
                    tracked.state = "inProgress"
                    if tracked_game.real_start_time is None:
                        tracked_game.real_start_time = await get_network_time()

                log.debug(
                    "[TRACKER] game_id=%s has_participants=%s draft=%s state=%s",
                    tracked_game.game_id, tracked_game.has_participants,
                    tracked_game.draft_in_progress, tracked_game.state,
                )
                        
            
            
            
            
            
            
            
            
            # Al final, si algún juego está en progreso, marca la serie como inProgress    
            # Refuerzo: el estado de la serie debe reflejar el estado real de los juegos
            if tracked.trackedGames:
                if all(g.state in ("completed", "unneeded") for g in tracked.trackedGames):
                    tracked.state = "completed"
                elif any(g.state == "inProgress" for g in tracked.trackedGames):
                    tracked.state = "inProgress"
                else:
                    tracked.state = "notStarted"
            # ...existing code...    
                            
            await self._update_tracking(tracked)
            log.debug(f"[🧠] Tracking actualizado para match_id: {tracked.match_id}")
            
            live_matches.append(tracked)   
        
            
            
            

           

            
        
        
         # 🔸 Verificar si algún TrackedMatch ya terminó
        
        
         
        log.debug(f"[+] Actualizando partidos del tracker: {len(self.tracked_matches)}")    
        await self.update_completed_matches()
        log.debug(f"[+] Actualizando partidos completados en memoria")
        await cleanup_completed_matches_in_memory(self.tracked_matches, hours=2)
        
        
        log.debug(f"[+] Guardando partidos trackeados en tracked_matches.json")
        await save_tracked_matches(list(self.tracked_matches.values()), "tracked_matches.json")
        
       
        
        end_time = datetime.now()  # Marca el final
        duration = (end_time - start_time).total_seconds()
        log.debug(f"[⏱️] detect_live_matches tardó {duration:.2f} segundos en ejecutarse")
        return await self._prioritize_matches(live_matches)
        

    async def _completar_por_frames(self, tracked: TrackedMatch, tracked_game) -> None:
        """Deduce el ganador de un mapa ya terminado leyendo sus últimos frames.

        Solo actúa cuando el marcador oficial va por detrás de los mapas
        jugados: si se han jugado 2 mapas pero `game_wins` suma 1, falta un
        resultado. El feed de LiveStats sigue sirviendo la partida un rato
        después del final, y en el último frame ya viene quién ganó.

        Estaba en línea dentro del bucle de `detect_live_matches`, mezclado con
        las dos ramas de partida activa. Se saca aparte porque el bucle ahora
        descarta de golpe todo lo que no está activo (`continue`), y porque así
        el caso "mapa terminado" se lee de una vez en lugar de rastrearlo entre
        los `if` de los otros estados.
        """
        equipos = tracked.teamsEventDetails
        if not equipos or len(equipos) < 2:
            return

        jugados = equipos[0].game_wins + equipos[1].game_wins
        if jugados >= tracked_game.number:
            # El marcador ya está al día: no hay nada que deducir y no se gasta
            # una petición.
            return

        try:
            crudo = await self.api_client.get_livestats(tracked_game.game_id)
        except LolEsportsError as e:
            if e.status in (204, 404):
                # El feed ya no guarda esta partida. No es una avería: el
                # marcador se acabará actualizando por el schedule.
                log.debug(
                    "[TRACKER] Sin frames para deducir game_id=%s (HTTP %s).",
                    tracked_game.game_id, e.status,
                )
            else:
                log.error("Error al deducir ganador por frames: %s", e)
            return
        except Exception as e:
            log.error("Error al deducir ganador por frames: %s", e)
            return

        await tracked_game.enrich_from_live_stats(LiveStats(crudo))
        log.debug(
            "[DEDUCCIÓN] Ganador por frames para game_id=%s (marcador %s de %s mapas).",
            tracked_game.game_id, jugados, tracked_game.number,
        )

    async def _update_tracking(self, tracked: TrackedMatch):
        
        if tracked.match_id not in self.tracked_matches:
            self.tracked_matches[tracked.match_id] = tracked
        else:
            await self.tracked_matches[tracked.match_id].update_last_checked()

    async def _prioritize_matches(self, matches: List[TrackedMatch]) -> List[TrackedMatch]:
        return sorted(
            matches,
            key=lambda m: (
                self.SLUG_PRIORITY.index(m.slug.lower()) if m.slug and m.slug.lower() in self.SLUG_PRIORITY else 999,
                m.start_time
            )
        )
    async def update_completed_matches(self):
        updated = False
        now = await get_network_time()
        log.debug(f"Network time: {now.isoformat() if now else 'None'}")
        
        

        for match_id, tracked in self.tracked_matches.items():
            # 1. Saltar partidos ya completados
            if tracked.status == TrackedStatus.COMPLETED:
                continue

         

            # 3. Si el estado general del partido es "completed" (por la API)
            if tracked.state == "completed":
                log.debug(f"[+] Partido completado: {tracked.match_id}")
                tracked.status = TrackedStatus.COMPLETED
                updated = True
                continue  # Ya está completado, no hace falta revisar más

            # 4. ¿El schedule marca este partido como "completed"?
            try:
                schedule_data = await self.api_client.get_schedule()
                raw_events = schedule_data.get("data", {}).get("schedule", {}).get("events", [])
                current_event = next((e for e in raw_events if e.get("match", {}).get("id") == match_id), None)
                if current_event and current_event.get("state") == "completed":
                    # --- NUEVO: Verifica EventDetails antes de marcar como completado ---
                    try:
                        event_data = await self.api_client.get_event_details(match_id)
                        event_details = EventDetails(event_data.get("data", {}).get("event", {}))
                        # Si hay algún juego inProgress, NO marcar como completado
                        if any(g.state == "inProgress" for g in event_details.gamesEventDetails):
                            log.warning(f"Schedule dice completed pero EventDetails tiene juegos activos: {match_id}")
                            continue  # No marcar como completado
                    except Exception as e:
                        log.error(f"Error verificando EventDetails para {match_id}: {e}")
                        # Si falla la API, mejor no marcar como completado
                        continue

                    log.debug(f"[📅] Serie completada según Schedule: {match_id}")
                    tracked.status = TrackedStatus.COMPLETED
                    updated = True
                    continue  # Ya está completado, no hace falta revisar más
            except Exception as e:
                log.error(f"Error al obtener schedule: {e}")

            
            
            # 5. Marcar juegos inactivos como completados (opcional)
            #for tracked_game in tracked.trackedGames:
                #if tracked_game.state == "inProgress" and tracked_game.last_frame_time:
                   # if (now - tracked_game.last_frame_time).total_seconds() > 60:
                        #print(f"[⏱️] Juego inactivo por falta de frames: {tracked_game.game_id}")
                        #tracked_game.state = "completed"
                       # updated = True

            # 6. Si TODOS los juegos están completados o no se jugaron, marca el partido como COMPLETED
            if all(game.state in ("completed", "unneeded") for game in tracked.trackedGames):
                log.debug(f"[🏆] Todos los juegos completados: {match_id}")
                tracked.status = TrackedStatus.COMPLETED
                tracked.state = "completed"
                updated = True

        # 7. Eliminar partidos completados de self.tracked_matches
        completed_ids = [match_id for match_id, match in self.tracked_matches.items() if match.status == TrackedStatus.COMPLETED]
        for match_id in completed_ids:
            log.debug(f"[🧹] Eliminando match completado de memoria: {match_id}")
            del self.tracked_matches[match_id]

        # 8. Guardar si hubo cambios
        if updated or completed_ids:
            await save_tracked_matches(list(self.tracked_matches.values()), "tracked_matches.json")
            log.debug("Guardado exitoso de partidos completados y limpieza de memoria")

        
    
    

    async def notify_new_games(self, channel):
        notified_games = load_notified_games()
        updated = False
        for match in self.tracked_matches.values():
            for tracked_game in reversed(match.trackedGames):
                game_id = tracked_game.game_id
                notified_channels = set(notified_games.get(game_id, []))
                if (
                    tracked_game.state == "inProgress"
                    and channel.id not in notified_channels
                    and tracked_game.live_blue_metadata
                    and tracked_game.live_red_metadata
                    and tracked_game.live_blue_metadata.participants
                    and tracked_game.live_red_metadata.participants
                ):
                    try:
                        embed = await EmbedService.create_live_match_embed(match, is_notification=True)
                        # Extrae los equipos igual que en el embed
                        tracked_game = next(
                            (g for g in reversed(match.trackedGames)
                            if g.state == "inProgress"
                            and g.live_blue_metadata
                            and g.live_red_metadata
                            and g.live_blue_metadata.participants
                            and g.live_red_metadata.participants),
                            None
                        )
                        if tracked_game and match.teamsEventDetails:
                            blue_team = next((t for t in match.teamsEventDetails if tracked_game.live_blue_metadata and t.id == tracked_game.live_blue_metadata.team_id), None)
                            red_team = next((t for t in match.teamsEventDetails if tracked_game.live_red_metadata and t.id == tracked_game.live_red_metadata.team_id), None)
                            
                            blue_wins = blue_team.game_wins if blue_team else 0
                            red_wins = red_team.game_wins if red_team else 0

                            if blue_wins > 0 or red_wins > 0:
                                await channel.send(embed=embed, view=ScoreButtonView(blue_wins, red_wins))
                            else:
                                await channel.send(embed=embed)
                        else:
                            await channel.send(embed=embed)
                        notified_channels.add(channel.id)
                        notified_games[game_id] = list(notified_channels)
                        save_notified_games(notified_games)
                        if tracked_game and hasattr(tracked_game, "number"):
                            log.info(
                                "Juego %s notificado en el canal %s",
                                tracked_game.number, channel.id,
                            )
                        else:
                            log.info(
                                "Juego notificado en el canal %s (sin número de mapa)",
                                channel.id,
                            )
                        updated = True
                    except Exception as e:
                        if tracked_game and hasattr(tracked_game, "number"):
                            log.error(f"Error notificando juego {tracked_game.number}: {e}")
                        else:
                            log.error(f"Error notificando juego: {e}")
                        continue
        if updated:
            log.debug("Guardado post-notificación exitoso")
            
   


## 🟢 Creamos el cliente que sabe cómo llamar a la API
#api = APIClient()

# 🟢 Creamos el tracker, y le pasamos ese cliente
#tracker = TrackerService(api)

# 🔵 Desde aquí, tracker puede usar el cliente internamente:
#await tracker.api_client.get_schedule()
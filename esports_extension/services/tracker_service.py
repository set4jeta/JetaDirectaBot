
from datetime import datetime, timezone
from typing import Any, List, Dict, Optional
from esports_extension.models.match import ScheduleEvent, EventDetails   # Asegúrate de que tu api.py esté en models/
from esports_extension.models.live import LiveStats
from esports_extension.models.tracker import TrackedMatch, TrackedStatus
from esports_extension.services.api import APIClient
from esports_extension.utils.time_utils import get_network_time, round_down_to_10_seconds
from esports_extension.services.storage import save_tracked_matches, load_tracked_matches, cleanup_completed_matches_in_memory, save_firestore_data, load_firestore_data # Asegúrate de que tu api.py esté en services/
from esports_extension.services.embed_service import EmbedService
from esports_extension.services.chat_winner_detector import analyze_chat_and_update_wins
from esports_extension.services.storage import load_notified_games, save_notified_games

from esports_extension.utils.buttons import ScoreButtonView

from datetime import datetime, timedelta, timezone
from enum import Enum
import copy
   



        
            


class TrackerService:
    def __init__(self, api_client: APIClient):
        
        
        
        self.api_client = api_client
        self.tracked_matches = {
            m.match_id: m for m in load_tracked_matches("tracked_matches.json")
        }
        self.firestore_data = load_firestore_data()# 🔹 Carga partidos previamente trackeados
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
            print(f"[DEBUG] Network time: {now.isoformat()}")
        else:
            print("[DEBUG] Network time: None")
        data = await self.api_client.get_schedule()
        
        raw_events = data.get("data", {}).get("schedule", {}).get("events", [])

        live_matches = []

        for raw_event in raw_events:
            if not raw_event or not isinstance(raw_event, dict):
                continue  # Salta eventos nulos o mal formateados

            # Salta eventos sin match o con match=None
            if "match" not in raw_event or raw_event.get("match") is None:
                print("[DEBUG] Evento sin match o match=None:", raw_event)
                continue
            elif not isinstance(raw_event.get("match"), dict):
                print("[DEBUG] Evento con match no dict:", raw_event)
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
                print(f"[👀] Partido en vivo detectado: {evento.league_name} (match_id: {evento.match_id})")
                print(f"[📌] Estado cambiado a DETECTED")
                tracked = await TrackedMatch.from_schedule_event(evento)

            
            print(f"[📥] Obteniendo EventDetails para match_id: {evento.match_id}")
            try:
                event_data = await self.api_client.get_event_details(evento.match_id)
            except Exception as e:
                print(f"[❌] Error API: {str(e)}")
                continue
            
            await tracked.enrich_from_event_details(EventDetails(event_data.get("data", {}).get("event", {})))
            print(f"[TRACKER] Procesando match_id={evento.match_id}, estado={evento.state}, best_of={evento.best_of_count}")
            # Buscar algún juego inProgress dentro de EventDetails
            for tracked_game in tracked.trackedGames:
                if tracked_game.state in ("inProgress", "unstarted"):
                    print(f"[🎮] Juego en progreso detectado: game_id={tracked_game.game_id}")
                    print(f"[📡] Obteniendo datos de LiveStats para game_id={tracked_game.game_id}, state={tracked_game.state}")
                    
                 
                    # --- NUEVO: Consulta LiveStats SIN startingTime ---
                    try:
                        live_stats_raw_simple = await self.api_client.get_livestats(tracked_game.game_id)
                        print(f"[📊] LiveStats para game {tracked_game.number}: game_id={tracked_game.game_id}")
                        # Si responde 200, la partida ha comenzado (o está en draft)
                        await tracked_game.enrich_from_live_stats(LiveStats(live_stats_raw_simple))
                        print(f"[Firestore] Forzando guardado para game_id: {tracked_game.game_id}")
                        await self._update_firestore_game(tracked_game.game_id)
                        if not tracked_game.live_blue_metadata or not tracked_game.live_red_metadata:
                            print(f"[⚠️] No hay metadata disponible para game {tracked_game.number}")
                        
                        if tracked_game.state == "unstarted":
                            print(f"[⚡] Forzando estado a inProgress por LiveStats (sin startingTime) para game_id={tracked_game.game_id}")
                            tracked_game.state = "inProgress"
                            tracked.state = "inProgress"
                            
                    except Exception as e:
                        if getattr(e, "status", None) == 204:
                            print(f"[TRACKER] LiveStats 204: game_id={tracked_game.game_id} -> Esperando partida (has_participants={tracked_game.has_participants}, draft_in_progress={tracked_game.draft_in_progress})")
                            tracked_game.draft_in_progress = False
                            tracked_game.has_participants = False
                        else:
                            print(f"[INFO] No hay partida activa para activa aún para esta Serie (LiveStats 204).")
                                
               
                    
                  
                    
                if tracked_game.state == "inProgress": 
                    
                    try:
                                    # Siempre pide el frame más reciente posible
                        dt = await get_network_time()
                        if dt is not None:
                            dt = dt - timedelta(seconds=37)
                            dt = round_down_to_10_seconds(dt)
                            starting_time = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                        else:
                            print("[❌] Error: get_network_time() returned None")
                            continue

                        live_stats_raw = await self.api_client.get_livestats(tracked_game.game_id, starting_time=starting_time)
                        await tracked_game.enrich_from_live_stats(LiveStats(live_stats_raw))
                        print(f"[TRACKER] Post-LiveStats: game_id={tracked_game.game_id}, has_participants={tracked_game.has_participants}, draft_in_progress={tracked_game.draft_in_progress}, state={tracked_game.state}")
                        print(f"[Firestore] Forzando guardado para game_id: {tracked_game.game_id}")
                        await self._update_firestore_game(tracked_game.game_id)                                    # Si no hay participantes, sigue siendo draft
                      
                                    # --- NUEVO: Si LiveStats responde y el estado es "unstarted", forzar a "inProgress" ---
                        if tracked_game.state == "unstarted":
                            print(f"[⚡] Forzando estado a inProgress por LiveStats para game_id={tracked_game.game_id}")
                            tracked_game.state = "inProgress"
                            # Opcional: también puedes marcar la serie como inProgress si al menos un juego lo está
                            tracked.state = "inProgress"  
                            # Si no hay real_start_time, asígnalo ahora
                            if not tracked_game.real_start_time:
                                tracked_game.real_start_time = await get_network_time()        
                        
                        
                                            # --- BLOQUE NUEVO ---
                        print(f"[DEBUG] game_id={tracked_game.game_id} has_participants={tracked_game.has_participants} draft_in_progress={tracked_game.draft_in_progress}")
                        if tracked_game.has_participants and not tracked_game.draft_in_progress:
                            print(f"[Firestore] Actualizando datos para game_id: {tracked_game.game_id}")
                            await self._update_firestore_game(tracked_game.game_id)
                           
                        # --- FIN BLOQUE NUEVO ---
                        
                        
                        
                    except Exception as e:
                        if hasattr(e, "status") and e.status == 404: # type: ignore
                            # Aquí llamas a la función de chat winner detector
                            
                            print(f"[TRACKER] LiveStats 404: game_id={tracked_game.game_id} -> Intentando detectar ganador por chat")
                            # Asegúrate de tener el EventDetails actualizado en tracked
                            winner_code = await analyze_chat_and_update_wins(tracked.eventDetails) # type: ignore
                            if winner_code:
                                print(f"[🏆] Ganador detectado por chat: {winner_code}")
                                # El game_wins ya fue sumado en teamsEventDetails
                        elif getattr(e, "status", None) == 204:
                            print(f"[🟡] Esperando partida para game_id={tracked_game.game_id}, aún no hay datos de partida (sin startingTime).")
                            tracked_game.draft_in_progress = False
                            tracked_game.has_participants = False
                        else:
                            print(f"[❌] Error al obtener LiveStats: {e}")
            
                if tracked_game.state == "completed":
                    # Solo si el score no está actualizado (ejemplo: ambos equipos tienen menos wins de los que deberían)
                    if tracked.teamsEventDetails and len(tracked.teamsEventDetails) >= 2:
                        blue_wins = tracked.teamsEventDetails[0].game_wins
                        red_wins = tracked.teamsEventDetails[1].game_wins
                        if (blue_wins + red_wins) < tracked_game.number:
                            try:
                                live_stats_raw = await self.api_client.get_livestats(tracked_game.game_id)
                                await tracked_game.enrich_from_live_stats(LiveStats(live_stats_raw))
                                print(f"[DEDUCCIÓN] Forzando deducción de ganador por frames para game_id={tracked_game.game_id}")
                            except Exception as e:
                                print(f"[❌] Error al deducir ganador por frames en juego terminado: {e}")
                        
            
            
            
            
            
            
            
            
            # Al final, si algún juego está en progreso, marca la serie como inProgress    
            if any(g.state == "inProgress" for g in tracked.trackedGames):
                tracked.state = "inProgress"    
                            
            await self._update_tracking(tracked)
            print(f"[🧠] Tracking actualizado para match_id: {tracked.match_id}")
            
            live_matches.append(tracked)   
        
            
            
            

           

            
        
        
         # 🔸 Verificar si algún TrackedMatch ya terminó
        
        
         
        print(f"[+] Actualizando partidos del tracker: {len(self.tracked_matches)}")    
        await self.update_completed_matches()
        print(f"[+] Actualizando partidos completados en memoria")
        await cleanup_completed_matches_in_memory(self.tracked_matches, hours=2)
        print(f"[+] Guardando partidos trackeados en tracked_matches.json")
        await save_tracked_matches(list(self.tracked_matches.values()), "tracked_matches.json")
        
       
        
        end_time = datetime.now()  # Marca el final
        duration = (end_time - start_time).total_seconds()
        print(f"[⏱️] detect_live_matches tardó {duration:.2f} segundos en ejecutarse")
        return await self._prioritize_matches(live_matches)
        

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
        print(f"[DEBUG] Network time: {now.isoformat() if now else 'None'}")
        
        

        for match_id, tracked in self.tracked_matches.items():
            # 1. Saltar partidos ya completados
            if tracked.status == TrackedStatus.COMPLETED:
                continue

         

            # 3. Si el estado general del partido es "completed" (por la API)
            if tracked.state == "completed":
                print(f"[+] Partido completado: {tracked.match_id}")
                tracked.status = TrackedStatus.COMPLETED
                updated = True
                continue  # Ya está completado, no hace falta revisar más

            # 4. ¿El schedule marca este partido como "completed"?
            try:
                schedule_data = await self.api_client.get_schedule()
                raw_events = schedule_data.get("data", {}).get("schedule", {}).get("events", [])
                current_event = next((e for e in raw_events if e.get("match", {}).get("id") == match_id), None)
                if current_event and current_event.get("state") == "completed":
                    print(f"[📅] Serie completada según Schedule: {match_id}")
                    tracked.status = TrackedStatus.COMPLETED
                    updated = True
                    continue  # Ya está completado, no hace falta revisar más
            except Exception as e:
                print(f"[❌] Error al obtener schedule: {e}")

            
            
            # 5. Marcar juegos inactivos como completados (opcional)
            #for tracked_game in tracked.trackedGames:
                #if tracked_game.state == "inProgress" and tracked_game.last_frame_time:
                   # if (now - tracked_game.last_frame_time).total_seconds() > 60:
                        #print(f"[⏱️] Juego inactivo por falta de frames: {tracked_game.game_id}")
                        #tracked_game.state = "completed"
                       # updated = True

            # 6. Si TODOS los juegos están completados o no se jugaron, marca el partido como COMPLETED
            if all(game.state in ("completed", "unneeded") for game in tracked.trackedGames):
                print(f"[🏆] Todos los juegos completados: {match_id}")
                tracked.status = TrackedStatus.COMPLETED
                tracked.state = "completed"
                updated = True

        # 7. Guardar solo si hubo cambios
        if updated:
            await save_tracked_matches(list(self.tracked_matches.values()), "tracked_matches.json")
            print("[💾] Guardado exitoso de partidos completados")

        
    
    

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
                            print(f"[✅] Juego {tracked_game.number} notificado correctamente en canal {channel.id}")
                        else:
                            print(f"[✅] Juego notificado correctamente en canal {channel.id} (no se pudo obtener número)")
                        updated = True
                    except Exception as e:
                        if tracked_game and hasattr(tracked_game, "number"):
                            print(f"[❌] Error notificando juego {tracked_game.number}: {e}")
                        else:
                            print(f"[❌] Error notificando juego: {e}")
                        continue
        if updated:
            print("[💾] Guardado post-notificación exitoso")
            
    
    async def _update_firestore_game(self, game_id: str) -> None:
        print(f"[Firestore] _update_firestore_game llamado para {game_id}")
        """Actualiza y guarda datos de Firestore para un game_id"""
        if not game_id:
            return
            
        try:
            # 1. Obtener datos de Firestore
            data = await self.api_client.get_firestore_game_data(game_id)
            if not data:
                return

            # 2. Guardar en memoria y disco
            self.firestore_data[game_id] = data
            await save_firestore_data(game_id, data)  # Guarda TODO el archivo
            
        except Exception as e:
            print(f"[Firestore] Error en game_id {game_id}: {str(e)}")
        
        
            
        
          


## 🟢 Creamos el cliente que sabe cómo llamar a la API
#api = APIClient()

# 🟢 Creamos el tracker, y le pasamos ese cliente
#tracker = TrackerService(api)

# 🔵 Desde aquí, tracker puede usar el cliente internamente:
#await tracker.api_client.get_schedule()
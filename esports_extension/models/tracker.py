from datetime import datetime, timezone
from typing import Any, List, Dict, Optional
from esports_extension.models.match import ScheduleEvent, EventDetails, TeamEventDetails, GameEventDetails, VodGameEventDetails
from esports_extension.models.live import LiveStats, LiveTeamMetadata, LiveFrame
from esports_extension.utils.time_utils import get_network_time
from enum import Enum
import copy

class TrackedStatus(Enum):
    DETECTED = "detected"
    COMPLETED = "completed"


class TrackedGame :
    def __init__(self, gameEventDetails_obj: GameEventDetails):
        
        # ...tus variables serializadas...
        self.paused: bool = False
        self.pause_start_time: Optional[datetime] = None
        self.total_paused_duration: float = 0.0  # NO serialices estas
        self.gold_history = []  # Guarda tuplas (blue_gold, red_gold)
        self.stagnant_gold_frames = 0  # Contador de frames estancados
        
        self.game_id = gameEventDetails_obj.id
        self.number = gameEventDetails_obj.number  
        self.state = gameEventDetails_obj.state
        self.vods = gameEventDetails_obj.vods
        self.draft_in_progress: bool = False
        self.has_participants: bool = False 
        self.notified_time: Optional[datetime] = None
        self.notified_game: bool = False
        self.real_start_time: Optional[datetime] = None
        self.finished_time: Optional[datetime] = None
        self.parent_match = None # Referencia al TrackedMatch padre, se asigna después  

        # Live data
        self.live_patch: Optional[str] = None
        self.live_blue_metadata: Optional[LiveTeamMetadata] = None
        self.live_red_metadata: Optional[LiveTeamMetadata] = None
        self.live_frames: List[LiveFrame] = []
        self.last_frame_time: Optional[datetime] = None

    async def enrich_from_live_stats(self, liveStats_obj: LiveStats):
      
            # Verifica que el game_id coincide
        if liveStats_obj.game_id and liveStats_obj.game_id != self.game_id:
            print(f"[⚠️] LiveStats game_id ({liveStats_obj.game_id}) no coincide con tracked_game.game_id ({self.game_id})")
            return

        # Solo actualiza metadata si corresponde a este juego
        if liveStats_obj.game_id == self.game_id:
            self.live_patch = liveStats_obj.patch_version
            self.live_blue_metadata = liveStats_obj.blueTeamMetadata
            self.live_red_metadata = liveStats_obj.redTeamMetadata
        else:
            # Si no hay game_id en LiveStats, limpia la metadata para evitar usar datos viejos
            self.live_blue_metadata = None
            self.live_red_metadata = None
            self.has_participants = False
            print(f"[🔄] Limpiando metadata vieja para game_id={self.game_id}")
 
        
        
        
        
        
        
        
        
        # Detectar inicio real por oro
        if liveStats_obj.frames:
            for frame in liveStats_obj.frames:
                print(f"[FRAME] {frame.timestamp} | {frame.gameState}")
            
            last_frame = liveStats_obj.frames[-1]
            blue_gold = getattr(last_frame.blue_team, "total_gold", 0)
            red_gold = getattr(last_frame.red_team, "total_gold", 0)
            print(f"[DEBUG] blue_gold={blue_gold}, red_gold={red_gold}, real_start_time={self.real_start_time}")
            if (
                self.state == "inProgress" or
                (self.state == "unstarted" and (blue_gold > 2500 or red_gold > 2500))
            ):
                self.state = "inProgress"   
                # Solo asigna el inicio real si aún no está asignado y el oro subió
                #if (blue_gold > 2500 or red_gold > 2500) and not self.real_start_time:
                   #print("[DEBUG] Asignando real_start_time")
                    #self.real_start_time = await get_network_time()
        
        
        
        
        
        # ...existing code...

        if liveStats_obj.frames:
            for frame in liveStats_obj.frames:
                blue_gold = getattr(frame.blue_team, "total_gold", 0)
                red_gold = getattr(frame.red_team, "total_gold", 0)

                # Guarda historial de oro (máximo 5 frames)
                self.gold_history.append((blue_gold, red_gold))
                if len(self.gold_history) > 5:
                    self.gold_history.pop(0)

            # Detecta oro estancado en los últimos 3 frames
            if len(self.gold_history) >= 3:
                last = self.gold_history[-1]
                stagnant = all(g == last for g in self.gold_history[-3:])
                if stagnant and last != (0, 0):  # No cuenta si es inicio de partida
                    self.stagnant_gold_frames += 1
                else:
                    self.stagnant_gold_frames = 0

                # Si el oro lleva 3+ frames estancado, forzar pausa
                if self.stagnant_gold_frames >= 3:
                    if not self.paused:
                        self.paused = True
                        self.pause_start_time = await get_network_time()
                        print(f"[PAUSA-FORZADA] Juego {self.game_id} detectado como PAUSADO por oro estancado")
                else:
                    if self.paused:
                        # Si se reanuda el oro, quitar pausa
                        pause_end = await get_network_time()
                        if pause_end is not None and self.pause_start_time is not None:
                            self.total_paused_duration += (pause_end - self.pause_start_time).total_seconds()
                        self.paused = False
                        self.pause_start_time = None
                        print(f"[REANUDADO-FORZADO] Juego {self.game_id} reanudado por oro en movimiento")
            
            
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        if (
            self.live_blue_metadata and self.live_blue_metadata.participants and
            self.live_red_metadata and self.live_red_metadata.participants
        ):
            self.has_participants = True
            self.draft_in_progress = False
            print(f"[ESTADO] Juego EN VIVO: has_participants=True, draft_in_progress=False")
        elif self.state == "completed":
            self.has_participants = False
            self.draft_in_progress = False
            print(f"[ESTADO] Juego COMPLETADO: has_participants=False, draft_in_progress=False")
        elif self.live_blue_metadata or self.live_red_metadata:
            # Solo marca draft si NUNCA hubo participantes antes
            if not self.has_participants:
                self.has_participants = False
                self.draft_in_progress = True
                print(f"[ESTADO] DRAFT REAL: has_participants=False, draft_in_progress=True")
        else:
            # Solo marca esperando partida si NUNCA hubo participantes antes
            if not self.has_participants:
                self.has_participants = False
                self.draft_in_progress = False
                print(f"[ESTADO] ESPERANDO PARTIDA: has_participants=False, draft_in_progress=False")
        self.live_frames = liveStats_obj.frames
        if liveStats_obj.frames:
            last_frame = liveStats_obj.frames[-1]
            self.last_frame_time = liveStats_obj.frames[-1].timestamp
            # Guarda el timestamp EXACTO como string (no como datetime)
            self.last_frame_time = last_frame._raw_data.get("rfc460Timestamp")
            
            
                        # ...existing code...
            
            # Detectar fin de partida por cualquier frame con finished
            finished_found = any(
                hasattr(frame, "gameState") and frame.gameState == "finished"
                for frame in liveStats_obj.frames
            )
            if finished_found and self.state != "completed":
                print(f"[🟢] Juego {self.game_id} detectado como terminado por frame (gameState=finished en algún frame)")
                self.state = "completed"
                
                self.finished_time = await get_network_time()
            
            
            
            
            
            
            
            
            # --- DEDUCCIÓN DE GANADOR: SIEMPRE QUE EL JUEGO ESTÉ COMPLETADO ---
            if self.state == "completed":
                if self.has_participants:
                    print(f"[FIX] Poniendo en False has_participants en juego completado: {self.game_id}")
                self.has_participants = False
                self.draft_in_progress = False
            
        
                
                                
                
                
                
                
                
                print(f"[DEBUG] Entrando a deducción de ganador para game_id={self.game_id}")
                finished_frame = next((f for f in liveStats_obj.frames if getattr(f, "gameState", "") == "finished"), None)
                if finished_frame:
                    blue_dead = sum(1 for p in finished_frame.blue_team.participants if getattr(p, "hp", 1) == 0)
                    red_dead = sum(1 for p in finished_frame.red_team.participants if getattr(p, "hp", 1) == 0)
                    blue_gold = getattr(finished_frame.blue_team, "total_gold", 0)
                    red_gold = getattr(finished_frame.red_team, "total_gold", 0)
                    blue_inhib = getattr(finished_frame.blue_team, "inhibitors", 0)
                    red_inhib = getattr(finished_frame.red_team, "inhibitors", 0)
                    blue_towers = getattr(finished_frame.blue_team, "towers", 0)
                    red_towers = getattr(finished_frame.red_team, "towers", 0)

                    print(f"[DEDUCCIÓN] Muertos: blue={blue_dead}, red={red_dead} | Oro: blue={blue_gold}, red={red_gold} | Inhibidores: blue={blue_inhib}, red={red_inhib} | Torres: blue={blue_towers}, red={red_towers}")

                    match = getattr(self, "parent_match", None)
                    if match and hasattr(match, "teamsEventDetails") and len(match.teamsEventDetails) == 2:
                        blue_team_id = getattr(finished_frame.blue_team, "team_id", None) or (self.live_blue_metadata.team_id if self.live_blue_metadata else None)
                        red_team_id = getattr(finished_frame.red_team, "team_id", None) or (self.live_red_metadata.team_id if self.live_red_metadata else None)
                        blue_team = next((t for t in match.teamsEventDetails if t.id == blue_team_id), None) or match.teamsEventDetails[0]
                        red_team = next((t for t in match.teamsEventDetails if t.id == red_team_id), None) or match.teamsEventDetails[1]
                        total_wins = blue_team.game_wins + red_team.game_wins

                        if total_wins < self.number or (blue_team.game_wins == 0 and red_team.game_wins == 0):
                            # 1. Si un equipo tiene 2+ muertos y el otro no, ese pierde
                            if blue_dead >= 2 and red_dead < 2:
                                red_team.game_wins += 1
                                print(f"[DEDUCCIÓN] Se asigna victoria a RED ({red_team.name}) por 2+ muertos en BLUE")
                                self.deduced_winner = "red"
                            elif red_dead >= 2 and blue_dead < 2:
                                blue_team.game_wins += 1
                                print(f"[DEDUCCIÓN] Se asigna victoria a BLUE ({blue_team.name}) por 2+ muertos en RED")
                                self.deduced_winner = "blue"
                            else:
                                # 2. Si ambos tienen menos de 2 muertos, gana el que tenga más de 5k de oro de diferencia
                                gold_diff = blue_gold - red_gold
                                if abs(gold_diff) >= 5000:
                                    if blue_gold > red_gold:
                                        blue_team.game_wins += 1
                                        print(f"[DEDUCCIÓN] Se asigna victoria a BLUE ({blue_team.name}) por ventaja de oro >= 5k")
                                        self.deduced_winner = "blue"
                                    else:
                                        red_team.game_wins += 1
                                        print(f"[DEDUCCIÓN] Se asigna victoria a RED ({red_team.name}) por ventaja de oro >= 5k")
                                        self.deduced_winner = "red"
                                else:
                                    # 3. Si oro < 5k, gana el de más inhibidores
                                    if blue_inhib > red_inhib:
                                        blue_team.game_wins += 1
                                        print(f"[DEDUCCIÓN] Se asigna victoria a BLUE ({blue_team.name}) por más inhibidores")
                                        self.deduced_winner = "blue"
                                    elif red_inhib > blue_inhib:
                                        red_team.game_wins += 1
                                        print(f"[DEDUCCIÓN] Se asigna victoria a RED ({red_team.name}) por más inhibidores")
                                        self.deduced_winner = "red"
                                    else:
                                        # 4. Si inhibidores empatados, gana el de más torres
                                        if blue_towers > red_towers:
                                            blue_team.game_wins += 1
                                            print(f"[DEDUCCIÓN] Se asigna victoria a BLUE ({blue_team.name}) por más torres")
                                            self.deduced_winner = "blue"
                                        elif red_towers > blue_towers:
                                            red_team.game_wins += 1
                                            print(f"[DEDUCCIÓN] Se asigna victoria a RED ({red_team.name}) por más torres")
                                            self.deduced_winner = "red"
                                        else:
                                            print("[DEDUCCIÓN] No se puede deducir ganador (empate en todo)")
                                            self.deduced_winner = None
                        else:
                            print("[DEDUCCIÓN] La API ya actualizó el score, no se deduce nada")
        
                    
                
                        
                            # --- AQUÍ VA EL BLOQUE DE CIERRE DE SERIE ---
                    parent = getattr(self, "parent_match", None)
                    if parent and hasattr(parent, "teamsEventDetails") and parent.teamsEventDetails:
                        teams = parent.teamsEventDetails
                        victorias_necesarias = (getattr(parent, "best_of_count", 1) // 2) + 1
                        blue_team = next((t for t in teams if t.id == getattr(self.live_blue_metadata, "team_id", None)), None)
                        red_team = next((t for t in teams if t.id == getattr(self.live_red_metadata, "team_id", None)), None)
                        if not blue_team or not red_team:
                            if len(teams) >= 2:
                                blue_team = teams[0]
                                red_team = teams[1]
                            else:
                                blue_team = teams[0] if teams else None
                                red_team = teams[1] if len(teams) > 1 else None

                        if blue_team and red_team:
                            if getattr(blue_team, "game_wins", 0) >= victorias_necesarias or getattr(red_team, "game_wins", 0) >= victorias_necesarias:
                                print(f"[🏁] Serie completada por deducción: {getattr(parent, 'match_id', '?')}")
                                parent.state = "completed"
                                parent.status = TrackedStatus.COMPLETED
                                for g in getattr(parent, "trackedGames", []):
                                    if getattr(g, "state", None) not in ("completed", "unneeded"):
                                        g.state = "completed"
                            
                    
                    
                    
                
                
                
                
                
                
                
                
            
             # Detectar pausa
        paused_found = any(
            hasattr(frame, "gameState") and frame.gameState == "paused"
            for frame in liveStats_obj.frames
        )
        if paused_found:
            if not self.paused:
                self.paused = True
                self.pause_start_time = await get_network_time()
                print(f"[PAUSA] Juego {self.game_id} detectado como PAUSADO")
        else:
            if self.paused:
                # Se reanuda el juego, suma la duración de la pausa
                pause_end = await get_network_time()
                if pause_end is not None and self.pause_start_time is not None:
                    self.total_paused_duration += (pause_end - self.pause_start_time).total_seconds()
                self.paused = False
                self.pause_start_time = None
                print(f"[REANUDADO] Juego {self.game_id} reanudado, pausa acumulada: {self.total_paused_duration} segundos")
                # Asigna real_start_time si aún no está asignado
                if not self.real_start_time:
                    self.real_start_time = pause_end












    def to_dict(self):
        return {
            "game_id": self.game_id,
            "number": self.number,
            "state": self.state,
            "draft_in_progress": self.draft_in_progress,
            "has_participants": self.has_participants,
            "notified_time": self.notified_time.isoformat() if self.notified_time else None,
            "notified_game": self.notified_game,
            "finished_time": self.finished_time.isoformat() if self.finished_time else None,
            "real_start_time": self.real_start_time.isoformat() if self.real_start_time else None,
            "vods": [vod.to_dict() for vod in self.vods],	
            "live_patch": self.live_patch,
            "live_blue_metadata": self.live_blue_metadata.to_dict() if self.live_blue_metadata else None,
            "live_red_metadata": self.live_red_metadata.to_dict() if self.live_red_metadata else None,
            #"live_frames": [f._raw_data for f in self.live_frames] if self.live_frames else [],
            "last_frame_time": self.last_frame_time,
            
        
        
        
        
        }

    @classmethod
    def from_dict(cls, data):
        # Crea una instancia vacía sin llamar al __init__ original
        obj = cls.__new__(cls)
        obj.game_id = data["game_id"]
        obj.number = data.get("number", 1)
        obj.state = data.get("state", "notStarted")
        obj.vods = [VodGameEventDetails(v) if not isinstance(v, VodGameEventDetails) else v for v in data.get("vods", [])]
        obj.draft_in_progress = data.get("draft_in_progress", False)
        obj.has_participants = data.get("has_participants", False)
        obj.notified_time = datetime.fromisoformat(data["notified_time"]) if data.get("notified_time") else None
        obj.notified_game = data.get("notified_game", False)
        obj.finished_time = datetime.fromisoformat(data["finished_time"]) if data.get("finished_time") else None
        obj.real_start_time = datetime.fromisoformat(data["real_start_time"]) if data.get("real_start_time") else None
        obj.live_patch = data.get("live_patch")
        obj.live_blue_metadata = LiveTeamMetadata(data["live_blue_metadata"]) if data.get("live_blue_metadata") else None
        obj.live_red_metadata = LiveTeamMetadata(data["live_red_metadata"]) if data.get("live_red_metadata") else None
       # obj.live_frames = [LiveFrame(f) for f in data.get("live_frames", [])]
        obj.last_frame_time = data["last_frame_time"]
        obj.paused = False
        obj.pause_start_time = None
        obj.total_paused_duration = 0.0
        obj.gold_history = []
        obj.stagnant_gold_frames = 0
        
        return obj

class TrackedMatch:
    def __init__(self, detection_time: datetime, scheduleEvent_obj: ScheduleEvent):
        self.detection_time = detection_time
        self.last_checked = detection_time
        self.status = TrackedStatus.DETECTED
        

        # Datos de ScheduleEvent
        self.start_time = scheduleEvent_obj.start_time
        self.match_id = scheduleEvent_obj.match_id
        self.state = scheduleEvent_obj.state
        self.blockName = scheduleEvent_obj.blockName

        # Desde EventDetails
        self.event_id = None
        self.league_name = None
        self.slug = None
        self.best_of_count = None
        self.teamsEventDetails: Optional[List[TeamEventDetails]] = None
        

        # Lista de juegos (TrackedGame)
        self.trackedGames: List[TrackedGame] = []

    async def enrich_from_event_details(self, eventDetails_obj: EventDetails):
        if not eventDetails_obj.id:
            raise ValueError("EventDetails incompleto")
        self.event_id = eventDetails_obj.id
        self.league_name = eventDetails_obj.league_name
        self.slug = eventDetails_obj.slug
        self.best_of_count = eventDetails_obj.best_of_count
        if self.teamsEventDetails:
            # Crea un dict por ID para máxima robustez
            old_teams_by_id = {t.id: t for t in self.teamsEventDetails}
            for new_team in eventDetails_obj.teamsEventDetails:
                old_team = old_teams_by_id.get(new_team.id)
                if old_team:
                    if old_team.game_wins > new_team.game_wins:
                        print(f"[PROTECCIÓN] Manteniendo score deducido para {old_team.name}: {old_team.game_wins} (API traía {new_team.game_wins})")
                        new_team.game_wins = old_team.game_wins
        self.teamsEventDetails = eventDetails_obj.teamsEventDetails
                    
        if eventDetails_obj.gamesEventDetails:
            for game_event in eventDetails_obj.gamesEventDetails:
               
                tracked_game = next((g for g in self.trackedGames if g.game_id == game_event.id), None)
                if not tracked_game:
                    tracked_game = TrackedGame(game_event)
                    tracked_game.parent_match = self # type: ignore
                    self.trackedGames.append(tracked_game)
                else:
                    tracked_game.parent_match = self  # type: ignore
                    if game_event.state == "completed" or tracked_game.state != "completed":
                        # Actualiza los datos base por si cambiaron en la API
                        tracked_game.state = game_event.state
                        if game_event.state == "completed" and not tracked_game.finished_time:
                            tracked_game.finished_time = await get_network_time()
                        
                        tracked_game.number = game_event.number
                        tracked_game.vods = game_event.vods
            # <-- Añade esto al final del método -->
        if self.trackedGames and all(g.state in ("completed", "unneeded") for g in self.trackedGames):
            self.state = "completed"                

        # --- BLOQUE NUEVO: Forzar siguiente juego a inProgress si el anterior terminó ---
        for idx, game in enumerate(self.trackedGames):
            if game.state == "completed":
                # Si hay un siguiente juego y está "unstarted", forzarlo a "inProgress"
                if idx + 1 < len(self.trackedGames):
                    next_game = self.trackedGames[idx + 1]
                    # Verifica si la serie ya terminó (alguien alcanzó el best_of_count)
                    blue_wins = self.teamsEventDetails[0].game_wins
                    red_wins = self.teamsEventDetails[1].game_wins
                    if (
                        next_game.state == "unstarted"
                        and blue_wins + red_wins == idx + 1  # Solo si ya hay suficientes victorias para justificar el siguiente juego
                        and blue_wins < self.best_of_count // 2 + 1
                        and red_wins < self.best_of_count // 2 + 1
                        and next_game.has_participants  # <
                    ):
                        print(f"[FORZADO] Juego {next_game.game_id} forzado a inProgress porque el anterior terminó.")
                        next_game.state = "inProgress"
        
         # --- BLOQUE EXTRA: Forzar siguiente juego a inProgress si tiene metadata de jugadores ---
        for idx, game in enumerate(self.trackedGames):
            if idx + 1 < len(self.trackedGames):
                next_game = self.trackedGames[idx + 1]
                if (
                    next_game.state == "unstarted"
                    and next_game.has_participants
                    and not ((blue_wins or 0) + (red_wins or 0) >= self.best_of_count // 2 + 1)
                ):
                    print(f"[FORZADO][METADATA] Juego {next_game.game_id} forzado a inProgress por presencia de jugadores en LiveStats.")
                    next_game.state = "inProgress"                
        
            # --- BLOQUE DE SCORE MÍNIMO SEGÚN NÚMERO DE MAPAS ---
        if self.teamsEventDetails and len(self.teamsEventDetails) == 2:
            blue_team = self.teamsEventDetails[0]
            red_team = self.teamsEventDetails[1]
            completed_games = [g for g in self.trackedGames if g.state == "completed"]
            num_completed = len(completed_games)
            # Solo aplica si hay más juegos completados que la suma de victorias
            if num_completed > (blue_team.game_wins + red_team.game_wins):
                min_score = num_completed // 2
                if blue_team.game_wins < min_score or red_team.game_wins < min_score:
                    print(f"[AUTO-SCORE] Forzando score mínimo {min_score}-{min_score} por {num_completed} mapas completados (antes: {blue_team.game_wins}-{red_team.game_wins})")
                    blue_team.game_wins = min_score
                    red_team.game_wins = min_score
        
        
        
    
    
    async def update_last_checked(self):
        self.last_checked = await get_network_time()

    @classmethod
    async def from_schedule_event(cls, match_event):
        if not isinstance(match_event, ScheduleEvent):
            raise TypeError("Se requiere un ScheduleEvent")
        return cls(
            detection_time=await get_network_time() or datetime.now(timezone.utc),
            scheduleEvent_obj=match_event
        )

    def to_dict(self) -> dict:
        return {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "match_id": self.match_id,
            "detection_time": self.detection_time.isoformat() if self.detection_time else None,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            
            "state": self.state,
            "status": self.status.value,
            "blockName": self.blockName,
            "event_id": self.event_id,
            "league_name": self.league_name,
            "slug": self.slug,
            "best_of_count": self.best_of_count,
            "teams_event_details": [team.to_dict() for team in self.teamsEventDetails] if self.teamsEventDetails else [],
            
            "trackedGames": [g.to_dict() for g in self.trackedGames],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrackedMatch":
        schedule_event_obj = ScheduleEvent.from_minimal_data(
            start_time=data["start_time"],
            match_id=data["match_id"],
            state=data["state"],
            blockName=data["blockName"]
        )
        obj = cls(
            detection_time=datetime.fromisoformat(data["detection_time"]),
            scheduleEvent_obj=schedule_event_obj
        )
        obj.last_checked = datetime.fromisoformat(data["last_checked"]) if data.get("last_checked") else None
        
        obj.status = TrackedStatus(data["status"])
        obj.event_id = data.get("event_id")
        obj.league_name = data.get("league_name")
        obj.slug = data.get("slug")
        obj.best_of_count = data.get("best_of_count")
        obj.teamsEventDetails = [TeamEventDetails(t) for t in data.get("teams_event_details", [])]
       
        obj.trackedGames = [TrackedGame.from_dict(g) for g in data.get("trackedGames", [])]
        return obj

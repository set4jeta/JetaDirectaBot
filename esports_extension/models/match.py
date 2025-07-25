
from datetime import datetime
from typing import Any, List, Dict, Optional

from esports_extension.utils.time_utils import get_network_time

import pytz




class TeamSchedule:      #  {"data": { "schedule": {  events: [ match: { teams: [ {} ] } } } } NOTA : "state": no es del todo fiable, por lo tanto para scanear sirve más no para confirmar el estado de un evento
    def __init__(self, teamSchedule_data: dict):                                                      # por lo tanto game_wins refleja datos incorrectos
        
        self._raw_data: Dict[str, Any] = teamSchedule_data 
        
        # Para acceso a campos no mapeados
        self.id: str = teamSchedule_data.get('id', '')  # team.id
        self.name: str = teamSchedule_data.get('name', '')
        self.code: str = teamSchedule_data.get('code', '')
        self.image: str = teamSchedule_data.get('image', '')
       
       
        result = teamSchedule_data.get('result') or {}
        self.outcome = result.get('outcome')
        self.game_wins = result.get('gameWins', 0)

        record = teamSchedule_data.get('record') or {}
        self.record_wins = record.get('wins', 0)
        self.record_losses = record.get('losses', 0)



class ScheduleEvent:        #  {"data": { "schedule": {  events: [    
    def __init__(self, scheduleEvent_data: Dict[str, Any]):
        self._raw_data: Dict[str, Any] = scheduleEvent_data  # Para acceso a campos no mapeados
        
        self.start_time: Optional[datetime] = self._parse_time(scheduleEvent_data.get('startTime'))
        self.state: str = scheduleEvent_data.get('state', '')
        self.type: str = scheduleEvent_data.get('type', '')
        self.blockName: str = scheduleEvent_data.get('blockName', '') 
        self.league_name: str = scheduleEvent_data.get('league', {}).get('name', '')
        self.slug: str = scheduleEvent_data.get('league', {}).get('slug', '')
        self.match_id = scheduleEvent_data.get('match', {}).get('id', '')
        self.best_of: str = scheduleEvent_data.get('match', {}).get('strategy', {}).get('type', '') 
        self.best_of_count: int = scheduleEvent_data.get('match', {}).get('strategy', {}).get('count', 0) 
        
        self.teams: List[TeamSchedule] = [
    TeamSchedule(team) 
            for team in scheduleEvent_data.get('match', {}).get('teams', [])
            if team.get('name') != 'TBD' #descartar equipos con nombre TBD
               
                ]   
             

    
    def _parse_time(self, time_str: Optional[str]) -> Optional[datetime]:
        if not time_str:
            return None
        try:
            parsed = datetime.fromisoformat(time_str.replace('Z', '+00:00')).astimezone(pytz.UTC)
            return parsed
        except ValueError as e:
            raise ValueError(f"Invalid time format: {time_str}") from e





    async def hora_de_inicio(self) -> float:
        if not self.start_time:
            return None # type: ignore
        ahora = await get_network_time()
        diferencia = self.start_time - ahora # type: ignore
        return diferencia.total_seconds() / 3600  # Convertir a horas




    @classmethod
    def from_minimal_data(cls, start_time: str, match_id: str, state: str, blockName: str) -> "ScheduleEvent":
        """Crea un ScheduleEvent con datos mínimos."""
        return cls({
            "startTime": start_time,
            "state": state,
            "blockName": blockName,
            "match": {
                "id": match_id,
                
            }
        })





class Schedule:        #  {"data": { "schedule": {                                 
    def __init__(self, schedule_data: Dict[str, Any]):
        
        self._raw_data: Dict[str, Any] = schedule_data
        self.events: List[ScheduleEvent] = [ScheduleEvent(event) for event in schedule_data.get('events', [])]  # event.match.teams   # Lista de eventos (cada uno es un objeto ScheduleEvent)
         # Lista de todas las match_id de los eventos
        self.match_ids: List[str] = [
            event.match_id 
            for event in self.events 
            if event.match_id  # Filtra IDs vacías (opcional)
        ]


class TeamEventDetails:            #  {"data": { "event": { "match": { teams: [ {} ] } } } }
    def __init__(self, teamEventDetails_data: Dict[str, Any]):
        
        self._raw_data: Dict[str, Any] = teamEventDetails_data
        
        self.id: str = teamEventDetails_data.get('id', '')
        self.name: str = teamEventDetails_data.get('name', '')
        self.code: str = teamEventDetails_data.get('code', '')
        self.image: str = teamEventDetails_data.get('image', '')
        self.game_wins: int = teamEventDetails_data.get('result', {}).get('gameWins', 0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "image": self.image,
            "game_wins": self.game_wins,
            
    }
        
        
class VodGameEventDetails:        #  {"data": { "event": { "match": { games: [ { vod [ {} ] } ] } } } }         # NOTA : hay vods una vez el partido ha sido "status" : "completed" 
    def __init__(self, vodGameEventDetails_data: Dict[str, Any]):
        self.id: str = vodGameEventDetails_data.get('id', '')
        self.parameter: str = vodGameEventDetails_data.get('parameter', '') # si self.provider es youtube y self.parameter es 5EEQ7nhltYQ entonces, https://www.youtube.com/watch?v=5EEQ7nhltYQ
        self.locale: str = vodGameEventDetails_data.get('locale', '')
        self.provider: str = vodGameEventDetails_data.get('provider', '') # youtube, twitch etc 
        
        self.offset: int = vodGameEventDetails_data.get('offset', 0)
        self.first_frame_time: Optional[datetime] = self._parse_time(vodGameEventDetails_data.get("firstFrameTime")) #primer frame del vod del partido completado   
        
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "parameter": self.parameter,
            "locale": self.locale,
            "provider": self.provider,
            "offset": self.offset,
            "first_frame_time": self.first_frame_time.isoformat() if self.first_frame_time else None,
    }    
    
    
    def _parse_time(self, time_str: Optional[str]) -> Optional[datetime]:
        if not time_str:
            return None
        try:
            parsed = datetime.fromisoformat(time_str.replace('Z', '+00:00')).astimezone(pytz.UTC)
            return parsed
        except ValueError as e:
            raise ValueError(f"Invalid time format: {time_str}") from e

        
        
        
class GameEventDetails:        #  {"data": { "event": { "match": { games: [ {} ] } } } }
    def __init__(self, gameEventDetails_data: Dict[str, Any]):
        
        self._raw_data: Dict[str, Any] = gameEventDetails_data  # Para acceso a campos no mapeados
        
        self.id: str = gameEventDetails_data.get('id', '')                  # game.id
        self.number: int = gameEventDetails_data.get('number', 0)
        self.state: str = gameEventDetails_data.get('state', 'unstarted')
        self.teams: List[Dict[str, Any]] = gameEventDetails_data.get('teams', [])
        
        self.team_blue = self._get_team_data(0)  # Equipo en posición 0 (blue)
        self.team_red = self._get_team_data(1)   # Equipo en posición 1 (red)
        
        self.vods: List[VodGameEventDetails] = [
            VodGameEventDetails(vod) if not isinstance(vod, VodGameEventDetails) else vod
            for vod in gameEventDetails_data.get('vods', [])
        ]
        
    
        
        
    def _get_team_data(self, index: int) -> Dict[str, str]:
            """Extrae los datos del equipo en el índice dado (0 o 1)."""
            
            if len(self.teams) > index:
                return {
                    "id": self.teams[index].get('id', ''),
                    "side": self.teams[index].get('side', '')
                }
            return {"id": "", "side": ""}  # Datos vacíos si no existe
        
        
        
        
    def to_dict(self) -> dict:
            return {
            "id": self.id,
            "number": self.number,
            "state": self.state,
            "vods": [vod.to_dict() for vod in self.vods]
    }
            
    

class Stream:                   #  {"data": { "event": { "streams": [ {} ] } } }
    def __init__(self, stream_data: Dict[str, Any]):
        self.provider: str = stream_data.get('provider', '')
        self.parameter: str = stream_data.get('parameter', '')
        self.locale: str = stream_data.get('locale', '')



class EventDetails:      #  {"data": { "event": {
    def __init__(self, eventDetails_data: Dict[str, Any]) -> None:
        """
        Parsea los datos del evento de la API.
        
        Estructura esperada de event_data (ejemplo simplificado):
        {
            "id": "...",
            "league": { "name": "...", ... },
            "match": { "teams": [...], "games": [...], ... },
            "startTime": "2023-10-25T12:00:00Z",
            "streams": [...]
        }
        """
        self._raw_data: Dict[str, Any] = eventDetails_data  # Para acceso a campos no mapeados
        
        # Extracción de campos principales (ajustados a tu API real)
        self.id: str = eventDetails_data.get('id', '')  # event.id,  event id (getEventDetails) = match id (getSchedule)   https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id=(ScheduleEvent.match.id)
        self.league_name: str = eventDetails_data.get('league', {}).get('name', '')  # event.league.name
        self.slug: str = eventDetails_data.get('league', {}).get('slug', '')  # event.league.slug
        self.best_of_count: int = eventDetails_data.get('match', {}).get('strategy', {}).get('count', 0) 
        self.teamsEventDetails: List[TeamEventDetails] = [TeamEventDetails(team) for team in eventDetails_data.get('match', {}).get('teams', [])]  # event.match.teams
        self.gamesEventDetails: List[GameEventDetails] = [GameEventDetails(game) for game in eventDetails_data.get('match', {}).get('games', [])]  # event.match.games
        self.streamsEventDetails: List[Stream] = [Stream(stream) for stream in eventDetails_data.get('streams', [])]  # event.streams
 
    




#class UnifiedMatch:
   # """Combina datos de EventDetails y Schedule."""
    #def __init__(self, event_details: EventDetails, schedule: Schedule):
        #self.id = event_details.id
        #self.league_name = event_details.league_name
        #self.league_slug = schedule.league_slug
        #self.start_time = schedule.start_time        


        
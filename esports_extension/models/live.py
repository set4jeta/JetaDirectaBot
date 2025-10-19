from datetime import datetime, timezone
from typing import Any, List, Dict, Optional
from enum import Enum
import copy
import json

import pytz




class LiveParticipantMetadata:     # {gameMetadata: { "blueTeamMetadata" (o "redTeamMetadata"): { "participantMetadata": [ { 
    def __init__(self, liveParticipantMetadata_data: dict):                                                      
        self._raw_data: Dict[str, Any] = liveParticipantMetadata_data  # Para acceso a campos no mapeados
        
        self.participant_id: int = liveParticipantMetadata_data.get("participantId", 0)
        self.player_id: str = liveParticipantMetadata_data.get("esportsPlayerId", "")
        self.summoner_name: str = liveParticipantMetadata_data.get("summonerName", "")
        self.champion_id: str = liveParticipantMetadata_data.get("championId", "")
        self.role: str = liveParticipantMetadata_data.get("role", "")
        
        
    def to_dict(self) -> dict:
        return {
        "participant_id": self.participant_id,
        "player_id": self.player_id,
        "summoner_name": self.summoner_name,
        "champion_id": self.champion_id,
        "role": self.role
    }    

class LiveTeamMetadata:         # {"blueTeamMetadata": { ... } } o {"redTeamMetadata": { ... } }

    def __init__(self, liveTeamMetadata_data: dict):                                                      
        self._raw_data: Dict[str, Any] = liveTeamMetadata_data  # Para acceso a campos no mapeados
        
       
        self.team_id: str = liveTeamMetadata_data.get('esportsTeamId', '')  # 
        self.participants: List[LiveParticipantMetadata] = [
            LiveParticipantMetadata(p) for p in liveTeamMetadata_data.get("participantMetadata", [])
        ]
        self.name: str = liveTeamMetadata_data .get('name', '')
        self.code: str = liveTeamMetadata_data .get('code', '')
        self.image: str = liveTeamMetadata_data .get('image', '')
       
    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "code": self.code,
            "image": self.image,
            "participants": [p.to_dict() for p in self.participants]
        }


class LiveStats:                             # { }
    def __init__(self, liveStats_data: dict):
        if "gameMetadata" not in liveStats_data:
            raise ValueError("Missing 'gameMetadata' in LiveStats data")                                                     
    
        self._raw_data: Dict[str, Any] = liveStats_data 
        
        # Para acceso a campos no mapeados
        self.game_id: str = liveStats_data.get('esportsGameId', '')  # liveStats.game_id
        self.match_id: str = liveStats_data.get('esportsMatchId', '')  # liveStats.match_id
        gameMetadata: dict = liveStats_data.get("gameMetadata", {})
        
        self.patch_version: str = gameMetadata.get("patchVersion", "")
        self.blueTeamMetadata: LiveTeamMetadata  = LiveTeamMetadata(gameMetadata.get("blueTeamMetadata", {}))
        self.redTeamMetadata: LiveTeamMetadata = LiveTeamMetadata(gameMetadata.get("redTeamMetadata", {}))
        
        self.frames: List[LiveFrame] = [
            LiveFrame(f) for f in liveStats_data.get("frames", [])
        ]
        



class LiveParticipantFrame:           # { frames:[ { "blueTeam (o "redTeam): { "participats" [  {         }  ]  }}  ]}
    def __init__(self, liveParticipantFrame_data: dict):
        self.participant_id = liveParticipantFrame_data.get("participantId", 0)
        self.total_gold = liveParticipantFrame_data.get("totalGold", 0)
        self.level = liveParticipantFrame_data.get("level", 1)
        self.kills = liveParticipantFrame_data.get("kills", 0)
        self.deaths = liveParticipantFrame_data.get("deaths", 0)
        self.assists = liveParticipantFrame_data.get("assists", 0)
        self.cs = liveParticipantFrame_data.get("creepScore", 0)
        self.hp = liveParticipantFrame_data.get("currentHealth", 0)
        self.max_hp = liveParticipantFrame_data.get("maxHealth", 0)









class LiveTeamFrame:             # { frames:[ { "blueTeam (o "redTeam): {}}  ]}
    def __init__(self, liveTeamFrame_data: dict):
        self.total_gold = liveTeamFrame_data.get("totalGold", 0)
        self.inhibitors = liveTeamFrame_data.get("inhibitors", 0)
        self.towers = liveTeamFrame_data.get("towers", 0)
        self.barons = liveTeamFrame_data.get("barons", 0)
        self.total_kills = liveTeamFrame_data.get("totalKills", 0)
        self.dragons = liveTeamFrame_data.get("dragons", [])
        
        self.participants: List[LiveParticipantFrame] = [
            LiveParticipantFrame(p) for p in liveTeamFrame_data.get("participants", [])
        ]




class LiveFrame:                             # { frames:[]}
    def __init__(self, liveFrame_data: dict):                                                     
        
        self._raw_data: Dict[str, Any] = liveFrame_data 
        
        self.timestamp: Optional[datetime] = self._parse_time(liveFrame_data.get("rfc460Timestamp", None))
        self.gameState: str = liveFrame_data.get("gameState", "")

        self.blue_team = LiveTeamFrame(liveFrame_data.get("blueTeam", {}))
        self.red_team = LiveTeamFrame(liveFrame_data.get("redTeam", {}))  
        
        
    def _parse_time(self, time_str: Optional[str]) -> Optional[datetime]:
        if not time_str:
            return None
        try:
            # Parsea y asegura UTC
            return datetime.fromisoformat(time_str.replace('Z', '+00:00')).astimezone(pytz.UTC)
        except ValueError:
            return None

class FirestoreGameData:
    def __init__(self, raw_data: dict):
        self._raw_data = raw_data  # Mantenemos acceso a datos brutos
        self.game_id: str = self._extract_game_id(raw_data)
        
        # Metadata (equipos/jugadores)
        self.metadata: Dict = self._parse_metadata(raw_data.get("fields", {}).get("metadata", {}))
        
        # Gold Diff
        self.gold_diff: List[List[int]] = self._parse_gold_diff(raw_data.get("fields", {}).get("goldDiff", {}))
        
        # Eventos
        self.events: List[Dict] = self._parse_events(raw_data.get("fields", {}).get("events", {}))
        
        # Frame actual
        self.frame: Optional[Dict] = self._parse_frame(raw_data.get("fields", {}).get("frame", {}))
        
        # Tiempos
        self.create_time: Optional[datetime] = self._parse_time(raw_data.get("createTime"))
        self.update_time: Optional[datetime] = self._parse_time(raw_data.get("updateTime"))

    def _extract_game_id(self, data: dict) -> str:
        """Extrae el game_id del campo 'name' (ej: 'projects/.../games/123456')"""
        name = data.get("name", "")
        return name.split("/")[-1] if name else ""

    def _parse_metadata(self, metadata_field: dict) -> Dict:
        if "stringValue" in metadata_field:
            return json.loads(metadata_field["stringValue"])
        return {}

    def _parse_gold_diff(self, gold_diff_field: dict) -> List[List[int]]:
        if "arrayValue" in gold_diff_field:
            return [
                json.loads(item["stringValue"])
                for item in gold_diff_field["arrayValue"].get("values", [])
            ]
        return []

    def _parse_events(self, events_field: dict) -> List[Dict]:
        if "arrayValue" in events_field:
            return [
                json.loads(item["stringValue"])
                for item in events_field["arrayValue"].get("values", [])
            ]
        return []

    def _parse_frame(self, frame_field: dict) -> Optional[Dict]:
        if "stringValue" in frame_field:
            return json.loads(frame_field["stringValue"])
        return None

    def _parse_time(self, time_str: Optional[str]) -> Optional[datetime]:
        if not time_str:
            return None
        try:
            return datetime.fromisoformat(time_str.replace('Z', '+00:00')).astimezone(pytz.UTC)
        except ValueError:
            return None

    def to_dict(self) -> Dict:
        """Serialización para guardar en JSON"""
        return {
            "game_id": self.game_id,
            "metadata": self.metadata,
            "gold_diff": self.gold_diff,
            "events": self.events,
            "frame": self.frame,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "update_time": self.update_time.isoformat() if self.update_time else None,
            #"_raw_data": self._raw_data  # Opcional: guardar datos brutos
        }

    @classmethod
    def from_dict(cls, data: dict):
        """Deserialización desde JSON"""
        instance = cls(data.get("_raw_data", {}))
        # Reconstruimos los campos que no están en _raw_data
        instance.game_id = data.get("game_id", "")
        instance.metadata = data.get("metadata", {})
        instance.gold_diff = data.get("gold_diff", [])
        instance.events = data.get("events", [])
        instance.frame = data.get("frame")
        instance.create_time = datetime.fromisoformat(data["create_time"]) if data.get("create_time") else None
        instance.update_time = datetime.fromisoformat(data["update_time"]) if data.get("update_time") else None
        return instance
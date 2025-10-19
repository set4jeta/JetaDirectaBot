# models/soloq_match.py
from cache.champion_cache import CHAMPION_ID_TO_NAME

class SoloQParticipant:
    def __init__(
        self,
        puuid,
        champion_id,
        champion_name,
        riot_id,
        team_id,
        kills=0,
        deaths=0,
        assists=0,
        win=False,
        position="",
        role=None,
        datos_extra=None
    ):
        self.puuid = puuid
        self.champion_id = champion_id
        self.champion_name = champion_name
        self.riot_id = riot_id  # dict con game_name y tag_line
        self.team_id = team_id
        self.kills = kills
        self.deaths = deaths
        self.assists = assists
        self.win = win
        self.position = position
        self.role = role
        self.datos_extra = datos_extra or {}

    def kda(self):
        if self.deaths == 0:
            return f"{self.kills + self.assists}/0"
        return f"{self.kills}/{self.deaths}/{self.assists}"

    def to_dict(self):
        return {
            "puuid": self.puuid,
            "champion_id": self.champion_id,
            "champion_name": self.champion_name,
            "riot_id": self.riot_id,
            "team_id": self.team_id,
            "kills": self.kills,
            "deaths": self.deaths,
            "assists": self.assists,
            "win": self.win,
            "position": self.position,
            "role": self.role,
            "datos_extra": self.datos_extra
        }


class SoloQMatch:
    def __init__(
        self,
        game_id,
        participants,
        game_mode,
        game_queue,
        game_start_time,
        game_length,
        datos_extra=None
    ):
        self.game_id = game_id
        self.participants = participants  # lista de SoloQParticipant
        self.game_mode = game_mode
        self.game_queue = game_queue
        self.game_start_time = game_start_time
        self.game_length = game_length
        self.datos_extra = datos_extra or {}

    @classmethod
    def from_riot_game_data(cls, data: dict):
        participants = []
        for p in data.get("participants", []):
            champ_id = p.get("championId")
            champ_name = p.get("championName")
            # Si no hay nombre, lo buscas por ID
            if not champ_name and champ_id is not None:
                champ_name = CHAMPION_ID_TO_NAME.get(str(champ_id), f"ID {champ_id}")
            participant = SoloQParticipant(
                puuid=p.get("puuid"),
                champion_id=champ_id,
                champion_name=champ_name,
                riot_id=p.get("riotId", {}),
                team_id=p.get("teamId"),
                kills=p.get("kills", 0),
                deaths=p.get("deaths", 0),
                assists=p.get("assists", 0),
                win=p.get("win", False),
                position=p.get("position", ""),
                role=p.get("role", ""),
                datos_extra=p
            )
            participants.append(participant)

        return cls(
            game_id=data.get("gameId"),
            participants=participants,
            game_mode=data.get("gameMode"),
            game_queue=data.get("queueId"),
            game_start_time=data.get("gameStartTime"),
            game_length=data.get("gameLength"),
            datos_extra=data
        )

    def get_participant_by_puuid(self, puuid):
        for p in self.participants:
            if p.puuid == puuid:
                return p
        return None

    def to_dict(self):
        return {
            "game_id": self.game_id,
            "participants": [p.to_dict() for p in self.participants],
            "game_mode": self.game_mode,
            "game_queue": self.game_queue,
            "game_start_time": self.game_start_time,
            "game_length": self.game_length,
            "datos_extra": self.datos_extra
        }

    async def load_ranks(self, session):
        from core.ranked_cache import get_rank_data_or_cache
        from core.rank_data import get_cached_rank, save_rank_data

        for p in self.participants:
            if not p.puuid:
                continue

            cached_rank = get_cached_rank(p)
            if cached_rank:
                p.rank = cached_rank
            else:
                rank_data = await get_rank_data_or_cache(p.puuid, session)
                p.rank = rank_data
                if rank_data["tier"] != "Desconocido":
                    save_rank_data(p)


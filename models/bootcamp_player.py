 # bootcamp_player.py

class Account:
    def __init__(
        self, game_name, tag_line, rank=None, puuid=None,
        leaderboard_position=None, champion_ids=None, kda=None, is_live=None,
        platform=None, profile_icon=None, summoner_level=None, last_match_timestamp=None
    ):
        self.riot_id = {
            "game_name": game_name,
            "tag_line": tag_line
        }
        self.rank = rank or {}
        self.puuid = puuid
        self.leaderboard_position = leaderboard_position
        self.champion_ids = champion_ids or []
        self.kda = kda
        self.is_live = is_live

        # Nuevos campos para cuentas de pro API
        self.platform = platform
        self.profile_icon = profile_icon
        self.summoner_level = summoner_level
        self.last_match_timestamp = last_match_timestamp

    @classmethod
    def from_leaderboard(cls, raw_data):
        rank = dict(raw_data.get("rank") or {})
        rank.pop("puuid", None)
        return cls(
            game_name=raw_data["gameName"],
            tag_line=raw_data["tagLine"],
            rank=rank,
            puuid=None, 
            leaderboard_position=raw_data.get("leaderboardPosition"),
            champion_ids=raw_data.get("championIds", []),
            kda=raw_data.get("kda"),
            is_live=raw_data.get("isLive"),
        )

    def to_dict(self):
        return {
            "riot_id": self.riot_id,
            "rank": self.rank,
            "puuid": self.puuid,
            "leaderboard_position": self.leaderboard_position,
            "champion_ids": self.champion_ids,
            "kda": self.kda,
            "is_live": self.is_live,
            "platform": self.platform,
            "profile_icon": self.profile_icon,
            "summoner_level": self.summoner_level,
            "last_match_timestamp": self.last_match_timestamp
        }

    @classmethod
    def from_dict(cls, data: dict):
        riot_id = data.get("riot_id", {})
        return cls(
            game_name=riot_id.get("game_name", ""),
            tag_line=riot_id.get("tag_line", ""),
            rank=data.get("rank"),
            puuid=data.get("puuid"), 
            leaderboard_position=data.get("leaderboard_position"),
            champion_ids=data.get("champion_ids", []),
            kda=data.get("kda"),
            is_live=data.get("is_live"),
            platform=data.get("platform"),
            profile_icon=data.get("profile_icon"),
            summoner_level=data.get("summoner_level"),
            last_match_timestamp=data.get("last_match_timestamp"),
        )


class BootcampPlayer:
    def __init__(self, name, team="", role=""):
        self.name = name
        self.team = team
        self.role = role
        self.accounts = []

        # Nuevos campos desde /pros/
        self.age = None
        self.birthdate = None
        self.contract = None
        self.country = None
        self.nationalities = []
        self.display_name = None             # displayName para esportPlayer
        self.team_name = None                # team renombrado a team_name para esportPlayer
        self.links = []                      # links de esportPlayer
        self.last_champions = []

    def add_account(self, account: Account):
        for acc in self.accounts:
            if acc.riot_id["game_name"].lower() == account.riot_id["game_name"].lower() and \
               acc.riot_id["tag_line"].lower() == account.riot_id["tag_line"].lower():
                return
        self.accounts.append(account)

    @classmethod
    def from_leaderboard_group(cls, name, accounts_raw):
        team = accounts_raw[0].get("team", "")
        role = accounts_raw[0].get("role", "")
        player = cls(name=name, team=team, role=role)

        for raw in accounts_raw:
            acc = Account.from_leaderboard(raw)
            player.add_account(acc)

        return player

    @classmethod
    def from_pro_api(cls, name, data):
        esport_info = data.get("esportPlayer") or {}
        accounts_data = data.get("players", [])
        team = accounts_data[0].get("team", "") if accounts_data else ""
        role = esport_info.get("role", "")

        player = cls(name=name, team=team, role=role)
        player.age = esport_info.get("age")
        player.birthdate = esport_info.get("birthdate")
        player.contract = esport_info.get("contract")
        player.country = esport_info.get("country")
        player.nationalities = esport_info.get("nationalities", [])
        player.display_name = esport_info.get("displayName") or esport_info.get("overviewPage")
        player.team_name = esport_info.get("team")
        player.links = esport_info.get("links", [])

        accounts_data = data.get("players", [])
        for acc_data in accounts_data:
            rank_data = cls._convert_rank_list(acc_data.get("ranks", []))
            account = Account(
                game_name=acc_data.get("gameName", ""),
                tag_line=acc_data.get("tagLine", ""),
                rank=rank_data,
                puuid=None,
                leaderboard_position=None,
                champion_ids=[],
                kda=None,
                is_live=None,
                platform=acc_data.get("platform"),
                profile_icon=acc_data.get("profileIcon"),
                summoner_level=acc_data.get("summonerLevel"),
                last_match_timestamp=acc_data.get("lastMatchTimestamp")
            )
            player.add_account(account)

        player.last_champions = [{
            "champion_name": c.get("championName"),
            "games": c.get("games"),
            "wins": c.get("wins"),
            "avg_dpm_score": c.get("avgDpmScore"),
            "avg_kda": c.get("avgKda"),
        } for c in data.get("lastChampions", [])]

        return player

    def to_dict(self):
        return {
            "name": self.name,
            "team": self.team,
            "role": self.role,
            "age": self.age,
            "birthdate": self.birthdate,
            "contract": self.contract,
            "country": self.country,
            "nationalities": self.nationalities,
            "displayName": self.display_name,
            "team_name": self.team_name,
            "links": self.links,
            "last_champions": self.last_champions,
            "accounts": [acc.to_dict() for acc in self.accounts]
        }

    @classmethod
    def from_dict(cls, data: dict):
        player = cls(
            name=data["name"],
            team=data.get("team", ""),
            role=data.get("role", "")
        )
        player.age = data.get("age")
        player.birthdate = data.get("birthdate")
        player.contract = data.get("contract")
        player.country = data.get("country")
        player.nationalities = data.get("nationalities", [])
        player.display_name = data.get("displayName")
        player.team_name = data.get("team_name")
        player.links = data.get("links", [])
        player.last_champions = data.get("last_champions", [])

        for acc_data in data.get("accounts", []):
            account = Account.from_dict(acc_data)
            player.add_account(account)

        return player

    @staticmethod
    def _convert_rank_list(ranks):
        if not ranks:
            return {}
        soloq = next((r for r in ranks if r.get("queue") == "RANKED_SOLO_5x5"), ranks[0])
        return {
            "tier": soloq.get("tier"),
            "rank": soloq.get("rank"),
            "lp": soloq.get("leaguePoints"),
            "wins": soloq.get("wins"),
            "losses": soloq.get("losses")
        } 

"""
players = [
    {
        "rank": {
            "rank": "I",
            "tier": "CHALLENGER",
            "leaguePoints": 2095,
            "wins": 360,
            "losses": 268,
            "platform": "NA1",
            "puuid": "MSLRd6I1yGMZig6IOBZKkIi6_QWqAgJtbfsGOa-Efk6dgzfc3pm4jCpcxaaQJhVP51LYULHl7OGorA"
        },
        "puuid": "MSLRd6I1yGMZig6IOBZKkIi6_QWqAgJtbfsGOa-Efk6dgzfc3pm4jCpcxaaQJhVP51LYULHl7OGorA",
        "gameName": "I will trade",
        "tagLine": "NA1",
        "displayName": "Bwipo",
        "profileIcon": 1633,
        "team": "FLY",
        "role": "PRO",
        "platform": "NA1",
        "lane": {
            "value": "TOP",
            "percentage": 86
        },
        "championIds": [875, 799, 126, 79],
        "kda": 2.17528338401991,
        "isLive": false,
        "leaderboardPosition": 1
    }
]
"""
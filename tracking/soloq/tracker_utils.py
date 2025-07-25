# tracking/soloq/tracker_utils.py
import time
from apis.riot_api import get_ranked_data
from tracking.soloq.active_game_cache import set_active_game_with_ranked

VALID_QUEUES = {400, 420, 430, 440}

def is_valid_game(game: dict, player_name: str = "", puuid: str = "") -> bool:
    valid = (
        game.get("gameType") == "MATCHED"
        and game.get("gameMode") == "CLASSIC"
        and game.get("gameQueueConfigId") in [400, 420, 430, 440]
    )

    if not valid:
        print(
            f"[SKIP] {player_name} ({puuid}): "
            f"gameType={game.get('gameType')}, "
            f"gameMode={game.get('gameMode')}, "
            f"queueId={game.get('gameQueueConfigId')}"
        )

    return valid


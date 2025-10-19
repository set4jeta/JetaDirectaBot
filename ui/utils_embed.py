# ui/utils_embed.py

from utils.constants import TEAM_TRICODES
from models.bootcamp_player import BootcampPlayer

def get_player_display(player: BootcampPlayer, game_name: str, tag_line: str, incluir_team_name: bool = True) -> str:
    team = player.team or ""
    tricode = team.upper()
    team_name = TEAM_TRICODES.get(tricode, team)
    if incluir_team_name:
        return f'**{player.name} [{tricode}]** ({game_name}#{tag_line}) ({team_name})'
    else:
        return f'**{player.name} [{tricode}]** ({game_name}#{tag_line})'

def get_player_name(player: BootcampPlayer) -> str:
    return f'**{player.name}**'

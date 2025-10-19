#ui/active_match_embed.py
import os
import nextcord
from typing import Optional
from utils.constants import QUEUE_ID_TO_NAME, TEAM_TRICODES, ROLE_ORDER
from utils.helpers import parse_ranked_data
from cache.champion_cache import CHAMPION_ID_TO_NAME
from utils.spectate_bat import generar_bat_spectate
from models.soloq_match import SoloQMatch, SoloQParticipant
from apis.dpm_api import get_rank_from_dpmlol
from ui.player_image_utils import get_player_image_path
from ui.team_image_utils import get_team_image_path
from utils.role_assigner import assign_roles
from tracking.soloq.accounts_io import load_accounts_cached, load_tracked_accounts


def extract_game_and_tag(riot_id):
    if isinstance(riot_id, dict):
        game_name = riot_id.get("game_name") or ""
        tag_line = riot_id.get("tag_line") or ""
    else:
        riot_str = str(riot_id)
        if "#" in riot_str:
            game_name, tag_line = riot_str.split("#", 1)
        else:
            game_name = riot_str
            tag_line = ""
    return game_name, tag_line

async def create_match_embed(
    match: SoloQMatch,
    puuid_to_player: dict,
    ranked_data_map: Optional[dict] = None
) -> tuple[nextcord.Embed, list[nextcord.File]]:
    participants = match.participants
    participants = assign_roles(participants, puuid_to_player)
    

    # Cargar jugadores de accounts_from_teams.json (trackeados)
    tracked_players = load_tracked_accounts()
    tracked_puuid_to_player = {
        acc.puuid: player
        for player in tracked_players
        for acc in player.accounts
        if acc.puuid
    }

    # Cargar jugadores de accounts.json (no trackeados)
    all_players = load_accounts_cached()
    all_puuid_to_player = {
        acc.puuid: player
        for player in all_players
        for acc in player.accounts
        if acc.puuid
    }





    files: list[nextcord.File] = []

    # Jugadores del bot en la partida (los que están en puuid_to_player)
    bot_players_in_game = [p for p in participants if p.puuid in puuid_to_player]
    displays = []
    for p in bot_players_in_game:
        game_name, tag_line = extract_game_and_tag(p.riot_id)
        player_name = puuid_to_player[p.puuid].name
        displays.append(f"{player_name} ({game_name}#{tag_line})")

        # Título dinámico
    if not bot_players_in_game:
        title = "No hay jugadores del bot en esta partida."
        team_line = ""
    else:
        jugadores_display = []
        for p in bot_players_in_game:
            game_name, tag_line = extract_game_and_tag(p.riot_id)
            player_name = puuid_to_player[p.puuid].name
            jugadores_display.append(f"{player_name} ({game_name}#{tag_line})")

        if len(jugadores_display) == 1:
            title = f"{jugadores_display[0]} está jugando! :loudspeaker:"
        elif len(jugadores_display) == 2:
            title = f"{jugadores_display[0]} y {jugadores_display[1]} están jugando! :loudspeaker:"
        else:
            title = f"{', '.join(jugadores_display[:-1])} y {jugadores_display[-1]} están jugando! :loudspeaker:"

        # Aún usamos el primero para sacar el nombre del equipo
        main_player = bot_players_in_game[0]
        player_obj = puuid_to_player[main_player.puuid]
        team_full_name = player_obj.team_name or ""
        team_line = f"**Equipo:** {team_full_name}\n" if team_full_name else ""


    # Cola y modo
    queue_id = match.game_queue if isinstance(match.game_queue, int) else match.datos_extra.get("gameQueueConfigId")
    queue_name = QUEUE_ID_TO_NAME.get(queue_id, f"Desconocida ({queue_id})") if queue_id else "Desconocida"
    game_mode = match.game_mode or match.datos_extra.get("gameMode", "Desconocido")
    game_start_time = match.game_start_time
    game_length = match.game_length

    # Tiempo transcurrido
    if isinstance(game_length, int):
        mins, secs = divmod(game_length, 60)
        tiempo_str = f"{mins}m {secs}s"
    else:
        tiempo_str = "Desconocido"

    # Hora de inicio
    if isinstance(game_start_time, int):
        timestamp = int(game_start_time / 1000)
        fecha_inicio_str = f"<t:{timestamp}:F>"
    else:
        fecha_inicio_str = "Desconocida"

    desc = f"{team_line}**Cola:** {queue_name}\n**Modo:** {game_mode}\n**Tiempo transcurrido:** {tiempo_str}\n**Hora de inicio:** {fecha_inicio_str}"

    embed = nextcord.Embed(
        title=title,
        description=desc,
        color=nextcord.Color.red()
    )
    
    main_player = bot_players_in_game[0] if bot_players_in_game else None
    
    if main_player:
        player_obj = puuid_to_player[main_player.puuid]
        img_path = get_player_image_path(player_obj.name)
        if img_path:
            filename = f'{player_obj.name.lower().replace(" ", "").replace("\'", "").replace(".", "")}.webp'
            embed.set_thumbnail(url=f"attachment://{filename}")
            files.append(nextcord.File(img_path, filename=filename))


                # --- LOGO DEL EQUIPO COMO MAIN IMAGE ---
        team_tricode = player_obj.team.upper() if player_obj.team else ""
        team_img_path = get_team_image_path(team_tricode)
        if team_img_path:
            embed.set_image(url=f"attachment://{team_tricode}.webp")
            files.append(nextcord.File(team_img_path, filename=f"{team_tricode}.webp"))







    # Tabla horizontal: Champion | Account | Rank (solo jugadores del bot)
    champion_row = []
    account_row = []
    rank_row = []

    for p in bot_players_in_game:
        champ_id = p.champion_id
        champ_name = p.champion_name or CHAMPION_ID_TO_NAME.get(str(champ_id), "?")

        game_name, tag_line = extract_game_and_tag(p.riot_id)

        display = f"{game_name}#{tag_line}"
        if len(display) > 22:
            display = display[:19] + "..."

        if ranked_data_map and p.puuid in ranked_data_map:
            rank = ranked_data_map[p.puuid]
        else:
            rank = None
        print(f"[DEBUG] Rank DPMLOL para {game_name}#{tag_line}: {rank}")
        if rank and rank.get("tier") and rank.get("lp") is not None:
            tier = rank.get("tier", "Unranked").capitalize()
            div = rank.get("division", "")
            lp = rank.get("lp", 0)
            rank_str = f"{tier} {div} ({lp} LP)"
        else:
            print(f"[DEBUG] Rank vacío o sin datos clave para {game_name}#{tag_line}: {rank}")
            rank_str = "Unranked"

        champion_row.append(champ_name)
        account_row.append(display)
        rank_row.append(rank_str)

    if champion_row:
        table1_lines = [
            f"{'Champion':<10} | {'Account':<16}",
            "-" * 29
        ]
        for champ, acc in zip(champion_row, account_row):
            champ_txt = champ[:10]
            acc_txt = acc[:16]
            table1_lines.append(f"{champ_txt:<10} | {acc_txt:<16}")

        table2_lines = ["Rank 🏆", "-" * 16]
        for rank in rank_row:
            table2_lines.append(rank)

        embed.add_field(
            name="Jugadores en la partida",
            value="```\n" + "\n".join(table1_lines) + "\n```",
            inline=False
        )
        embed.add_field(
            name="",
            value="```\n" + "\n".join(table2_lines) + "\n```",
            inline=False
        )


    
    # Separar jugadores por equipo
    blue_team = [p for p in participants if p.team_id == 100]
    red_team = [p for p in participants if p.team_id == 200]

    # Ordenar cada equipo por rol según ROLE_ORDER
    print("[DEBUG] Roles antes de ordenar blue_team:", [p.role for p in blue_team])
    blue_team.sort(key=lambda p: ROLE_ORDER.get(p.role or "", 99))
    print("[DEBUG] Roles después de ordenar blue_team:", [p.role for p in blue_team])

    print("[DEBUG] Roles antes de ordenar red_team:", [p.role for p in red_team])
    red_team.sort(key=lambda p: ROLE_ORDER.get(p.role or "", 99))
    print("[DEBUG] Roles después de ordenar red_team:", [p.role for p in red_team])

    # Crear listas para mostrar en embed con formato
    blue_side = []
    red_side = []

    for p in blue_team:
        champ_id = p.champion_id
        champ_name = p.champion_name or CHAMPION_ID_TO_NAME.get(str(champ_id), f"ID {champ_id}")
        game_name, tag_line = extract_game_and_tag(p.riot_id)

        # 1. Prioriza accounts_from_teams.json
        player = tracked_puuid_to_player.get(p.puuid)
        if player:
            display_name = f"**{player.name} [{player.team.upper()}]**"
            line = f"{display_name} ({champ_name})"
        else:
            # 2. Si no, busca en accounts.json
            player2 = all_puuid_to_player.get(p.puuid)
            if player2:
                team = f"[{player2.team.upper()}]" if player2.team else ""
                display_name = f"{player2.name} {team}"
                line = f"{display_name} ({champ_name})"
            else:
                # 3. Si no está en ninguna, muestra el nick normal
                line = f"{game_name}#{tag_line} ({champ_name})"

        blue_side.append(line)

    for p in red_team:
        champ_id = p.champion_id
        champ_name = p.champion_name or CHAMPION_ID_TO_NAME.get(str(champ_id), f"ID {champ_id}")
        game_name, tag_line = extract_game_and_tag(p.riot_id)

        # 1. Prioriza accounts_from_teams.json
        player = tracked_puuid_to_player.get(p.puuid)
        if player:
            display_name = f"**{player.name} [{player.team.upper()}]**"
            line = f"{display_name} ({champ_name})"
        else:
            # 2. Si no, busca en accounts.json
            player2 = all_puuid_to_player.get(p.puuid)
            if player2:
                team = f"[{player2.team.upper()}]" if player2.team else ""
                display_name = f"{player2.name} {team}"
                line = f"{display_name} ({champ_name})"
            else:
                # 3. Si no está en ninguna, muestra el nick normal
                line = f"{game_name}#{tag_line} ({champ_name})"

        red_side.append(line)

    embed.add_field(name="🔵 Blue Team", value="\n".join(blue_side) or "No players", inline=False)
    embed.add_field(name="🔴 Red Team", value="\n".join(red_side) or "No players", inline=False)


    # Espectate .bat
    
    game_id = match.game_id
    platform_id = match.datos_extra.get("platformId") if hasattr(match, "datos_extra") else None
    encryption_key = match.datos_extra.get("observers", {}).get("encryptionKey") if hasattr(match, "datos_extra") else None
    if game_id and platform_id and encryption_key:
        bat_path = generar_bat_spectate(
            server=f"spectator.{platform_id.lower()}.lol.pvp.net:8080",
            key=encryption_key,
            match_id=game_id,
            region=platform_id
        )
        files.append(nextcord.File(bat_path, filename="spectate_lol.bat"))
        embed.add_field(
            name="🔗 Espectar en directo",
            value="Descarga y ejecuta el archivo **spectate_lol.bat** adjunto arriba para espectar la partida desde tu cliente. (Debes tener el cliente de LoL cerrado)",
            inline=False
        )
        embed.add_field(
            name="!info <nombre jugador>",
            value="Puedes usar este comando para obtener información adicional sobre un jugador de la partida que su Nick sea visible.",
            inline=False
        )
    else:
        embed.add_field(
            name="🔗 Espectar en directo",
            value="No disponible para esta partida.",
            inline=False
        )

    return embed, files

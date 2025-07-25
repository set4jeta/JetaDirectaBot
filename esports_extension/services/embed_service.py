# services/embed_service.py

from nextcord import Embed
from datetime import datetime, timezone
from esports_extension.models.tracker import TrackedMatch
from esports_extension.services.storage import format_elapsed_time
from typing import Optional

class EmbedService:
    
    @staticmethod
    async def create_live_match_embed(match: TrackedMatch, is_notification: bool = False) -> Embed:
        
        tracked_game = None
        for g in reversed(match.trackedGames):
            if (
                g.state == "inProgress"
                and g.live_blue_metadata
                and g.live_red_metadata
                and g.live_blue_metadata.participants
                and g.live_red_metadata.participants
            ):
                tracked_game = g
                break
        if not tracked_game:
            return Embed(title="No hay datos de juego en vivo")
                        
    
        
        
        
            
        blue_metadata = tracked_game.live_blue_metadata
        red_metadata = tracked_game.live_red_metadata
        # Buscar el equipo azul y rojo según el team_id de la metadata
        blue_team = next((t for t in match.teamsEventDetails if t.id == (blue_metadata.team_id if blue_metadata else None)), None) # type: ignore
        red_team = next((t for t in match.teamsEventDetails if t.id == (red_metadata.team_id if red_metadata else None)), None) # type: ignore
         
        # Fallback si no se encuentra el equipo (robusto)
        if not blue_team or not red_team:
            if match.teamsEventDetails and len(match.teamsEventDetails) >= 2:
                blue_team = match.teamsEventDetails[0]
                red_team = match.teamsEventDetails[1]
            else:
                # Si ni siquiera hay teamsEventDetails, muestra un embed de error
                return Embed(title="No hay datos de equipos para este partido")
        blue_default = match.teamsEventDetails[0] # type: ignore # type: ignore
        red_default = match.teamsEventDetails[1]         # type: ignore
            
        blue_players = [
            f"{p.summoner_name} ({p.champion_id})" for p in blue_metadata.participants
        ] if blue_metadata else ["Sin datos"]
        red_players = [
            f"{p.summoner_name} ({p.champion_id})" for p in red_metadata.participants
        ] if red_metadata else ["Sin datos"]
        
        
        blue_wins = blue_team.game_wins
        red_wins = red_team.game_wins
        number_emojis = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        blue_score = number_emojis[blue_wins]
        red_score = number_emojis[red_wins]
        
        max_len = max(len(blue_default.name), len(red_default.name))
        embed = Embed(
    title=f"🏆 {match.league_name} - {match.blockName}",
    color=0x0099ff,
    description=(
        f"**{blue_default.name}** \n"
        f"{ '🆚'.center(max_len) }\n"
        f"**{red_default.name}** "
    )
)

                # Decide si se oculta el score (solo cuando no es 0-0)
        if blue_wins == 0 and red_wins == 0:
            blue_score_str = blue_score
            red_score_str = red_score
        else:
            blue_score_str = f"||{blue_score}||"
            red_score_str = f"||{red_score}||"

        # Construcción de los nombres con marcador
        if blue_wins > red_wins:
            blue_name = f"🏆 🔵 **{blue_team.name}** {blue_score_str}"
            red_name = f"🔴 {red_team.name} {red_score_str}"
        elif red_wins > blue_wins:
            blue_name = f"🔵 {blue_team.name} {blue_score_str}"
            red_name = f"🏆 🔴 **{red_team.name}** {red_score_str}"
        else:
            blue_name = f"🔵 {blue_team.name} {blue_score_str}"
            red_name = f"🔴 {red_team.name} {red_score_str}"

        embed.add_field(name=blue_name, value="\n".join(blue_players), inline=False)
        embed.add_field(name=red_name, value="\n".join(red_players), inline=False)

        # Si es una notificación nueva, agregar mensaje especial
        if is_notification:
            embed.add_field(
                name="🚨 ¡Partido en vivo nuevo detectado!",
                value="¡No te pierdas la acción!",
                inline=False
            )
        else:
             # Si está en pausa, NO mostrar tiempo transcurrido
            if tracked_game.paused:
                embed.color = 0xffcc00  # Amarillo para pausa
                embed.add_field(
                    name="⏸️ Estado",
                    value="El juego está actualmente en pausa.",
                    inline=False
                )
                
            
            else:
                # Si no, mostrar tiempo transcurrido
                if tracked_game.real_start_time:
                    embed.add_field(
                        name="⏱ Tiempo transcurrido",
                        value=await format_elapsed_time(tracked_game.real_start_time, tracked_game),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="⏱ Tiempo transcurrido",
                        value="00:00 (esperando inicio real)",
                        inline=False
        )
        # Footer con BO y score
        blue_wins = blue_team.game_wins
        red_wins = red_team.game_wins
        if match.best_of_count and match.best_of_count > 1:
            if blue_wins == 0 and red_wins == 0:
                score_text = f" ({blue_wins}-{red_wins})"
            else:
                score_text = " (?-?)"
        else:
            score_text = "" # type: ignore # type: ignore
        current_game = tracked_game.number
       
       
        embed.set_thumbnail(url=blue_team.image)
        embed.set_image(url=red_team.image)

        embed.set_footer(
            text=f"BO{match.best_of_count}{score_text} | 🎮 Juego {current_game}"
        )
        
        return embed
    
    
    
        
    @staticmethod
    async def create_upcoming_embed(match: TrackedMatch) -> Embed:
        team1 = match.teamsEventDetails[0]  # type: ignore
        team2 = match.teamsEventDetails[1]  # type: ignore

        block = f" - {match.blockName}" if match.blockName else ""
        best_of = f" - BO {match.best_of_count}"

        if match.start_time:
            start_time_utc = match.start_time.replace(tzinfo=timezone.utc)
            start_timestamp = int(start_time_utc.timestamp())
        else:
            start_timestamp = int(datetime.now(timezone.utc).timestamp())  # fallback
        start_timestamp = int(start_time_utc.timestamp())

        embed = Embed(
            title=f"⏰ {match.league_name} {block} {best_of} - Próximo Partido",
            color=0x00FF00,
            description=(
                f"⌛ **Inicio:** <t:{start_timestamp}:F>\n\n"
                f"🛡️ {team1.name} vs 🎯 {team2.name}"
            )
        )

        embed.set_thumbnail(url=team1.image)
        embed.set_image(url=team2.image)

        return embed

    
    
    
    
    @staticmethod
    async def create_draft_embed(match: TrackedMatch) -> Embed:
        tracked_game = next(
            (g for g in match.trackedGames if g.state in ("inProgress", "unstarted") and not g.has_participants and g.draft_in_progress),
            None
        )

        # Determina equipos y número de juego
        if tracked_game:
            blue_metadata = tracked_game.live_blue_metadata
            red_metadata = tracked_game.live_red_metadata

            blue_team = next((t for t in match.teamsEventDetails if blue_metadata and t.id == blue_metadata.team_id), None) # type: ignore
            red_team = next((t for t in match.teamsEventDetails if red_metadata and t.id == red_metadata.team_id), None) # type: ignore

            if not blue_team or not red_team:
                blue_team = match.teamsEventDetails[0] # type: ignore
                red_team = match.teamsEventDetails[1] # type: ignore

            current_game = tracked_game.number if hasattr(tracked_game, "number") else "?"
            paused = getattr(tracked_game, "paused", False)
        else:
            blue_team = match.teamsEventDetails[0] # type: ignore
            red_team = match.teamsEventDetails[1] # type: ignore
            current_game = "?"
            paused = False

        blue_wins = blue_team.game_wins
        red_wins = red_team.game_wins
        if match.best_of_count and match.best_of_count > 1:
            if blue_wins == 0 and red_wins == 0:
                score_text = f" ({blue_wins}-{red_wins})"
            else:
                score_text = " (?-?)"
        else:
            score_text = "" # type: ignore # type: ignore

        embed = Embed(
            title=f"🧠 Draft en progreso - {match.league_name}",
            color=0xff9900,
            description=(
                f"**{blue_team.name}** vs **{red_team.name}**\n\n"
                f"El draft del 🎮 Juego {current_game} está en curso. ¡Pronto comenzará la partida!"
            )
        )
        embed.set_thumbnail(url=blue_team.image)
        embed.set_image(url=red_team.image)
        embed.set_footer(
            text=f"BO{match.best_of_count}{score_text} | 🎮 Juego {current_game}"
        )

        if paused:
            embed.color = 0xffcc00  # Amarillo para pausa
            embed.add_field(
                name="⏸️ Estado",
                value="El juego está actualmente en pausa.",
                inline=False
            )

        return embed
    
    
    @staticmethod
    async def create_waiting_embed(match: TrackedMatch, next_game_number: Optional[int] = None) -> Embed:
        number_emojis = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

        tracked_game = next(
            (g for g in match.trackedGames if g.state in ("unstarted", "inProgress") and not g.has_participants and not g.draft_in_progress),
            None
        )

        if tracked_game:
            blue_metadata = tracked_game.live_blue_metadata
            red_metadata = tracked_game.live_red_metadata

            blue_team = next((t for t in match.teamsEventDetails if blue_metadata and t.id == blue_metadata.team_id), None) # type: ignore
            red_team = next((t for t in match.teamsEventDetails if red_metadata and t.id == red_metadata.team_id), None) # type: ignore

            if not blue_team or not red_team:
                blue_team = match.teamsEventDetails[0] # type: ignore
                red_team = match.teamsEventDetails[1] # type: ignore

            current_game = tracked_game.number if hasattr(tracked_game, "number") else "?"
        else:
            blue_team = match.teamsEventDetails[0] # type: ignore
            red_team = match.teamsEventDetails[1] # type: ignore
            current_game = next_game_number if next_game_number is not None else "?"

        blue_wins = blue_team.game_wins
        red_wins = red_team.game_wins

        blue_score = number_emojis[blue_wins]
        red_score = number_emojis[red_wins]

        # Ocultar marcador con spoilers igual que en create_live_match_embed
        if blue_wins == 0 and red_wins == 0:
            blue_score_str = blue_score
            red_score_str = red_score
        else:
            blue_score_str = f"||{blue_score}||"
            red_score_str = f"||{red_score}||"

        if blue_wins > red_wins:
            blue_name = f"🏆 **{blue_team.name}** {blue_score_str}"
            red_name = f"**{red_team.name}** {red_score_str}"
        elif red_wins > blue_wins:
            blue_name = f"**{blue_team.name}** {blue_score_str}"
            red_name = f"🏆 **{red_team.name}** {red_score_str}"
        else:
            blue_name = f"**{blue_team.name}** {blue_score_str}"
            red_name = f"**{red_team.name}** {red_score_str}"

        if match.best_of_count and match.best_of_count > 1:
            if blue_wins == 0 and red_wins == 0:
                score_text = f" ({blue_wins}-{red_wins})"
            else:
                score_text = " (?-?)"
        else:
            score_text = ""

        embed = Embed(
            title=f"🟡 Esperando partida... - {match.league_name}",
            color=0xffcc00,
            description=(
                f"{blue_name} vs {red_name}\n\n"
                f"Esperando que comience el 🎮 Juego {current_game}..."
            )
        )

        embed.set_thumbnail(url=blue_team.image)
        embed.set_image(url=red_team.image)
        embed.set_footer(
            text=f"BO{match.best_of_count}{score_text} | 🎮 Juego {current_game}"
        )

        return embed

            
            
    
    
    
    
    
    
    
    
    
    
    
    
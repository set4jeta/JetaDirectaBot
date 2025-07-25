from utils.constants import TEAM_TRICODES
from core.ranked_cache import get_rank_data_or_cache 
from tracking.soloq.accounts_io import load_accounts
from core.rank_data import get_cached_rank
from nextcord.ext import commands
import aiohttp
from tracking.soloq.accounts_io import load_tracked_accounts
from core.rank_data import save_rank_data
import time


players = load_tracked_accounts()


def register_team_commands(bot: commands.Bot):
    @bot.command(name="team")
    async def team_command(ctx, team_tag: str):
        team_tag = team_tag.lower()
        loading_msg = await ctx.send("⏳ Calculando datos, por favor espera...")

        team_players = [p for p in players if p.team and p.team.lower() == team_tag]

        if not team_players:
            await loading_msg.edit(content=f"❌ No hay jugadores registrados para el equipo '{team_tag.upper()}'.")
            return

        
        # Ordenar por rol
        ROLE_ORDER = ["Top", "Jungle", "Mid", "ADC", "Support"]
        team_players.sort(key=lambda p: ROLE_ORDER.index(p.role) if p.role in ROLE_ORDER else len(ROLE_ORDER))
        
        
        lines = []
        rate_limited = False  # Flag para detectar rate limit
        async with aiohttp.ClientSession() as session:
            for p in team_players:
                account = p.accounts[0]
                puuid = account.puuid
                game_name = account.riot_id.get("game_name", "")
                tag_line = account.riot_id.get("tag_line", "")
                cached_rank = get_cached_rank(account)
                force_update = False

                if cached_rank and cached_rank.get("tier") != "Desconocido":
                    # Si el caché es viejo (>2 horas), fuerza update
                    ts = cached_rank.get("timestamp", 0)
                    if time.time() - ts > 7200:
                        force_update = True
                else:
                    force_update = True

                if not force_update and cached_rank:
                    rank_str = f"{cached_rank['tier']} {cached_rank['division']} ({cached_rank['lp']} LP)"
                else:
                    rank_data = await get_rank_data_or_cache(puuid, session)
                    if rank_data is None:
                        # Si no hay datos, intenta usar el caché persistente
                        cached_rank = get_cached_rank(account)
                        if cached_rank:
                            rank_str = f"{cached_rank['tier']} {cached_rank['division']} ({cached_rank['lp']} LP) (cache)"
                        else:
                            rank_str = "Sin datos"
                    elif isinstance(rank_data, dict) and rank_data.get("status") == 429:
                        rate_limited = True
                        cached_rank = get_cached_rank(account)
                        if cached_rank:
                            rank_str = f"{cached_rank['tier']} {cached_rank['division']} ({cached_rank['lp']} LP) (cache)"
                        else:
                            rank_str = "Sin datos (rate limit)"
                    elif rank_data.get("tier") != "Desconocido":
                        rank_str = f"{rank_data['tier']} {rank_data['division']} ({rank_data['lp']} LP)"
                        # Guarda el dato actualizado en el caché persistente
                        account.rank = rank_data
                        save_rank_data(account)
                    else:
                        rank_str = "Sin datos"

                lines.append(f"**{p.name}** ({game_name}#{tag_line}) - {rank_str}")

        team_name_full = TEAM_TRICODES.get(team_tag.upper(), team_tag.upper())
        msg = f"**Jugadores de {team_tag.upper()} ({team_name_full}):**\n\n" + "\n".join(lines)
        if rate_limited:
            msg += "\n\n⚠️ Algunos datos no pudieron obtenerse por rate limit. Intenta más tarde para información completa."

        await loading_msg.edit(content=msg)

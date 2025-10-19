# core/live_command.py
import asyncio
import time
from datetime import datetime, timezone
import aiohttp

from nextcord.ext import commands

from tracking.soloq.active_game_cache import ACTIVE_GAME_CACHE, set_active_game
from tracking.soloq.notifier import load_announced_games
from utils.cache_utils import limpiar_cache_partidas_viejas
from apis.riot_api import get_active_game
from apis.dpm_api import get_is_live_and_updated_from_dpmlol 
from tracking.soloq.accounts_io import load_accounts_cached
from models.bootcamp_player import Account
from tracking.soloq.accounts_io import load_tracked_accounts 

from cache.champion_cache import CHAMPION_ID_TO_NAME

def register_live_command(bot: commands.Bot):
    @bot.command(name="live")
    async def live(ctx: commands.Context):
        """
        Muestra jugadores del bootcamp que están actualmente en partida.
        """
        loading_msg = await ctx.send("⏳ Buscando jugadores en partida...")
        limpiar_cache_partidas_viejas()

        vivos = []
        now = time.time()
        players = load_tracked_accounts() 

        # Mapea PUUID a BootcampPlayer y Account para lookup rápido
        puuid_to_player = {}
        puuid_to_account = {}
        for player in players:
            for account in player.accounts:
                if account.puuid:
                    puuid_to_player[account.puuid] = player
                    puuid_to_account[account.puuid] = account

        # Para evitar duplicados si varios jugadores están en la misma partida
        ya_mostrados = set()

        for puuid, cache_entry in ACTIVE_GAME_CACHE.items():
            if not cache_entry or "active_game" not in cache_entry:
                continue

            player = puuid_to_player.get(puuid)
            account = puuid_to_account.get(puuid)
            if not player or not account:
                continue

            display_name = account.riot_id.get("game_name", "")
            tag_line = account.riot_id.get("tag_line", "")
            team = (player.team or "").upper()
            player_name = player.name

            # Evita mostrar dos veces el mismo jugador si tiene varias cuentas
            key = (player_name, display_name, tag_line)
            if key in ya_mostrados:
                continue
            ya_mostrados.add(key)

            # Calcula el tiempo de partida estimado
            game_length = cache_entry.get("game_length", 0) or 0
            timestamp = cache_entry.get("timestamp", 0)
            elapsed = int(now - timestamp)
            total_game_length = game_length + elapsed                #total_game_length = max(0, game_length + elapsed)
            sign = "-" if total_game_length < 0 else ""
            mins, secs = divmod(abs(total_game_length), 60)
            tiempo_str = f"{sign}{mins:02d}:{secs:02d}"                                                          #mins, secs = divmod(total_game_length, 60)
                                                                        #tiempo_str = f"{mins:02d}:{secs:02d}"

            champ_id = None
            kda_str = "?"
            active_game = cache_entry["active_game"]
            if active_game and isinstance(active_game, dict):
                for part in active_game.get("participants", []):
                    if part.get("puuid") == puuid:
                        champ_id = part.get("championId")
                        kills = part.get("kills", 0)
                        deaths = part.get("deaths", 0)
                        assists = part.get("assists", 0)
                        kda_str = f"{kills}/{deaths}/{assists}"
                        break

            champ_name = CHAMPION_ID_TO_NAME.get(str(champ_id), "?") if champ_id else "?"

            # Formato: FNC Upset - asdfasdf (Lulu) | 15:49 en partida - KDA 9/0/4
            team_str = f"{team} " if team else ""
            role = player.role.upper() if hasattr(player, "role") and player.role else "?"
            vivos.append(
                f"👤 {team_str} {player_name} — {display_name}#{tag_line} | {champ_name} ({role}) | ⏱ {tiempo_str} en partida"
            )

        if not vivos:
            final_msg = (
                "No hay jugadores en partida en este momento.\n"
                "*(Puede haber partidas no detectadas aún. Usa `!<jugador>` si tienes dudas.)*"
            )
        else:
            final_msg = "**Jugadores en partida ahora mismo:**\n\n" + "\n".join(vivos)
            final_msg += "\n\n*(Usa `!match <jugador>` para más información)*"
            
            
            # ⚠️ Mensaje de advertencia sobre el delay
            final_msg += "\n\n⚠️ *A veces puede tener un pequeño delay y que haya terminado una partida)*"

        await loading_msg.edit(content=final_msg)
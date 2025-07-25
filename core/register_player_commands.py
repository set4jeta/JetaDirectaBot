# core/register_player_commands.py

import asyncio
import time
import nextcord
from nextcord.ext import commands
import aiohttp

from tracking.soloq.accounts_io import load_tracked_accounts
from core.retry_handler import add_to_retry_queue
from tracking.soloq.active_game_cache import get_active_game_cache, get_active_game_cache_by_name
from apis.riot_api import get_active_game
from ui.active_match_embed import create_match_embed
from models.soloq_match import SoloQMatch
from core.rank_data import save_rank_data

players = load_tracked_accounts()
name_to_players = {p.name.lower().replace(" ", ""): p for p in players}


def register_match_command(bot: commands.Bot):

    @bot.command(name="match")
    async def match_cmd(ctx, *, player_name: str = ""):
        if not player_name:
            await ctx.send("❌ Debes indicar un nombre de jugador. Ej: `!match stend`")
            return

        normalized_name = player_name.lower().replace(" ", "")
        player = name_to_players.get(normalized_name)

        if not player:
            await ctx.send(f"❌ No se encontró ningún jugador con el nombre '{player_name}'.")
            return

        found = False
        async with aiohttp.ClientSession() as session:
            for account in player.accounts:
                puuid = account.puuid
                if not puuid:
                    continue

                for intento in range(8):
                    active_game, status = await get_active_game(puuid, session)
                    if active_game:
                        found = True
                        try:
                            match = SoloQMatch.from_riot_game_data(active_game)
                            # Aquí cargas los rangos **antes** de crear el embed
                            await match.load_ranks(session)
                        except Exception as e:
                            await ctx.send(f"⚠️ Error procesando partida activa: {e}")
                            return

                        ranked_data_map = {}
                        for part in match.participants:
                            if hasattr(part, "puuid") and part.puuid:
                                from core.rank_data import get_cached_rank
                                rank = getattr(part, "rank", None) or get_cached_rank(part)
                                if rank and rank.get("tier") and rank.get("lp") is not None:
                                    ranked_data_map[part.puuid] = rank

                        puuid_to_player = {a.puuid: player for a in player.accounts if a.puuid}
                        embed, files = await create_match_embed(match, puuid_to_player, ranked_data_map)
                        embed.title = f"Partida de {player.name} ({account.riot_id['game_name']}#{account.riot_id['tag_line']}) 🎮"
                        await ctx.send(embed=embed, files=files)
                        return  # Termina después de enviar embed exitoso

                    if status == 429:  # Rate Limit
                        # 1. Intenta primero con PUUID
                        cache_entry = get_active_game_cache(puuid)

                        # 2. Si falla, intenta con el nombre del jugador
                        if not cache_entry:
                            cache_entry = get_active_game_cache_by_name(player.name)
                            if cache_entry:
                                print(f"[CACHE] Recuperado desde cache por nombre: {player.name}")
                            else:
                                await ctx.send("⚠️ Rate limit detectado, pero no hay datos en caché disponibles.")
                                return

                        try:
                            match = SoloQMatch.from_riot_game_data(cache_entry["active_game"])
                        except Exception as e:
                            await ctx.send(f"⚠️ Error leyendo datos en caché: {e}")
                            return

                        
                        # Para cada participante, si tiene puuid y rank, guarda el rank
                        for part in match.participants:
                            if hasattr(part, "puuid") and hasattr(part, "rank") and part.rank:
                                save_rank_data(part)
                     
                        
                        ranked_data_map = {}
                        for part in match.participants:
                            if hasattr(part, "puuid") and part.puuid:
                                from core.rank_data import get_cached_rank
                                rank = getattr(part, "rank", None) or get_cached_rank(part)
                                if rank and rank.get("tier") and rank.get("lp") is not None:
                                    ranked_data_map[part.puuid] = rank
                        
                         
                        
                        
                        # Recalcula tiempo estimado
                        game_length = int((cache_entry.get("game_length") or 0) + (time.time() - cache_entry["timestamp"]))
                        match.game_length = game_length

                        puuid_to_player = {a.puuid: player for a in player.accounts if a.puuid}
                        embed, files = await create_match_embed(match, puuid_to_player, ranked_data_map)
                        mins, secs = divmod(game_length, 60)
                        embed.add_field(
                            name="⏳ Tiempo estimado desde notificación",
                            value=f"{mins}m {secs}s (estimado, por rate limit)",
                            inline=False
                        )
                        embed.title = f"Partida de {player.name} ({account.riot_id['game_name']}#{account.riot_id['tag_line']}) 🎮 (rate limit)"
                        await ctx.send(embed=embed, files=files)
                        add_to_retry_queue(puuid)
                        return

                    if status == 404:
                        break  # Jugador no está en partida

                    await asyncio.sleep(2)

        if not found:
            await ctx.send(f"❌ {player.name} no está en ninguna partida activa en ninguna de sus cuentas.")

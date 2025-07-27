#traking/soloq/active_game_checker.py

import asyncio
import aiohttp

from tracking.soloq.accounts_io import load_accounts_cached
from tracking.soloq.active_game_cache import set_active_game_with_ranked, ACTIVE_GAME_CACHE
from utils.cache_utils import limpiar_cache_partidas_viejas
from utils.spectate_bat import generar_bat_spectate
from ui.active_match_embed import create_match_embed
from core.retry_handler import add_to_retry_queue
from core.ranked_cache import get_rank_data_or_cache 
from apis.riot_api import get_active_game
from tracking.soloq.notifier import (
    load_announced_games,
    save_announced_games,
    already_announced,
    mark_announced,
    clean_old_announcements,
)
from tracking.soloq.index_tracker import load_last_index, save_last_index
from models.soloq_match import SoloQMatch
from tracking.soloq.channel_config import load_channel_ids
from tracking.soloq.tracker_utils import is_valid_game
from utils.player_filters import get_tracked_players
from tracking.soloq.accounts_io import load_tracked_accounts
from utils.player_filters import get_tracked_players
from core.rank_data import get_cached_rank, save_rank_data


class ActiveGameTracker:
    def __init__(self, bot):
        self.bot = bot
        self.players = get_tracked_players(load_tracked_accounts())  # Solo trackeados
        self.total_players = len(self.players)
        self.index = load_last_index()
        self.announced_games = load_announced_games()
        self.embed_cache = {}

        self.puuid_to_player = {
            acc.puuid: player
            for player in self.players
            for acc in player.accounts
            if acc.puuid
        }

    async def run(self):
        while True:
            self.index = 0
            async with aiohttp.ClientSession() as session:
                while self.index < self.total_players:
                    player = self.players[self.index]
                    await self.check_player(player, session)
                    self.index += 1
                    await asyncio.sleep(0.5)
            self.cleanup()
            print("✅ Revisión de partidas finalizada.")
            await asyncio.sleep(5)

    async def check_player(self, player, session):
        for account in player.accounts:
            if not account.puuid:
                continue

            found = False
            while True:
                print(f"🔍 Revisando {player.name} | {account.riot_id['game_name']}#{account.riot_id['tag_line']}")

                try:
                    game_data, status = await get_active_game(account.puuid, session)
                except Exception as e:
                    print(f"[ERROR] Excepción consultando Riot API: {e}")
                    break

                if status == 429:
                    print("⚠️ Rate Limit alcanzado. Reintentando en 8s...")
                    await asyncio.sleep(8)
                    continue

                if status == 404:
                    ACTIVE_GAME_CACHE.pop(account.puuid, None)
                    break

                if not game_data:
                    print(f"❌ No se encontró partida en vivo para {player.name} | {account.riot_id['game_name']}#{account.riot_id['tag_line']}")
                    break

                if not is_valid_game(game_data):
                    print(f"❌ Partida encontrada pero no válida para {player.name} | {account.riot_id['game_name']}#{account.riot_id['tag_line']}")
                    break

                match = SoloQMatch.from_riot_game_data(game_data)
                await self.notificar_partida(account, match, session)  # <-- PASA session AQUÍ
                print(f"✅ Partida activa encontrada para {player.name} | {account.riot_id['game_name']}#{account.riot_id['tag_line']}")
                found = True
                break

            if not found:
                print(f"⏹️ {player.name} | {account.riot_id['game_name']}#{account.riot_id['tag_line']} NO tiene partida activa.")


    import aiohttp

    async def notificar_partida(self, account, match: SoloQMatch, session):  # <-- AGREGA session AQUÍ
        game_id = match.game_id

        msi_puuids = {p.puuid for p in match.participants if p.puuid}
        ranked_map = {}

        for p in match.participants:
            if not p.puuid:
                continue

            cached_rank = get_cached_rank(p)

            if cached_rank:
                ranked_map[p.puuid] = cached_rank
            else:
                rank_data = await get_rank_data_or_cache(p.puuid, session)
                ranked_map[p.puuid] = rank_data

                # Guardar en el JSON
                if rank_data["tier"] != "Desconocido":
                    p.rank = rank_data
                    save_rank_data(p)

        player = self.puuid_to_player.get(account.puuid)
        player_name = player.name if player else account.riot_id["game_name"]
        set_active_game_with_ranked(account.puuid, match.datos_extra, ranked_map, player_name)
        
        for guild_id_str, channel_id in load_channel_ids().items():
            if already_announced(self.announced_games, game_id, channel_id):
                continue

            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            embed, files = await create_match_embed(match, self.puuid_to_player, ranked_map)

            try:
                await channel.send(embed=embed, files=files)
                mark_announced(self.announced_games, game_id, channel_id)
            except Exception as e:
                print(f"[ERROR] No se pudo enviar mensaje a canal {channel_id}: {e}")

    def cleanup(self):
        clean_old_announcements(self.announced_games)
        save_announced_games(self.announced_games)
        limpiar_cache_partidas_viejas()
        save_last_index(self.index if self.index < self.total_players else 0)
        print("✅ Revisión de partidas finalizada.")

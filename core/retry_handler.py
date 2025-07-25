# core/retry_handler.py

import asyncio
from apis.riot_api import get_active_game
from tracking.soloq.active_game_cache import set_active_game, ACTIVE_GAME_CACHE
import aiohttp

RETRY_PUUIDS = []
RETRY_WORKER_RUNNING = False

def add_to_retry_queue(puuid: str):
    """Agrega un PUUID a la cola de reintentos para verificar partida activa"""
    if puuid not in RETRY_PUUIDS:
        RETRY_PUUIDS.append(puuid)
        if not RETRY_WORKER_RUNNING:
            asyncio.create_task(retry_worker())

async def retry_worker():
    """Tarea asíncrona que reintenta obtener partidas activas"""
    global RETRY_WORKER_RUNNING
    RETRY_WORKER_RUNNING = True

    async with aiohttp.ClientSession() as session:
        while RETRY_PUUIDS:
            puuid = RETRY_PUUIDS[0]
            while True:
                active_game, status = await get_active_game(puuid, session)

                if status == 200 and active_game:
                    set_active_game(puuid, active_game)
                    break
                elif status == 404:
                    ACTIVE_GAME_CACHE.pop(puuid, None)
                    break
                elif status != 429:
                    break

                await asyncio.sleep(2)

        RETRY_PUUIDS.pop(0)

    RETRY_WORKER_RUNNING = False

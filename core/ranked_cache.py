# core/ranked_cache.py

import time
import asyncio
from apis.riot_api import get_ranked_data
from utils.helpers import parse_ranked_data
import aiohttp

RANKED_CACHE = {}  # {puuid: (timestamp, ranked_data)}
CACHE_TTL = 120  # segundos

async def get_rank_data_or_cache(puuid: str, session: aiohttp.ClientSession, retries: int = 5, delay: float = 1.0) -> dict:
    for _ in range(retries):
        now = time.time()
        if puuid in RANKED_CACHE:
            ts, data = RANKED_CACHE[puuid]
            if now - ts < CACHE_TTL:
                return parse_ranked_data(data)

        ranked_data = await get_ranked_data(puuid, session)
        if ranked_data:
            RANKED_CACHE[puuid] = (now, ranked_data)
            return parse_ranked_data(ranked_data)
        await asyncio.sleep(delay)
    return {"tier": "Desconocido", "division": "", "lp": 0}





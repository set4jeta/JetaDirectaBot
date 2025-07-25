#apis/riot_api.py
import aiohttp
import os
#from .champion_cache import CHAMPION_ID_TO_NAME
import urllib.parse
import cloudscraper
import asyncio

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
HEADERS = {"X-Riot-Token": RIOT_API_KEY}

# Región para Riot Account API (Americas)
RIOT_BASE_URL = "https://europe.api.riotgames.com"
# Región para NA-specific endpoints
EU_BASE_URL = "https://euw1.api.riotgames.com"

# ————————————————

#endpoint para obtene los Puuids de los jugadores desde Riot
from urllib.parse import quote

async def get_puuid_from_riot_id(game_name: str, tag_line: str, session: aiohttp.ClientSession) -> tuple[str | None, int]:
    game_name_encoded = quote(game_name)
    tag_line_encoded = quote(tag_line)
    url = f"{RIOT_BASE_URL}/riot/account/v1/accounts/by-riot-id/{game_name_encoded}/{tag_line_encoded}"
    async with session.get(url, headers=HEADERS) as resp: # type: ignore
        if resp.status == 200:
            data = await resp.json()
            return data.get("puuid"), 200
        elif resp.status == 404:
            return None, 404
        else:
            return None, resp.status

async def get_active_game(puuid: str, session: aiohttp.ClientSession) -> tuple[dict | None, int]:
    url = f"{EU_BASE_URL}/lol/spectator/v5/active-games/by-summoner/{puuid}"
    async with session.get(url, headers=HEADERS) as resp: # type: ignore
        if resp.status == 200:
            return await resp.json(), 200
        return None, resp.status

async def get_ranked_data(puuid: str, session: aiohttp.ClientSession) -> dict | None:
    url = f"{EU_BASE_URL}/lol/league/v4/entries/by-puuid/{puuid}"
    async with session.get(url, headers=HEADERS) as resp: # type: ignore
        if resp.status == 200:
            return await resp.json()
        return None
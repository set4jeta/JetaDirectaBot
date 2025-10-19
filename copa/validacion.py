#copa/validacion.py
import aiohttp
import os

RIOT_API_KEY = os.getenv("RIOT_API_KEY")  # Asegúrate de que esté configurada
HEADERS = {"X-Riot-Token": RIOT_API_KEY}
EU_BASE_URL = "https://euw1.api.riotgames.com"
ACCOUNT_BASE_URL = "https://europe.api.riotgames.com"

async def obtener_region_activa(puuid, game="lol"):
    """
    Devuelve la región activa del jugador usando su puuid.
    Ejemplo de resultado: "EUW1", "NA1", etc.
    """
    url = f"{ACCOUNT_BASE_URL}/riot/account/v1/region/by-game/{game}/by-puuid/{puuid}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp: # type: ignore
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("region")

async def validar_cuenta(game_name, tag_line):
    """
    Obtiene la cuenta de Riot por Riot ID y añade el campo 'platform' (región activa).
    """
    async with aiohttp.ClientSession() as session:
        url = f"{ACCOUNT_BASE_URL}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        async with session.get(url, headers=HEADERS) as resp: # type: ignore
            if resp.status != 200:
                return None
            data = await resp.json()
            puuid = data.get("puuid")
            if not puuid:
                return None

    # Obtener región activa (plataforma)
    region = await obtener_region_activa(puuid)
    if not region:
        return None

    data["platform"] = region  # Añade la plataforma (EUW1, NA1, etc.)
    return data

async def obtener_elo(puuid):
    """
    Obtiene el ELO (liga) del jugador según su PUUID. Solo busca RANKED_SOLO_5x5.
    """
    async with aiohttp.ClientSession() as session:
        url = f"{EU_BASE_URL}/lol/league/v4/entries/by-puuid/{puuid}"
        async with session.get(url, headers=HEADERS) as resp: # type: ignore
            if resp.status != 200:
                return None
            data = await resp.json()
            for entry in data:
                if entry["queueType"] == "RANKED_SOLO_5x5":
                    return entry
            return None

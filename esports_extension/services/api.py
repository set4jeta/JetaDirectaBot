import aiohttp
import json
import os
from typing import Optional, Dict
import requests



class APIClient:
    def __init__(self):
        self.API_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
        self.HEADERS = {"x-api-key": self.API_KEY, "User-Agent": "Mozilla/5.0",
                        }
        
        self.firestore_headers = {
            
            "Accept": "application/json",
            
            "Referer": "https://piltoverpost.gg",  # Solo si realmente lo necesitas
            "Origin": "https://piltoverpost.gg",  
        }
        
        
            
    async def get_schedule(self):
        
          
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US",
                headers=self.HEADERS
            ) as response:
                if response.status != 200:
                    raise Exception(f"Error {response.status} al acceder a url")
                print(f"Accediendo a la API: {response.url}")
                return await response.json()

    async def get_event_details(self, event_id):
        
            
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={event_id}",
                headers=self.HEADERS
            ) as response:
                if response.status != 200:
                    raise Exception(f"Error {response.status} al acceder a url")
                (print(f"Accediendo a la API: {response.url}"))
                return await response.json()

    async def get_livestats(self, game_id, starting_time: Optional[str] = None):
            
        if starting_time:
            url = f"https://feed.lolesports.com/livestats/v1/window/{game_id}?startingTime={starting_time}"
        else:
            url = f"https://feed.lolesports.com/livestats/v1/window/{game_id}" 
        print(f"[DEBUG] URL: {url}")
        print(f"[DEBUG] starting_time usado: {starting_time} (type: {type(starting_time)})")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self.HEADERS
            ) as response:
                if response.status != 200:
                    raise Exception(f"Error {response.status} al acceder a url")
                print(f"Accediendo a la API: {response.url}")
                return await response.json()

    
    
    
    async def get_firestore_game_data(self, game_id: str) -> Optional[Dict]:
        """
        Obtiene datos en tiempo real de Firestore para un game_id específico
        """
        url = f"https://firestore.googleapis.com/v1/projects/lolesports-ink/databases/(default)/documents/games/{game_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.firestore_headers) as response:
                    if response.status != 200:
                        print(f"[Firestore] Error {response.status} para game_id {game_id}")
                        return None
                    return await response.json()
        except Exception as e:
            print(f"[Firestore] Exception: {str(e)}")
            return None

    
    
FIREBASE_API_KEY = "AIzaSyAWJjAJglbZ8L2gAPipdMMfcQQWdC4UOMQ"  # API_KEY pública de lolesports-ink
FIREBASE_PROJECT_ID = "lolesports-ink"

def firebase_sign_in_anonymous():
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"returnSecureToken": True}
    response = requests.post(url, json=payload)
    response.raise_for_status()
    data = response.json()
    return data["idToken"], data["localId"]

def firestore_query_matches():
    id_token, _ = firebase_sign_in_anonymous()
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/matches"
    headers = {"Authorization": f"Bearer {id_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 403:
        print("❌ No tienes permiso para acceder a la colección 'matches'.")
        return None

    response.raise_for_status()
    return response.json()
     
     
     

# Ejemplo de uso

#client = APIClient()
#data = await client.get_schedule()
#event = ScheduleEvent(data["data"]["schedule"]["events"][0])
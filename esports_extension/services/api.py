import aiohttp
import json
import os
from typing import Optional, Dict
import requests

# Las claves vienen de la configuración central (y por tanto del .env), nunca
# del código: así se pueden rotar sin editar ni redesplegar.
import config
from utils.logger import get_logger

log = get_logger("esports.api")


class LolEsportsError(Exception):
    """Fallo HTTP de la API de lolesports, **con el código accesible**.

    Antes esto era `Exception(f"Error {status} al acceder a url")`: el código
    quedaba dentro del texto y no había forma de mirarlo. Y sí se miraba —
    `tracker_service` tiene dos ramas que preguntan por él:

        if hasattr(e, "status") and e.status == 404:   -> ganador por chat
        elif getattr(e, "status", None) == 204:        -> partida sin empezar

    Con una `Exception` pelada, `hasattr(e, "status")` es False **siempre**, así
    que las dos ramas eran código muerto y todo caía en el `else`, que hace
    `log.error`. Por eso un 204 ("la partida aún no ha empezado", que es el caso
    normal antes del inicio) salía en la consola como ERROR, y la detección del
    ganador por el chat de Twitch no se disparaba nunca.
    """

    def __init__(self, status: int, url: str, mensaje: str = ""):
        self.status = status
        self.url = url
        self.mensaje = mensaje
        detalle = f": {mensaje}" if mensaje else ""
        super().__init__(f"HTTP {status} en {url}{detalle}")


class APIClient:
    def __init__(self):
        self.API_KEY = config.LOL_API_KEY
        self.HEADERS = {
            "x-api-key": self.API_KEY,
            # Cloudflare bloquea el User-Agent por defecto de aiohttp (403,
            # "error code: 1010"). Hay que presentarse como navegador.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
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
                    raise LolEsportsError(response.status, str(response.url))
                log.debug(f"Accediendo a la API: {response.url}")
                return await response.json()

    async def get_event_details(self, event_id):
        
            
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={event_id}",
                headers=self.HEADERS
            ) as response:
                if response.status != 200:
                    raise LolEsportsError(response.status, str(response.url))
                log.debug("Accediendo a la API: %s", response.url)
                return await response.json()

    async def get_livestats(self, game_id, starting_time: Optional[str] = None):
        """Ventana de estadísticas en vivo de una partida.

        Sobre `starting_time`
        ---------------------
        El feed **rechaza cualquier ventana que termine hace menos de 600 s**.
        Medido contra el feed real (`scripts/_probe_livestats_umbral.py`):

            -300s .. -600s -> 400 BAD_QUERY_PARAMETER
                              "disallowed window with end time less than 600
                               sec old (was 29.12 sec old)"
            -610s y más    -> 200

        `tracker_service` pedía `ahora - 37s`, así que **todas** sus llamadas con
        marca de tiempo eran 400: cinco ERROR por vuelta en la consola y ni un
        frame aprovechado.

        Y no hace falta: sin el parámetro el feed devuelve por su cuenta la
        ventana más reciente que permite, y medido resultó **más fresca** que
        pedirla a mano (531-2576 s de antigüedad frente a los 610 s fijos del
        cálculo manual). Así que el camino bueno es no mandar `startingTime`, y
        se deja el parámetro solo para poder pedir un instante concreto del
        pasado.
        """
        if starting_time:
            url = f"https://feed.lolesports.com/livestats/v1/window/{game_id}?startingTime={starting_time}"
        else:
            url = f"https://feed.lolesports.com/livestats/v1/window/{game_id}" 
        log.debug(f"URL: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self.HEADERS
            ) as response:
                # 204 sin cuerpo: la partida existe pero todavía no manda datos.
                # Es el estado normal antes del inicio, no un error.
                if response.status != 200:
                    cuerpo = ""
                    if response.status not in (204, 404):
                        cuerpo = (await response.text())[:200]
                    raise LolEsportsError(response.status, str(response.url), cuerpo)
                log.debug(f"Accediendo a la API: {response.url}")
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
                        log.error(f"[Firestore] Error {response.status} para game_id {game_id}")
                        return None
                    return await response.json()
        except Exception as e:
            log.debug(f"[Firestore] Exception: {str(e)}")
            return None

    
    
FIREBASE_API_KEY = config.FIREBASE_API_KEY
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
        log.debug("❌ No tienes permiso para acceder a la colección 'matches'.")
        return None

    response.raise_for_status()
    return response.json()
     
     
     

# Ejemplo de uso

#client = APIClient()
#data = await client.get_schedule()
#event = ScheduleEvent(data["data"]["schedule"]["events"][0])
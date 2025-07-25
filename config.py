from dotenv import load_dotenv
import os

load_dotenv()  # carga variables del .env al entorno

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LOL_API_KEY = os.getenv("LOL_API_KEY")
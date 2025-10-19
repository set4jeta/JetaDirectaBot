import pytchat
from collections import Counter
from twitchio.ext import commands
import asyncio

async def analyze_chat_and_update_wins(event_details, min_mentions=20, max_messages=500):
    """
    Analiza el chat del stream principal (YouTube o Twitch), detecta el equipo ganador y suma game_wins.
    :param event_details: objeto EventDetails (con .streamsEventDetails y .teamsEventDetails)
    :return: code del equipo ganador o None
    """
    streams = event_details.streamsEventDetails
    teams = event_details.teamsEventDetails
    team_codes = [t.code for t in teams]

    # Selecciona el stream principal (YouTube > Twitch)
    youtube_stream = next((s for s in streams if s.provider == "youtube"), None)
    twitch_stream = next((s for s in streams if s.provider == "twitch"), None)
    stream = youtube_stream or twitch_stream
    if not stream:
        return None  # No hay stream soportado

    keyword_counts = Counter()
    messages_checked = 0

    # --- YouTube ---
    if stream.provider == "youtube":
        video_id = stream.parameter.split("v=")[-1] if "v=" in stream.parameter else stream.parameter
        chat = pytchat.create(video_id=video_id)
        while chat.is_alive() and messages_checked < max_messages:
            for message in chat.get().sync_items(): # type: ignore
                text = message.message.lower()
                for code in team_codes:
                    # Patrones: "gg DZ", "DZ win", "ganó DZ"
                    if f"gg {code.lower()}" in text or f"{code.lower()} win" in text or f"ganó {code.lower()}" in text:
                        keyword_counts[code] += 1
                messages_checked += 1
                if messages_checked >= max_messages:
                    break

    # --- Twitch ---
    elif stream.provider == "twitch":
        channel_name = stream.parameter.lower()
        keyword_counts = await analyze_twitch_chat(channel_name, team_codes, min_mentions, max_messages)

    # Decide ganador y suma game_wins
    if keyword_counts:
        winner, count = keyword_counts.most_common(1)[0]
        if count >= min_mentions:
            # Suma 1 a game_wins del equipo ganador en teamsEventDetails
            for t in teams:
                if t.code == winner:
                    if hasattr(t, "game_wins"):
                        t.game_wins += 1
                    elif hasattr(t, "gameWins"):
                        t.gameWins += 1
                    elif hasattr(t, "result") and isinstance(t.result, dict):
                        t.result["gameWins"] = t.result.get("gameWins", 0) + 1
            return winner
    return None

# Twitch helper
async def analyze_twitch_chat(channel_name, team_codes, min_mentions, max_messages):
    class Bot(commands.Bot):
        def __init__(self):
            super().__init__(
                token='oauth:7fvxj3ra255umt5d4h8zlfvbfq5jfp',  # <-- Cambia por tu token
                prefix='!',
                initial_channels=[channel_name]
            )
            self.keyword_counts = Counter()
            self.messages_checked = 0

        async def event_message(self, message):
            if self.messages_checked >= max_messages:
                return
            text = message.content.lower() # type: ignore
            for code in team_codes:
                if f"gg {code.lower()}" in text or f"{code.lower()} win" in text or f"ganó {code.lower()}" in text:
                    self.keyword_counts[code] += 1
            self.messages_checked += 1

    bot = Bot()
    task = asyncio.create_task(bot.start())
    await asyncio.sleep(10)  # Espera 10 segundos para recolectar mensajes
    await bot.close()
    return bot.keyword_counts
# utils/time_utils.py
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import aiohttp

async def get_network_time():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.google.com") as response:
                if date_header := response.headers.get("Date"):
                    return parsedate_to_datetime(date_header).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)
    
# Puedes poner esto en utils/time_utils.py
def round_down_to_10_seconds(dt):
    dt = dt.replace(microsecond=0)
    seconds = (dt.second // 10) * 10
    return dt.replace(second=seconds)
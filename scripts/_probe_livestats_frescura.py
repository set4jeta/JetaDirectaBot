"""¿Qué frescura da el feed sin `startingTime` frente a pedirlo a mano?

Si la llamada sin parámetro ya devuelve la ventana más reciente que el feed
permite, calcular la marca de tiempo a mano no aporta nada y además se puede
equivocar (es justo lo que pasaba: `ahora - 37s` daba 400 siempre).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import aiohttp  # noqa: E402

from esports_extension.services.api import APIClient  # noqa: E402
from esports_extension.utils.time_utils import (  # noqa: E402
    get_network_time,
    round_down_to_10_seconds,
)

FEED = "https://feed.lolesports.com/livestats/v1/window"


def _edad(ts: str, ahora) -> float:
    t = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return (ahora - t).total_seconds()


async def main() -> int:
    cliente = APIClient()
    datos = await cliente.get_schedule()
    eventos = datos.get("data", {}).get("schedule", {}).get("events", [])

    juegos = []
    for evento in eventos:
        if not (isinstance(evento, dict) and evento.get("state") == "inProgress"):
            continue
        match_id = (evento.get("match") or {}).get("id")
        if not match_id:
            continue
        detalle = await cliente.get_event_details(match_id)
        ev = detalle.get("data", {}).get("event", {})
        liga = (ev.get("league") or {}).get("name", "?")
        for juego in (ev.get("match") or {}).get("games", []):
            if juego.get("state") == "inProgress":
                juegos.append((str(juego.get("id")), liga))

    if not juegos:
        print("No hay ninguna partida en curso ahora mismo.")
        return 0

    print("=" * 78)
    print("FRESCURA DEL FEED")
    print("=" * 78)
    print(f"{'liga':<18} {'sin param':>12} {'-610s':>12} {'frames':>8}")
    print("-" * 78)

    ahora = await get_network_time()
    async with aiohttp.ClientSession(headers=cliente.HEADERS) as session:
        for gid, liga in juegos:
            sin_param = "-"
            n_frames = 0
            async with session.get(f"{FEED}/{gid}") as r:
                if r.status == 200:
                    cuerpo = await r.json()
                    frames = cuerpo.get("frames") or []
                    n_frames = len(frames)
                    if frames:
                        sin_param = f"{_edad(frames[-1]['rfc460Timestamp'], ahora):.0f}s"
                else:
                    sin_param = f"HTTP {r.status}"

            con_param = "-"
            dt = round_down_to_10_seconds(ahora - timedelta(seconds=610))
            marca = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            async with session.get(f"{FEED}/{gid}?startingTime={marca}") as r:
                if r.status == 200:
                    cuerpo = await r.json()
                    frames = cuerpo.get("frames") or []
                    if frames:
                        con_param = f"{_edad(frames[-1]['rfc460Timestamp'], ahora):.0f}s"
                else:
                    con_param = f"HTTP {r.status}"

            print(f"{liga:<18} {sin_param:>12} {con_param:>12} {n_frames:>8}")

    print()
    print("Interpretación: si la columna 'sin param' es igual o más fresca que")
    print("'-610s', la llamada sin parámetro es la correcta y calcular la marca")
    print("de tiempo a mano solo añade una petición de reloj y un modo de fallo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

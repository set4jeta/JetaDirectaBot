"""¿Por qué el feed de lolesports contesta 400 y qué offset sí acepta?

En la consola del bot salían cinco líneas seguidas de

    ERROR | esports.tracker | Error al obtener LiveStats: Error 400 al acceder a url

Esto mide dos cosas contra el feed real:

1. Qué código devuelve el endpoint `window/<game_id>` sin `startingTime`.
2. Qué códigos devuelve con `startingTime` a distintos retrasos, para saber si
   los 37 s que usa `tracker_service` son suficientes.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
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


async def _codigo(session, url: str) -> tuple[int, int]:
    async with session.get(url) as r:
        cuerpo = await r.read()
        return r.status, len(cuerpo)


async def main() -> int:
    cliente = APIClient()

    print("=" * 74)
    print("SONDEO DEL FEED DE LIVESTATS")
    print("=" * 74)

    datos = await cliente.get_schedule()
    eventos = datos.get("data", {}).get("schedule", {}).get("events", [])
    en_vivo = [
        e for e in eventos
        if isinstance(e, dict) and (e.get("match") or {}) and e.get("state") == "inProgress"
    ]
    print(f"   eventos en el calendario : {len(eventos)}")
    print(f"   en curso ahora mismo     : {len(en_vivo)}")

    # Los game_id salen de getEventDetails, no del calendario.
    juegos: list[tuple[str, str, str]] = []
    for evento in en_vivo[:4]:
        match_id = (evento.get("match") or {}).get("id")
        if not match_id:
            continue
        detalle = await cliente.get_event_details(match_id)
        ev = detalle.get("data", {}).get("event", {})
        liga = (ev.get("league") or {}).get("name", "?")
        for juego in (ev.get("match") or {}).get("games", []):
            juegos.append((str(juego.get("id")), juego.get("state", "?"), liga))

    if not juegos:
        print()
        print("   No hay ningún partido en curso: sin partida en vivo el feed")
        print("   contesta 404 para cualquier game_id, así que el sondeo de")
        print("   offsets no diría nada. Vuelve a ejecutarlo con LEC/LCK en vivo.")
        return 0

    print()
    for gid, estado, liga in juegos:
        print(f"   {liga:<16} game {gid}  estado={estado}")

    ahora = await get_network_time()
    async with aiohttp.ClientSession(headers=cliente.HEADERS) as session:
        for gid, estado, liga in juegos:
            print()
            print(f"-- {liga} · game {gid} (estado {estado}) " + "-" * 20)

            code, size = await _codigo(session, f"{FEED}/{gid}")
            print(f"   sin startingTime          -> {code} ({size} bytes)")

            for retraso in (20, 37, 45, 60, 90, 120):
                dt = round_down_to_10_seconds(ahora - timedelta(seconds=retraso))
                ts = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                code, size = await _codigo(session, f"{FEED}/{gid}?startingTime={ts}")
                marca = "ok " if code == 200 else "   "
                print(f"   {marca}startingTime -{retraso:>3}s      -> {code} ({size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Confirma el umbral real del feed: ¿desde qué retraso deja de dar 400?

El mensaje del 400 lo dice literalmente:

    "disallowed window with end time less than 600 sec old (was 29.12 sec old).
     requested window: [..., ...]) ahead of broadcast"

O sea: la ventana pedida (10 s a partir de `startingTime`) tiene que **terminar
al menos 600 s en el pasado**. El bot pedía `ahora - 37s`, que es 563 s
demasiado reciente, así que *todas* sus peticiones con `startingTime` eran 400.

Esto lo comprueba barriendo el retraso alrededor de los 600 s.
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


async def main() -> int:
    cliente = APIClient()
    datos = await cliente.get_schedule()
    eventos = datos.get("data", {}).get("schedule", {}).get("events", [])

    gid = None
    for evento in eventos:
        if not (isinstance(evento, dict) and evento.get("state") == "inProgress"):
            continue
        match_id = (evento.get("match") or {}).get("id")
        if not match_id:
            continue
        detalle = await cliente.get_event_details(match_id)
        ev = detalle.get("data", {}).get("event", {})
        for juego in (ev.get("match") or {}).get("games", []):
            if juego.get("state") == "inProgress":
                gid = str(juego.get("id"))
                break
        if gid:
            break

    if not gid:
        print("No hay ninguna partida en curso ahora mismo.")
        return 0

    print("=" * 74)
    print(f"UMBRAL DEL FEED · game {gid}")
    print("=" * 74)

    ahora = await get_network_time()
    async with aiohttp.ClientSession(headers=cliente.HEADERS) as session:
        async with session.get(f"{FEED}/{gid}") as r:
            cuerpo = await r.json() if r.status == 200 else {}
            frames = cuerpo.get("frames") or []
            ts = frames[-1].get("rfc460Timestamp") if frames else "?"
            print(f"\n   sin startingTime -> {r.status} · último frame {ts}")
            if frames:
                edad = (ahora - _parse(ts)).total_seconds()
                print(f"      ese frame tiene {edad:.0f}s de antigüedad")

        print()
        for retraso in (300, 500, 590, 600, 610, 620, 700, 900):
            dt = round_down_to_10_seconds(ahora - timedelta(seconds=retraso))
            marca = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            async with session.get(f"{FEED}/{gid}?startingTime={marca}") as r:
                if r.status == 200:
                    datos_r = await r.json()
                    n = len(datos_r.get("frames") or [])
                    print(f"   ok  -{retraso:>4}s -> 200 · {n} frame(s)")
                else:
                    texto = await r.text()
                    razon = "ventana demasiado reciente" if "less than 600" in texto else texto[:70]
                    print(f"       -{retraso:>4}s -> {r.status} · {razon}")

    return 0


def _parse(ts: str):
    from datetime import datetime, timezone

    return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""¿Qué dice exactamente el 400 del feed y qué formato de `startingTime` acepta?

El sondeo anterior mostró que **cualquier** offset da 400, así que el problema no
es el retraso: es el parámetro. Esto imprime el cuerpo del error y prueba varios
formatos de marca de tiempo sobre una partida en curso.
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
    en_vivo = [
        e for e in eventos
        if isinstance(e, dict) and (e.get("match") or {}) and e.get("state") == "inProgress"
    ]

    gid = None
    for evento in en_vivo:
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
    print(f"FORMATOS DE startingTime · game {gid}")
    print("=" * 74)

    ahora = await get_network_time()
    base = round_down_to_10_seconds(ahora - timedelta(seconds=60))

    # El de `tracker_service` es el primero: `%Y-%m-%dT%H:%M:%S.000Z`, aplicado
    # sobre un datetime **con tzinfo UTC**.
    formatos = {
        "actual (.000Z sobre aware)": base.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "isoformat() crudo": base.isoformat(),
        "sin milisegundos + Z": base.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "naive + .000Z": base.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "segundo no múltiplo de 10": (base + timedelta(seconds=3)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        ),
    }

    async with aiohttp.ClientSession(headers=cliente.HEADERS) as session:
        async with session.get(f"{FEED}/{gid}") as r:
            print(f"\n   sin parámetro -> {r.status}")

        for etiqueta, ts in formatos.items():
            url = f"{FEED}/{gid}?startingTime={ts}"
            async with session.get(url) as r:
                cuerpo = (await r.text())[:220].replace("\n", " ")
                print(f"\n   {etiqueta}")
                print(f"      ts   : {ts}")
                print(f"      code : {r.status}")
                if r.status != 200:
                    print(f"      body : {cuerpo}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

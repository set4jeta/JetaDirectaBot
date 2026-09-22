"""Comprueba la salud real del pipeline de tracking.

Para cada cuenta trackeada hace UNA llamada a spectator-v5 y clasifica la
respuesta:

    200 -> en partida ahora mismo
    404 -> no en partida (correcto, es el caso normal)
    4xx -> PUUID inválido u otro error: el bot es CIEGO a esa cuenta

Este script es el que demuestra el bug de los PUUIDs corruptos y verifica que
la reparación funcionó.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from apis.riot_client import RiotApiError, close_riot_client, get_riot_client  # noqa: E402
from utils.game_clock import desde_partida  # noqa: E402

FILES = {
    "accounts_from_teams (trackeados)": ROOT / "tracking" / "soloq" / "accounts_from_teams.json",
    "accounts (leaderboard)": ROOT / "tracking" / "soloq" / "accounts.json",
}

# Solo estas cuentas alimentan el tracker de partidas.
USE_ONLY_TRACKED_TEAMS = True


async def check_file(client, label: str, path: Path, only_tracked: bool) -> dict:
    players = json.loads(path.read_text(encoding="utf-8"))
    targets = []

    for player in players:
        if only_tracked and player.get("team") not in TRACKED_TEAMS:
            continue
        for account in player.get("accounts", []):
            if account.get("stale") or not account.get("puuid"):
                continue
            targets.append((player.get("displayName") or player.get("name"), account))

    print()
    print("=" * 70)
    print(f"{label}  ·  {len(targets)} cuentas activas")
    print("=" * 70)

    async def probe(item):
        name, account = item
        try:
            game = await client.get_active_game(account["puuid"])
            return name, account, 200 if game else 404, game
        except RiotApiError as exc:
            return name, account, exc.status, None

    results = await asyncio.gather(*(probe(t) for t in targets))
    counter = Counter(status for _, _, status, _ in results)
    broken = [(n, a, s) for n, a, s, _ in results if s not in (200, 404)]
    live = [(n, a, g) for n, a, s, g in results if s == 200]

    print(f"   en partida (200)   : {counter[200]}")
    print(f"   no en partida (404): {counter[404]}")
    print(f"   ROTAS              : {len(broken)}")

    if live:
        print()
        print("   partidas detectadas ahora mismo:")
        for name, account, game in live[:12]:
            rid = account.get("riot_id", {})
            # `gameLength` a pelo sale negativo al principio de la partida (es el
            # reloj del espectador): se muestra el mismo texto que da el bot.
            print(
                f"     {name:<18} {rid.get('game_name')}#{rid.get('tag_line'):<10} "
                f"gameId={game['gameId']} {game['gameMode']} "
                f"{desde_partida(game).texto_corto()}"
            )

    if broken:
        print()
        print("   cuentas con PUUID inválido:")
        for name, account, status in broken[:12]:
            rid = account.get("riot_id", {})
            print(f"     [HTTP {status}] {name} · {rid.get('game_name')}#{rid.get('tag_line')}")

    return {"total": len(targets), "live": counter[200], "ok": counter[404], "broken": len(broken)}


TRACKED_TEAMS = {"G2", "FNC", "VIT", "TH", "KC", "NAVI", "GX", "BDS", "SK", "MKOI", "KOI", "LR"}


async def main() -> int:
    client = await get_riot_client()
    summary = {}
    try:
        label, path = next(iter(FILES.items()))
        # El tracker usa solo los equipos de TRACKED_TEAMS.
        summary[label] = await check_file(client, label, path, only_tracked=True)
        # El archivo grande se usa para !team / !info / !historial.
        label2, path2 = list(FILES.items())[1]
        summary[label2] = await check_file(client, label2, path2, only_tracked=False)
    finally:
        await close_riot_client()

    print()
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    failures = 0
    for label, s in summary.items():
        pct = (s["broken"] / s["total"] * 100) if s["total"] else 0
        print(f"   {label:<34} {s['broken']}/{s['total']} rotas ({pct:.1f}%) · {s['live']} en partida")
        failures += s["broken"]
    print()
    print(f"   red: {client.rate_limit_report()}")
    print()
    if failures == 0:
        print("   [OK] Ninguna cuenta activa tiene PUUID inválido.")
    else:
        print(f"   [FALLO] {failures} cuentas siguen rotas. Ejecuta scripts/repair_puuids.py")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

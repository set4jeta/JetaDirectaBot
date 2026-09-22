"""Prueba de humo del cliente de Riot contra la API real.

Ejecutar:  python scripts/verify_riot_client.py

No toca datos del proyecto: solo hace peticiones de lectura y comprueba que
el cliente, el rate limiter y el manejo de errores se comportan como deben.
"""

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from apis.riot_client import (  # noqa: E402
    RiotApiError,
    close_riot_client,
    get_riot_client,
)


async def main() -> int:
    client = await get_riot_client()
    failures = 0

    print("=" * 68)
    print("1) Key válida y User-Agent correcto")
    print("=" * 68)
    t0 = time.perf_counter()
    account = await client.get_account_by_riot_id("Caps", "G2W")
    elapsed = time.perf_counter() - t0
    if account and account.get("puuid"):
        print(f"   [OK] Caps#G2W -> puuid {account['puuid'][:20]}...  ({elapsed:.2f}s)")
    else:
        print("   [FALLO] account-v1 no devolvió puuid. Revisa la key o el User-Agent.")
        failures += 1

    puuid = account["puuid"] if account else None

    print()
    print("=" * 68)
    print("2) Endpoints que usa el bot")
    print("=" * 68)
    if puuid:
        league = await client.get_league_entries(puuid)
        print(f"   [{'OK' if league is not None else 'FALLO'}] league-v4 entries -> {len(league or [])} colas")
        if league is None:
            failures += 1

        soloq = await client.get_soloq_rank(puuid)
        if soloq:
            print(f"   [OK] soloq -> {soloq['tier']} {soloq['rank']} {soloq['leaguePoints']}LP")
        else:
            print("   [OK] soloq -> sin datos (cuenta unranked, es válido)")

        game = await client.get_active_game(puuid)
        print(f"   [OK] spectator-v5 -> {'EN PARTIDA gameId=%s' % game['gameId'] if game else 'no en partida (404 = correcto)'}")

        region = await client.get_region_by_puuid(puuid)
        print(f"   [{'OK' if region else 'FALLO'}] region -> {region}")
        if not region:
            failures += 1

        summoner = await client.get_summoner(puuid)
        print(f"   [{'OK' if summoner else 'FALLO'}] summoner-v4 -> nivel {summoner.get('summonerLevel') if summoner else '?'}")
        if not summoner:
            failures += 1

        ids = await client.get_match_ids(puuid, count=3)
        print(f"   [{'OK' if ids else 'AVISO'}] match-v5 ids -> {len(ids)} partidas")

    print()
    print("=" * 68)
    print("3) Cuenta inexistente -> None limpio, no excepción")
    print("=" * 68)
    ghost = await client.get_account_by_riot_id("NoExisteEsteNombre", "ZZZZ")
    if ghost is None:
        print("   [OK] devolvió None (404 manejado como resultado legítimo)")
    else:
        print("   [FALLO] debería devolver None")
        failures += 1

    print()
    print("=" * 68)
    print("4) PUUID corrupto -> error tipado y claro (el bug que tenías)")
    print("=" * 68)
    bad_puuid = "j6SMVnBwOSSDAQghv9VH0On31WXunf5-zBAD-PUUID-FALSO-j6SMVnBwOSSDAQ"
    try:
        await client.get_active_game(bad_puuid)
        print("   [AVISO] Riot aceptó el puuid falso (inesperado)")
    except RiotApiError as exc:
        print(f"   [OK] RiotApiError capturado: status={exc.status}")
        print(f"       mensaje: {str(exc)[:150]}")

    print()
    print("=" * 68)
    print("5) Rate limiter bajo carga: 60 peticiones seguidas")
    print("=" * 68)
    t0 = time.perf_counter()
    tasks = [client.get_account_by_riot_id("Caps", "G2W") for _ in range(60)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - t0
    ok = sum(1 for r in results if isinstance(r, dict))
    errs = sum(1 for r in results if isinstance(r, Exception))
    print(f"   {ok}/60 correctas, {errs} errores, {elapsed:.2f}s "
          f"({60 / elapsed:.1f} req/s efectivas)")
    print(f"   El limitador esperó {client._app_limiter.total_waits} vez/veces "
          f"({client._app_limiter.total_wait_seconds:.2f}s en total)")
    print(f"   stats: {client.rate_limit_report()}")

    print()
    print("=" * 68)
    print("6) Concurrencia real: 55 jugadores como en el tracker")
    print("=" * 68)
    t0 = time.perf_counter()
    sweep = await asyncio.gather(
        *[client.get_account_by_riot_id("Caps", "G2W") for _ in range(55)],
        return_exceptions=True,
    )
    elapsed = time.perf_counter() - t0
    ok = sum(1 for r in sweep if isinstance(r, dict))
    print(f"   {ok}/55 en {elapsed:.2f}s -> una pasada completa del tracker "
          f"tardaría esto en vez de minutos")
    if elapsed > 5:
        print("   [AVISO] más lento de lo esperado")

    await close_riot_client()

    print()
    print("=" * 68)
    print(f"RESULTADO: {'todo correcto' if failures == 0 else f'{failures} fallo(s)'}")
    print("=" * 68)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

#tracking/soloq/update_puuids.py

import os
import asyncio
import aiohttp
from apis.riot_api import get_puuid_from_riot_id
from models.bootcamp_player import BootcampPlayer
from tracking.soloq.accounts_io import load_accounts, save_accounts

async def update_puuids_in_accounts():
    print("📥 Cargando accounts.json...")
    players = load_accounts()
    updated = False

    async with aiohttp.ClientSession() as session:
        for player in players:
            print(f"👤 Revisando jugador: {player.name}")
            for account in player.accounts:
                if account.puuid:
                    continue

                game_name = account.riot_id.get("game_name", "")
                tag_line = account.riot_id.get("tag_line", "")

                if not game_name or not tag_line:
                    print(f"⛔ Riot ID incompleto: {game_name}#{tag_line}")
                    continue

                print(f"🔍 Buscando puuid para {game_name}#{tag_line}...")
                retries = 0
                while True:
                    puuid_real, status = await get_puuid_from_riot_id(game_name, tag_line, session)
                    if status == 200 and puuid_real:
                        print(f"🟡 Actualizado: {account.puuid} → {puuid_real}")
                        account.puuid = puuid_real
                        updated = True
                        break
                    elif status == 429:
                        retries += 1
                        print(f"⏳ Rate limit (429), reintentando en 8s... (intento {retries})")
                        await asyncio.sleep(8)
                        continue
                    elif status == 404:
                        print(f"❌ Cuenta no encontrada (404): {game_name}#{tag_line}")
                        break
                    else:
                        print(f"❌ No se pudo obtener el puuid (status {status})")
                        break

    if updated:
        print("💾 Guardando archivo actualizado...")
        save_accounts(players)
        print("✅ accounts.json actualizado con los PUUIDs.")
    else:
        print("✅ No había cuentas nuevas para actualizar.")

if __name__ == "__main__":
    asyncio.run(update_puuids_in_accounts())

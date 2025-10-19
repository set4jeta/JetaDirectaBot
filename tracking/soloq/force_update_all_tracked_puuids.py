import asyncio
import sys
import os
import aiohttp
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from apis.riot_api import get_puuid_from_riot_id
from tracking.soloq.accounts_io import load_tracked_accounts, save_tracked_accounts
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

async def force_update_all_tracked_puuids():
    print("🔄 Forzando revisión de TODOS los PUUIDs en accounts_from_teams.json...")
    players = load_tracked_accounts()
    updated = False
    async with aiohttp.ClientSession() as session:
        for player in players:
            print(f"👤 Revisando jugador: {player.name}")
            for account in player.accounts:
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
                        if account.puuid != puuid_real:
                            print(f"🟡 Actualizado: {account.puuid} → {puuid_real}")
                            account.puuid = puuid_real
                            updated = True
                        else:
                            print(f"✅ PUUID ya correcto")
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
        save_tracked_accounts(players)
        print("✅ accounts_from_teams.json actualizado con los PUUIDs.")
    else:
        print("✅ No había cuentas nuevas para actualizar en accounts_from_teams.json.")

if __name__ == "__main__":
    asyncio.run(force_update_all_tracked_puuids())
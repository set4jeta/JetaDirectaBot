# main.py

import asyncio
import subprocess
from config import DISCORD_TOKEN
from keep_alive import keep_alive
from tracking.soloq.accounts_from_leaderboard import main as update_accounts_from_leaderboard
from tracking.soloq.update_puuids import update_puuids_in_accounts
from tracking.soloq.update_tracked_puuids import update_puuids_in_tracked_accounts
from tracking.soloq.accounts_io import load_accounts, load_tracked_accounts      

from tracking.soloq.accounts_from_teams import main as update_accounts_from_teams

if __name__ == "__main__":
    # 0) Actualiza accounts.json desde el leaderboard
    print("🔄 Actualizando accounts.json desde leaderboard externo…")
    update_accounts_from_leaderboard()
    print("✅ accounts.json actualizado.")
    
    print("🔄 Actualizando accounts_from_teams.json desde equipos…")
    update_accounts_from_teams()
    print("✅ accounts_from_teams.json actualizado.")

    # 1) Verifica y actualiza PUUIDs SOLO si falta alguno
    
    players = load_accounts()
    needs_update = any(
        not account.puuid
        for player in players
        for account in player.accounts
    )
    if needs_update:
        print("🔄 Hay cuentas sin PUUID, actualizando antes de iniciar el bot...")
        asyncio.run(update_puuids_in_accounts())
        print("✅ PUUIDs verificados/corregidos.")
    else:
        print("✅ Todas las cuentas tienen PUUID.")



    # 1.1) Verifica y actualiza PUUIDs en accounts_from_teams.json
    tracked_players = load_tracked_accounts()
    needs_update_tracked = any(
        not account.puuid
        for player in tracked_players
        for account in player.accounts
    )
    if needs_update_tracked:
        print("🔄 Hay cuentas sin PUUID en accounts_from_teams.json, actualizando...")
        asyncio.run(update_puuids_in_tracked_accounts())
        print("✅ PUUIDs verificados/corregidos en accounts_from_teams.json.")
    else:
        print("✅ Todas las cuentas de accounts_from_teams.json tienen PUUID.")








    # 2) Comprueba token
    if DISCORD_TOKEN is None:
        raise RuntimeError("❌ La variable DISCORD_TOKEN no está definida en .env")

    # 3) Mantiene el bot activo (solo para entornos como Discloud o Replit)
    keep_alive()

    # 4) Ejecuta el bot desde bot_launcher
    print("🚀 Iniciando bot de Discord…")
    subprocess.run(["python", "-m", "core.bot_launcher"], check=True)

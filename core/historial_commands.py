import asyncio
import nextcord
from nextcord.ext import commands
from tracking.soloq.accounts_io import load_tracked_accounts
from apis.dpm_api import get_match_history_from_dpmlol, get_dpmlol_puuid
from utils.constants import TEAM_TRICODES
from utils.cache_utils import get_puuid_cached, load_puuid_cache


def register_historial_command(bot: commands.Bot):
    @bot.command(name="historial")
    async def historial(ctx, *, nombre: str = None):  # type: ignore
        nombre = (nombre or "").strip().lower().replace(" ", "")
        loading_msg = await ctx.send("⏳ Calculando datos, por favor espera...")

        jugadores = load_tracked_accounts()
        print(f"[DEBUG] Jugadores cargados: {[p.name for p in jugadores]}")

        if not nombre:
            partidas_globales = []

            async def fetch_player_matches(player, puuid_cache):
                partidas = []
                for account in player.accounts:
                    acc_name = account.riot_id.get("game_name", "")
                    acc_tag = account.riot_id.get("tag_line", "")
                    cuenta_str = f"{acc_name}#{acc_tag}" if acc_name and acc_tag else ""

                    # Obtener puuid cacheado o actualizar
                    puuid_dpmlol = await get_puuid_cached(acc_name, acc_tag, puuid_cache)
                    if not puuid_dpmlol:
                        print(f"[DEBUG] No se encontró PUUID en DPM.lol para {cuenta_str}")
                        continue

                    print(f"[DEBUG] Consultando historial en DPM.lol para PUUID: {puuid_dpmlol} ({cuenta_str})")
                    data = await get_match_history_from_dpmlol(puuid_dpmlol)
                    print(f"[DEBUG] Respuesta DPM LOL para {puuid_dpmlol}: {data}")
                    if not data or "matches" not in data or not data["matches"]:
                        continue
                    for match in data["matches"]:
                        participante = next((p for p in match.get("participants", []) if p.get("puuid") == puuid_dpmlol), None)
                        if not participante:
                            continue
                        partidas.append({
                            "player": player,
                            "participante": participante,
                            "match": match
                        })
                return partidas

            puuid_cache = load_puuid_cache()
            tasks = [fetch_player_matches(p, puuid_cache) for p in jugadores]
            all_results = await asyncio.gather(*tasks)
            for result in all_results:
                partidas_globales.extend(result)
            partidas_globales.sort(key=lambda x: x["match"].get("gameCreation", 0), reverse=True)
            partidas_top10 = partidas_globales[:10]

            POS_EMOJI = {
                "TOP": "🗻",
                "JUNGLE": "🌲",
                "MID": "✨",
                "ADC": "🏹",
                "BOTTOM": "🏹",
                "SUPPORT": "🛡️",
            }

            msg = "**Últimas 10 partidas (todos los jugadores, máximo 1 por jugador):**\n"
            msg += "Si quieres ver el historial de un jugador usa `!historial <jugador>` o `!historial <gameName#tag>`\n\n"
            for i, partida in enumerate(partidas_top10, 1):
                player = partida["player"]
                participante = partida["participante"]
                match = partida["match"]

                champ = participante.get("championName", "???")
                kills = participante.get("kills", 0)
                deaths = participante.get("deaths", 0)
                assists = participante.get("assists", 0)
                win = participante.get("win", False)
                duration = match.get("gameDuration", 0)
                mins = duration // 60
                pos = participante.get("teamPosition", "") or participante.get("position", "")
                if pos.upper() == "UTILITY":
                    pos = "SUPPORT"
                pos_str = f" ({pos.title()})" if pos else ""
                emoji = POS_EMOJI.get(pos.upper(), "") if pos else ""
                start_ts = match.get("gameCreation")
                hora_inicio_str = f"<t:{int(start_ts / 1000)}:f>" if isinstance(start_ts, int) else "¿?"
                resultado = "✅" if win else "❌"

                if player.accounts:
                    riot_id = player.accounts[0].riot_id
                    game_name = riot_id.get("game_name", "")
                    tag_line = riot_id.get("tag_line", "")
                else:
                    game_name = ""
                    tag_line = ""

                tricode = player.team.upper() if player.team else ""
                nick_str = f"{player.name} [{tricode}] ({game_name}#{tag_line})" if tricode else f"{player.name} ({game_name}#{tag_line})"
                msg += f"{i}. {resultado} **{champ}**{pos_str} {emoji} | {kills}/{deaths}/{assists} | {mins} min | 🕒 {hora_inicio_str} | {nick_str}\n"

            await loading_msg.edit(content=msg)
            return

        # Historial individual
        nombre_input = (nombre or "").strip().lower()
        nombre_input_sin_espacios = nombre_input.replace(" ", "")

        jugadores_filtrados = []
        cuenta_filtrada = None

        for p in jugadores:
            # Normaliza el nombre del jugador para comparar
            if p.name.lower().replace(" ", "") == nombre:
                jugadores_filtrados.append(p)
                break
            for acc in p.accounts:
                acc_name = acc.riot_id.get("game_name", "").lower()
                acc_tag = acc.riot_id.get("tag_line", "").lower()
                acc_str = f"{acc_name}#{acc_tag}"
                acc_str_sin_espacios = acc_str.replace(" ", "")
                if (
                    acc_name.replace(" ", "") == nombre or
                    acc_str == nombre or
                    acc_str_sin_espacios == nombre
                ):
                    jugadores_filtrados = [p]
                    cuenta_filtrada = (acc_name, acc_tag)
                    break

        if not jugadores_filtrados:
            print(f"[DEBUG] No se encontró el jugador o cuenta '{nombre}' en los datos cargados.")
            await ctx.send(f"No se encontró el jugador o cuenta '{nombre}'.")
            return

        puuid_cache = load_puuid_cache()
        msg = ""
        POS_EMOJI = {
            "TOP": "🗻",
            "JUNGLE": "🌲",
            "MID": "✨",
            "ADC": "🏹",
            "BOTTOM": "🏹",
            "SUPPORT": "🛡️",
        }

        # Si es búsqueda por cuenta específica
        if cuenta_filtrada:
            player = jugadores_filtrados[0]
            acc_name, acc_tag = cuenta_filtrada
            cuenta_str = f"{acc_name}#{acc_tag}"
            puuid_dpmlol = await get_puuid_cached(acc_name, acc_tag, puuid_cache)
            if not puuid_dpmlol:
                await loading_msg.edit(content=f"No se encontró historial para la cuenta {cuenta_str}.")
                return
            data = await get_match_history_from_dpmlol(puuid_dpmlol)
            partidas = []
            if data and "matches" in data:
                for match in data["matches"][:10]:
                    participante = next((p for p in match.get("participants", []) if p.get("puuid") == puuid_dpmlol), None)
                    if not participante:
                        continue
                    champ = participante.get("championName", "???")
                    kills = participante.get("kills", 0)
                    deaths = participante.get("deaths", 0)
                    assists = participante.get("assists", 0)
                    win = participante.get("win", False)
                    duration = match.get("gameDuration", 0)
                    mins = duration // 60
                    pos = participante.get("teamPosition", "") or participante.get("position", "")
                    if pos.upper() == "UTILITY":
                        pos = "SUPPORT"
                    pos_str = f" ({pos.title()})" if pos else ""
                    emoji = POS_EMOJI.get(pos.upper(), "") if pos else ""
                    start_ts = match.get("gameCreation")
                    hora_inicio_str = f"<t:{int(start_ts / 1000)}:f>" if isinstance(start_ts, int) else "¿?"
                    resultado = "✅" if win else "❌"
                    partidas.append(f"{resultado} **{champ}**{pos_str} {emoji} | {kills}/{deaths}/{assists} | {mins} min | 🕒 {hora_inicio_str}")
            if partidas:
                tricode = player.team.upper() if player.team else ""
                nick_str = f"{player.name} [{tricode}] ({cuenta_str})" if tricode else f"{player.name} ({cuenta_str})"
                msg += f"**Últimas partidas de {nick_str}:**\n"
                for i, linea in enumerate(partidas, 1):
                    msg += f"{i}. {linea}\n"
            else:
                msg = f"No se encontró historial para la cuenta {cuenta_str}."
            await loading_msg.edit(content=msg)
            return
        
        
        else:   # Si es búsqueda por jugador (no por cuenta específica)
            player = jugadores_filtrados[0]
            partidas_todas = []
            for account in player.accounts:
                acc_name = account.riot_id.get("game_name", "")
                acc_tag = account.riot_id.get("tag_line", "")
                cuenta_str = f"{acc_name}#{acc_tag}" if acc_name and acc_tag else ""
                puuid_dpmlol = await get_puuid_cached(acc_name, acc_tag, puuid_cache)
                if not puuid_dpmlol:
                    continue
                data = await get_match_history_from_dpmlol(puuid_dpmlol)
                if data and "matches" in data:
                    for match in data["matches"]:
                        participante = next((p for p in match.get("participants", []) if p.get("puuid") == puuid_dpmlol), None)
                        if not participante:
                            continue
                        partidas_todas.append({
                            "participante": participante,
                            "match": match,
                            "cuenta_str": cuenta_str
                        })
            # Ordena por fecha y toma las 10 últimas
            partidas_todas.sort(key=lambda x: x["match"].get("gameCreation", 0), reverse=True)
            partidas_top10 = partidas_todas[:10]
            if partidas_top10:
                solo_una_cuenta = len(player.accounts) == 1
                if solo_una_cuenta:
                    msg += f"**Últimas 10 partidas de {player.name}:**\n"
                else:
                    msg += f"**Últimas 10 partidas de {player.name} (todas sus cuentas):**\n"
                for i, partida in enumerate(partidas_top10, 1):
                    participante = partida["participante"]
                    match = partida["match"]
                    cuenta_str = partida["cuenta_str"]
                    champ = participante.get("championName", "???")
                    kills = participante.get("kills", 0)
                    deaths = participante.get("deaths", 0)
                    assists = participante.get("assists", 0)
                    win = participante.get("win", False)
                    duration = match.get("gameDuration", 0)
                    mins = duration // 60
                    pos = participante.get("teamPosition", "") or participante.get("position", "")
                    if pos.upper() == "UTILITY":
                        pos = "SUPPORT"
                    pos_str = f" ({pos.title()})" if pos else ""
                    emoji = POS_EMOJI.get(pos.upper(), "") if pos else ""
                    start_ts = match.get("gameCreation")
                    hora_inicio_str = f"<t:{int(start_ts / 1000)}:f>" if isinstance(start_ts, int) else "¿?"
                    resultado = "✅" if win else "❌"
                    if solo_una_cuenta:
                        msg += f"{i}. {resultado} **{champ}**{pos_str} {emoji} | {kills}/{deaths}/{assists} | {mins} min | 🕒 {hora_inicio_str}\n"
                    else:
                        msg += f"{i}. {resultado} **{champ}**{pos_str} {emoji} | {kills}/{deaths}/{assists} | {mins} min | 🕒 {hora_inicio_str} _(Cuenta: {cuenta_str})_\n"
            else:
                msg = f"No se encontró historial para {player.name}."
            await loading_msg.edit(content=msg)
            return
                



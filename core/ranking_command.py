#core/ranking_command.py
import nextcord
from nextcord.ext import commands
from utils.cache_utils import load_ranking_cache
from core.rank_data import build_and_cache_ranking




def register_ranking_command(bot):
    @bot.command(name="ranking")
    async def ranking(ctx):
        ranking = load_ranking_cache()
        if not ranking:
            await ctx.send("⏳ Calculando ranking, esto puede tardar unos segundos...")
            ranking = await build_and_cache_ranking()
        if not ranking:
            await ctx.send("❌ No se pudo obtener el ranking.")
            return

        embed = nextcord.Embed(
            title="📊 Ranking jugadores trackeados en SoloQ Europeo (ordenado por LP)",
            color=nextcord.Color.gold()
        )
            # Define los encabezados y extrae los datos
        headers = ["Pos", "Jugador", "Equipo", "Rol", "Rango", "LP", "Winrate", "KDA", "Best Champs"]
        rows = []
        for i, p in enumerate(ranking[:20], 1):
            name = p['player'] #name = f"{p['riot_id']['game_name']}#{p['riot_id']['tag_line']}"
            team = p['team']
            
            role_map = {
            "top": "TOP",
            "jungle": "JG",
            "mid": "MID",
            "bot": "ADC",
            "bottom": "ADC",
            "support": "SUPP"
        }
            
            
            role_value = p.get('role')
            if role_value is not None:
                role = role_map.get(role_value.lower(), role_value.upper())
                if role is not None and role.upper() == "UTILITY":
                    role = "SUPP"
            else:
                role = "UNKNOWN"

            rank = f"{p['tier'].capitalize()} {p['division'].upper()}"
            lp = str(p['lp'])
            winrate = f"{p['wins']} W - {p['losses']} L ({round(p['winrate'])}%)"
            kda = f"{p['kda']:.1f}"
            champ_abbr = {
            "TwistedFate": "Twisted F",
            "MissFortune": "Miss F",
            
            # añade más si quieres
        }

            champs = ", ".join(p['best_champions'][:2])
            rows.append([
                str(i),
                name,
                team,
                role,
                rank,
                lp,
                winrate,
                kda,
                champs
            ])

        # Calcula el ancho máximo de cada columna
        col_widths = [len(h) for h in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                col_widths[idx] = max(col_widths[idx], len(str(cell)))

        # Función para centrar texto en un ancho dado
        def center(text, width):
            text = str(text)
            if len(text) >= width:
                return text
            padding = width - len(text)
            left = padding // 2
            right = padding - left
            return " " * left + text + " " * right

        # Construye la tabla
        lines = []
        # Encabezado
        header_line = "| " + " | ".join(center(h, col_widths[i]) for i, h in enumerate(headers)) + " |"
        lines.append(header_line)
        # Separador
        sep_line = "|-" + "-|-".join("-" * col_widths[i] for i in range(len(headers))) + "-|"
        lines.append(sep_line)
        # Filas
        for row in rows:
            line = "| " + " | ".join(center(cell, col_widths[i]) for i, cell in enumerate(row)) + " |"
            lines.append(line)

        # Divide en bloques de máximo 2000 caracteres (sin cortar líneas)
        current_chunk = "```markdown\n"
        for line in lines:
            if len(current_chunk) + len(line) + 1 > 1990:  # +1 por el salto de línea final
                current_chunk += "```"
                await ctx.send(current_chunk)
                current_chunk = "```markdown\n"
            current_chunk += line + "\n"

        if current_chunk.strip() != "```markdown":
            current_chunk += "```"
            await ctx.send(current_chunk)
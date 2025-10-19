#core/info_command.py
import nextcord
from nextcord.ext import commands
from ui.player_info_embed import crear_embed_infoplayer
from tracking.soloq.infoplayers_search import buscar_jugador_o_cuenta

def register_info_command(bot: commands.Bot):
    @bot.command(name="info")
    async def info(ctx, *, nombre: str):
        print(f"[INFO] Buscando info en EU para: '{nombre}'")
        res = buscar_jugador_o_cuenta(nombre)
        if not res:
            return await ctx.send(f"❌ No se encontró información para '{nombre}'.")

        jugador = res["jugador"]
        cuentas = res["cuentas"]
        campeones_recientes = res.get("campeones_recientes", [])
        estadisticas_2_semanas = res.get("estadisticas_2_semanas", {})

        print(f"[INFO] Encontrado: {jugador.get('nombre') or jugador.get('name')}")
        try:
            embed, archivo_logo = crear_embed_infoplayer(jugador, cuentas, campeones_recientes, estadisticas_2_semanas)

            if archivo_logo:
                await ctx.send(embed=embed, file=archivo_logo)
            else:
                if embed:
                    await ctx.send(embed=embed)

            print("[INFO] Embed enviado correctamente.")
        except Exception as e:
            print(f"[✗] Error generando embed: {e}")
            await ctx.send("❌ Ocurrió un error generando el embed.")

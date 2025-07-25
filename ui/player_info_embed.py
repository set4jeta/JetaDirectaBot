# ui/player_info_embed.py
import nextcord
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from utils.cache_utils import formatear_fecha
from ui.team_image_utils import get_team_image_path
from urllib.parse import urlparse
import os

def calcular_winrate(wins, losses):
    total = wins + losses
    if total == 0:
        return "0%"
    return f"{round((wins / total) * 100)}%"

def tiempo_relativo_desde_timestamp(timestamp_ms):
    now = datetime.now(timezone.utc)
    dt = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)
    diff = relativedelta(now, dt)
    if diff.years > 0:
        return f"{diff.years} year{'s' if diff.years > 1 else ''} ago"
    if diff.months > 0:
        return f"{diff.months} month{'s' if diff.months > 1 else ''} ago"
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    if diff.hours > 0:
        return f"{diff.hours} hour{'s' if diff.hours > 1 else ''} ago"
    if diff.minutes > 0:
        return f"{diff.minutes} min ago"
    return "just now"

def extraer_tricode_desde_url(url):
    try:
        filename = os.path.basename(urlparse(url).path)  # Ej: "T1.webp"
        tricode, _ = os.path.splitext(filename)           # Extrae "T1"
        return tricode
    except Exception:
        return None

def crear_embed_infoplayer(p, cuentas=None, campeones_recientes=None, estadisticas_2_semanas=None):
    nombre = p.get("nombre", "?")
    nombre_real = p.get("nombre_real", "")
    edad = p.get("edad")
    birthday = formatear_fecha(p.get("birthdate") or p.get("birthday")) or "Desconocido"
    equipo = p.get("equipo", "Sin equipo")
    pais = p.get("pais", "Desconocido")
    contrato = formatear_fecha(p.get("contrato_hasta") or p.get("contrato")) or "Desconocido"
    redes = p.get("redes_sociales", {})
    twitter_url = redes.get("twitter")
    twitch_url = redes.get("twitch")

    imagen_jugador = p.get("imagen_jugador")
    logo_equipo = p.get("logo_equipo")

    embed = nextcord.Embed(
        title=f"{nombre} ({nombre_real})",
        description=f"Equipo: **{equipo}** | País: {pais}",
        color=nextcord.Color.blue()
    )
    embed.set_thumbnail(url=imagen_jugador or "")

    archivo_logo_equipo = None  # Aquí guardaremos el archivo local si existe

    if logo_equipo:
        tricode = extraer_tricode_desde_url(logo_equipo)
        if tricode:
            ruta_local = get_team_image_path(tricode)
            if ruta_local and os.path.exists(ruta_local):
                archivo_logo_equipo = nextcord.File(ruta_local, filename=os.path.basename(ruta_local))
                embed.set_image(url=f"attachment://{os.path.basename(ruta_local)}")
            else:
                embed.set_image(url=logo_equipo)
        else:
            embed.set_image(url=logo_equipo)

    embed.add_field(name="🎂 Nacimiento", value=birthday or "Desconocido", inline=True)
    if edad is not None:
        embed.add_field(name="👶 Edad", value=str(edad), inline=True)
    embed.add_field(name="📄 Contrato", value=contrato or "Desconocido", inline=True)

    redes_texto = []
    if twitch_url:
        redes_texto.append(f"🔗 [Twitch]({twitch_url})")
    if twitter_url:
        redes_texto.append(f"🔗 [Twitter]({twitter_url})")
    if not redes_texto:
        redes_texto.append("🙅 Sin redes públicas conocidas.")
    embed.add_field(name="Redes Sociales", value="\n".join(redes_texto), inline=False)

    cuentas_texto = []
    if cuentas:
        
        cuentas.sort(key=lambda acc: 0 if acc.get("region") == "EUW" else 1)
        
        
        for acc in cuentas:
            nombre_cuenta = acc.get("nombre") or "Desconocida"
            liga = acc.get("liga") or "Sin liga"
            lp = acc.get("lp")  # No pongo valor por defecto aquí para detectar None
            victorias = acc.get("victorias") or 0
            derrotas = acc.get("derrotas") or 0
            winrate = calcular_winrate(victorias, derrotas)
            ultima_partida = acc.get("ultima_partida")
            if isinstance(ultima_partida, (int, float)) and ultima_partida > 0:
                tiempo_ultimo = tiempo_relativo_desde_timestamp(ultima_partida)
            else:
                tiempo_ultimo = "Desconocido"

            region = acc.get("region", "Desconocida")

            # Aquí chequeamos si lp es válido para mostrarlo
            if lp is not None:
                liga_texto = f"{liga} {lp}LP"
            else:
                liga_texto = liga

            cuentas_texto.append(
                f"**{nombre_cuenta}** ({region}) — {liga_texto}\n"
                f"Victorias: {victorias}W - Derrotas: {derrotas}L ({winrate})\n"
                f"Última partida: {tiempo_ultimo}"
            )
    else:
        cuentas_texto.append("Sin cuentas registradas.")

    embed.add_field(name="🎮 Cuentas SoloQ", value="\n\n".join(cuentas_texto), inline=False)

    if campeones_recientes:
        champs_texto = []
        for champ in campeones_recientes[:3]:
            nombre_champ = champ.get("nombre", "Desconocido")
            partidas = champ.get("partidas", 0)
            victorias = champ.get("victorias", 0)
            winrate = calcular_winrate(victorias, partidas - victorias)
            kda = champ.get("kda_promedio", 0)
            champs_texto.append(
                f"**{nombre_champ}** — {victorias}W-{partidas - victorias}L ({winrate}) | KDA Promedio: {kda:.2f}"
            )
        embed.add_field(name="🔥 Campeones recientes", value="\n".join(champs_texto), inline=False)

    if estadisticas_2_semanas:
        games = estadisticas_2_semanas.get("games") or 0
        wins = estadisticas_2_semanas.get("wins") or 0
        losses = estadisticas_2_semanas.get("losses") or 0
        time_played_s = estadisticas_2_semanas.get("timePlayed") or 0
        winrate_2s = calcular_winrate(wins, losses)

        horas = time_played_s // 3600
        minutos = (time_played_s % 3600) // 60
        tiempo_jugado = f"{horas}h {minutos}m" if horas > 0 else f"{minutos}m"

        embed.add_field(
            name=f"📊 Estadísticas últimas 2 semanas",
            value=f"{wins}W - {losses}L ({winrate_2s})\nTiempo jugado: {tiempo_jugado}",
            inline=False
        )

    return embed, archivo_logo_equipo  # Devuelve embed y archivo local si hay

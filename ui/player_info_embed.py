# ui/player_info_embed.py
"""Ficha de un jugador profesional (`/info`).

Sobre el idioma
---------------
`crear_embed_infoplayer(..., idioma=...)` monta la ficha en el idioma que se le
pida y cae al español si no se le pide ninguno, igual que el embed de partida.
Antes estaba en español a pelo, así que un servidor con `/lang en` veía
«Victorias: 12W - Derrotas: 3L».

Un detalle que ya venía torcido: el tiempo relativo («3 days ago») **estaba en
inglés también en la versión española**, porque se construía a mano con un
condicional dentro de la f-string. Se ha traducido por clave —una para singular
y otra para plural, que es lo que ese condicional hacía— pero el valor español
se ha dejado como estaba: esto es un refactor y la salida en español no debe
cambiar. Corregirlo es una decisión aparte.
"""
import nextcord
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from utils.cache_utils import formatear_fecha
from ui.team_image_utils import get_team_image_path
from urllib.parse import urlparse
from utils.i18n import t
import os

def calcular_winrate(wins, losses):
    total = wins + losses
    if total == 0:
        return "0%"
    return f"{round((wins / total) * 100)}%"

def tiempo_relativo_desde_timestamp(timestamp_ms, idioma=None):
    now = datetime.now(timezone.utc)
    dt = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)
    diff = relativedelta(now, dt)
    # Singular y plural son claves distintas: el `'s' if n > 1 else ''` de antes
    # no se puede expresar en una sola plantilla.
    if diff.years > 0:
        clave = "info.hace_anios" if diff.years > 1 else "info.hace_anio"
        return t(clave, idioma, n=diff.years)
    if diff.months > 0:
        clave = "info.hace_meses" if diff.months > 1 else "info.hace_mes"
        return t(clave, idioma, n=diff.months)
    if diff.days > 0:
        clave = "info.hace_dias" if diff.days > 1 else "info.hace_dia"
        return t(clave, idioma, n=diff.days)
    if diff.hours > 0:
        clave = "info.hace_horas" if diff.hours > 1 else "info.hace_hora"
        return t(clave, idioma, n=diff.hours)
    if diff.minutes > 0:
        return t("info.hace_min", idioma, n=diff.minutes)
    return t("info.ahora_mismo", idioma)

def extraer_tricode_desde_url(url):
    try:
        filename = os.path.basename(urlparse(url).path)  # Ej: "T1.webp"
        tricode, _ = os.path.splitext(filename)           # Extrae "T1"
        return tricode
    except Exception:
        return None

def crear_embed_infoplayer(p, cuentas=None, campeones_recientes=None, estadisticas_2_semanas=None, idioma=None):
    def _(clave, **kw):
        """Atajo local: traduce con el idioma de esta ficha."""
        return t(clave, idioma, **kw)

    nombre = p.get("nombre", "?")
    nombre_real = p.get("nombre_real", "")
    edad = p.get("edad")
    birthday = formatear_fecha(p.get("birthdate") or p.get("birthday")) or _("info.desconocido")
    equipo = p.get("equipo", _("info.sin_equipo"))
    pais = p.get("pais", _("info.desconocido"))
    contrato = formatear_fecha(p.get("contrato_hasta") or p.get("contrato")) or _("info.desconocido")
    redes = p.get("redes_sociales", {})
    twitter_url = redes.get("twitter")
    twitch_url = redes.get("twitch")

    imagen_jugador = p.get("imagen_jugador")
    logo_equipo = p.get("logo_equipo")

    embed = nextcord.Embed(
        title=f"{nombre} ({nombre_real})",
        description=_("info.embed_descripcion", equipo=equipo, pais=pais),
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

    embed.add_field(name=_("info.campo_nacimiento"), value=birthday or _("info.desconocido"), inline=True)
    if edad is not None:
        embed.add_field(name=_("info.campo_edad"), value=str(edad), inline=True)
    embed.add_field(name=_("info.campo_contrato"), value=contrato or _("info.desconocido"), inline=True)

    redes_texto = []
    if twitch_url:
        redes_texto.append(f"🔗 [Twitch]({twitch_url})")
    if twitter_url:
        redes_texto.append(f"🔗 [Twitter]({twitter_url})")
    if not redes_texto:
        redes_texto.append(_("info.sin_redes"))
    embed.add_field(name=_("info.campo_redes"), value="\n".join(redes_texto), inline=False)

    cuentas_texto = []
    if cuentas:
        
        cuentas.sort(key=lambda acc: 0 if acc.get("region") == "EUW" else 1)
        
        
        for acc in cuentas:
            nombre_cuenta = acc.get("nombre") or _("info.desconocida")
            liga = acc.get("liga") or _("info.sin_liga")
            lp = acc.get("lp")  # No pongo valor por defecto aquí para detectar None
            victorias = acc.get("victorias") or 0
            derrotas = acc.get("derrotas") or 0
            winrate = calcular_winrate(victorias, derrotas)
            ultima_partida = acc.get("ultima_partida")
            if isinstance(ultima_partida, (int, float)) and ultima_partida > 0:
                tiempo_ultimo = tiempo_relativo_desde_timestamp(ultima_partida, idioma)
            else:
                tiempo_ultimo = _("info.desconocido")

            region = acc.get("region", _("info.desconocida"))

            # Aquí chequeamos si lp es válido para mostrarlo
            if lp is not None:
                liga_texto = f"{liga} {lp}LP"
            else:
                liga_texto = liga

            cuentas_texto.append(
                _("info.cuenta_cabecera", cuenta=nombre_cuenta, region=region,
                  liga=liga_texto) + "\n"
                + _("info.cuenta_balance", victorias=victorias, derrotas=derrotas,
                    winrate=winrate) + "\n"
                + _("info.cuenta_ultima", tiempo=tiempo_ultimo)
            )
    else:
        cuentas_texto.append(_("info.sin_cuentas"))

    embed.add_field(name=_("info.campo_cuentas"), value="\n\n".join(cuentas_texto), inline=False)

    if campeones_recientes:
        champs_texto = []
        for champ in campeones_recientes[:3]:
            nombre_champ = champ.get("nombre", _("info.desconocido"))
            partidas = champ.get("partidas", 0)
            victorias = champ.get("victorias", 0)
            winrate = calcular_winrate(victorias, partidas - victorias)
            kda = champ.get("kda_promedio", 0)
            champs_texto.append(
                _("info.champ_linea", campeon=nombre_champ, victorias=victorias,
                  derrotas=partidas - victorias, winrate=winrate, kda=f"{kda:.2f}")
            )
        embed.add_field(name=_("info.campo_champs"), value="\n".join(champs_texto), inline=False)

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
            name=_("info.campo_stats"),
            value=_("info.stats_valor", victorias=wins, derrotas=losses,
                    winrate=winrate_2s, tiempo=tiempo_jugado),
            inline=False
        )

    return embed, archivo_logo_equipo  # Devuelve embed y archivo local si hay

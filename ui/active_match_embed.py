#ui/active_match_embed.py
"""Embed de una partida en curso.

Sobre el idioma
---------------
`create_match_embed(..., idioma=...)` construye el embed en el idioma que se le
pida y cae al español si no se le pide ninguno. Esto era lo último que quedaba
en español a pelo, y es la superficie más visible del bot: se publica sola en el
canal cada vez que un pro entra en partida, así que un servidor en inglés veía
«está jugando!» aunque tuviera `/lang en` puesto.

El notificador automático lo llama **una vez por idioma** en uso, no una por
servidor: dos servidores en inglés comparten el mismo embed.
"""
import os
import nextcord
from typing import Optional
from utils.constants import TEAM_TRICODES, ROLE_ORDER, nombre_cola
from utils.game_clock import desde_partida, humano, mmss
from utils.helpers import parse_ranked_data
from cache.champion_cache import CHAMPION_ID_TO_NAME
from utils.spectate_bat import generar_bat_spectate
from models.soloq_match import SoloQMatch, SoloQParticipant
from apis.dpm_api import get_rank_from_dpmlol
from ui.player_image_utils import get_player_image_path
from ui.team_image_utils import get_team_image_path
from utils.branding import sellar_embed
from utils.i18n import t
from utils.role_assigner import assign_roles
from utils.logger import get_logger
from tracking.soloq.accounts_io import load_accounts_cached, load_tracked_accounts

log = get_logger("ui.active_match_embed")


def _clave_riot_id(riot_id) -> str:
    """Clave normalizada 'gametag' para comparar cuentas sin depender del PUUID."""
    game_name, tag_line = extract_game_and_tag(riot_id)
    if not game_name:
        return ""
    return f"{game_name}#{tag_line}".replace(" ", "").lower()


def resolver_participante(p, tracked_puuid_to_player, all_puuid_to_player,
                          tracked_riot_to_player, all_riot_to_player):
    """Devuelve (nombre_a_mostrar, jugador, es_trackeado).

    El orden de búsqueda es: trackeado por PUUID, trackeado por riot_id,
    conocido por PUUID, conocido por riot_id. Si nada coincide devuelve
    (None, None, False) y el participante se muestra con su nick de Riot.

    Todos los jugadores conocidos salen en negrita, no solo los trackeados:
    antes los que venían de accounts.json se quedaban sin marcar y no se
    distinguían del resto de la partida.
    """
    jugador = tracked_puuid_to_player.get(p.puuid)
    if jugador:
        return jugador, jugador, True

    clave = _clave_riot_id(p.riot_id)
    if clave and clave in tracked_riot_to_player:
        jugador = tracked_riot_to_player[clave]
        return jugador, jugador, True

    jugador = all_puuid_to_player.get(p.puuid)
    if jugador:
        return jugador, jugador, False

    if clave and clave in all_riot_to_player:
        jugador = all_riot_to_player[clave]
        return jugador, jugador, False

    return None, None, False


def linea_participante(p, tracked_puuid_to_player, all_puuid_to_player,
                       tracked_riot_to_player, all_riot_to_player):
    """Línea del embed para un participante: `**Caps [G2]** (Syndra)`."""
    champ_id = p.champion_id
    champ_name = p.champion_name or CHAMPION_ID_TO_NAME.get(str(champ_id), f"ID {champ_id}")

    jugador, _, _trackeado = resolver_participante(
        p, tracked_puuid_to_player, all_puuid_to_player,
        tracked_riot_to_player, all_riot_to_player,
    )

    if jugador:
        equipo = f" [{jugador.team.upper()}]" if getattr(jugador, "team", None) else ""
        # En negrita siempre que se le conozca, esté o no en un equipo seguido:
        # antes los que venían de accounts.json se quedaban sin marcar.
        return f"**{jugador.name}{equipo}** ({champ_name})"

    game_name, tag_line = extract_game_and_tag(p.riot_id)
    return f"{game_name}#{tag_line} ({champ_name})"


def extract_game_and_tag(riot_id):
    if isinstance(riot_id, dict):
        game_name = riot_id.get("game_name") or ""
        tag_line = riot_id.get("tag_line") or ""
    else:
        riot_str = str(riot_id)
        if "#" in riot_str:
            game_name, tag_line = riot_str.split("#", 1)
        else:
            game_name = riot_str
            tag_line = ""
    return game_name, tag_line

async def create_match_embed(
    match: SoloQMatch,
    puuid_to_player: dict,
    ranked_data_map: Optional[dict] = None,
    idioma: Optional[str] = None,
) -> tuple[nextcord.Embed, list[nextcord.File]]:
    participants = match.participants
    participants = assign_roles(participants, puuid_to_player)

    def _(clave: str, **kw) -> str:
        """Atajo local: traduce con el idioma de este embed."""
        return t(clave, idioma, **kw)

    # Cargar jugadores de accounts_from_teams.json (trackeados)
    tracked_players = load_tracked_accounts()
    tracked_puuid_to_player = {
        acc.puuid: player
        for player in tracked_players
        for acc in player.accounts
        if acc.puuid
    }

    # Cargar jugadores de accounts.json (no trackeados)
    all_players = load_accounts_cached()
    all_puuid_to_player = {
        acc.puuid: player
        for player in all_players
        for acc in player.accounts
        if acc.puuid
    }

    # Además del PUUID se indexa por riot_id. Un jugador al que le falte el
    # PUUID, o que lo tenga desactualizado, se seguía quedando sin reconocer
    # aunque su cuenta estuviera en la base de datos.
    tracked_riot_to_player = {}
    for player in tracked_players:
        for acc in player.accounts:
            clave = _clave_riot_id(acc.riot_id)
            if clave:
                tracked_riot_to_player.setdefault(clave, player)

    all_riot_to_player = {}
    for player in all_players:
        for acc in player.accounts:
            clave = _clave_riot_id(acc.riot_id)
            if clave:
                all_riot_to_player.setdefault(clave, player)





    files: list[nextcord.File] = []

    # Jugadores del bot en la partida (los que están en puuid_to_player)
    bot_players_in_game = [p for p in participants if p.puuid in puuid_to_player]
    displays = []
    for p in bot_players_in_game:
        game_name, tag_line = extract_game_and_tag(p.riot_id)
        player_name = puuid_to_player[p.puuid].name
        displays.append(f"{player_name} ({game_name}#{tag_line})")

        # Título dinámico
    if not bot_players_in_game:
        title = _("partida.sin_seguidos")
        team_line = ""
    else:
        jugadores_display = []
        for p in bot_players_in_game:
            game_name, tag_line = extract_game_and_tag(p.riot_id)
            player_name = puuid_to_player[p.puuid].name
            jugadores_display.append(f"{player_name} ({game_name}#{tag_line})")

        # La lista se arma aparte del verbo porque en inglés cambia el número:
        # "X is in game" contra "X and Y are in game".
        y = _("partida.y")
        if len(jugadores_display) == 1:
            lista = jugadores_display[0]
            title = _("partida.titulo_uno", jugadores=lista)
        else:
            if len(jugadores_display) == 2:
                lista = f"{jugadores_display[0]} {y} {jugadores_display[1]}"
            else:
                lista = f"{', '.join(jugadores_display[:-1])} {y} {jugadores_display[-1]}"
            title = _("partida.titulo_varios", jugadores=lista)

        # Aún usamos el primero para sacar el nombre del equipo
        main_player = bot_players_in_game[0]
        player_obj = puuid_to_player[main_player.puuid]
        team_full_name = player_obj.team_name or ""
        team_line = _("partida.equipo", equipo=team_full_name) + "\n" if team_full_name else ""


    # Cola y modo
    queue_id = match.game_queue if isinstance(match.game_queue, int) else match.datos_extra.get("gameQueueConfigId")
    queue_name = nombre_cola(queue_id, idioma)
    game_mode = match.game_mode or match.datos_extra.get("gameMode") or _("partida.desconocido")
    game_start_time = match.game_start_time

    # Tiempo transcurrido y delay del espectador.
    # Antes se pintaba `game_length` a pelo, que es el reloj del servidor de
    # espectadores: va unos 3 minutos por detrás y arranca en negativo, así que
    # una partida recién detectada mostraba un tiempo que no correspondía con
    # nada. `game_clock` separa el tiempo real del tiempo visible.
    reloj = desde_partida(match.datos_extra)
    tiempo_str = reloj.texto_embed(idioma)

    # Hora de inicio
    if isinstance(game_start_time, int) and game_start_time > 0:
        timestamp = int(game_start_time / 1000)
        fecha_inicio_str = f"<t:{timestamp}:F>"
    else:
        # `gameStartTime` vale 0 mientras la partida está en pantalla de carga.
        fecha_inicio_str = _("partida.en_carga")

    desc = "\n".join([
        _("partida.cola", cola=queue_name),
        _("partida.modo", modo=game_mode),
        _("partida.transcurrido", tiempo=tiempo_str),
        _("partida.hora_inicio", hora=fecha_inicio_str),
    ])
    desc = team_line + desc
    aviso = reloj.aviso_delay(idioma)
    if aviso:
        desc += f"\n\n{aviso}"

    embed = nextcord.Embed(
        title=title,
        description=desc,
        color=nextcord.Color.red()
    )
    
    main_player = bot_players_in_game[0] if bot_players_in_game else None
    
    if main_player:
        player_obj = puuid_to_player[main_player.puuid]
        img_path = get_player_image_path(player_obj.name)
        if img_path:
            filename = f'{player_obj.name.lower().replace(" ", "").replace("\'", "").replace(".", "")}.webp'
            embed.set_thumbnail(url=f"attachment://{filename}")
            files.append(nextcord.File(img_path, filename=filename))


                # --- LOGO DEL EQUIPO COMO MAIN IMAGE ---
        team_tricode = player_obj.team.upper() if player_obj.team else ""
        team_img_path = get_team_image_path(team_tricode)
        if team_img_path:
            embed.set_image(url=f"attachment://{team_tricode}.webp")
            files.append(nextcord.File(team_img_path, filename=f"{team_tricode}.webp"))







    # Tabla horizontal: Champion | Account | Rank (solo jugadores del bot)
    champion_row = []
    account_row = []
    rank_row = []

    for p in bot_players_in_game:
        champ_id = p.champion_id
        champ_name = p.champion_name or CHAMPION_ID_TO_NAME.get(str(champ_id), "?")

        game_name, tag_line = extract_game_and_tag(p.riot_id)

        display = f"{game_name}#{tag_line}"
        if len(display) > 22:
            display = display[:19] + "..."

        if ranked_data_map and p.puuid in ranked_data_map:
            rank = ranked_data_map[p.puuid]
        else:
            rank = None
        if rank and rank.get("tier") and rank.get("lp") is not None:
            tier = rank.get("tier", "Unranked").capitalize()
            div = rank.get("division", "")
            lp = rank.get("lp", 0)
            rank_str = f"{tier} {div} ({lp} LP)"
        else:
            log.debug("Sin rango para %s#%s: %s", game_name, tag_line, rank)
            rank_str = _("partida.sin_rango")

        champion_row.append(champ_name)
        account_row.append(display)
        rank_row.append(rank_str)

    if champion_row:
        # Las cabeceras van traducidas pero el ancho de columna se mantiene fijo:
        # es un bloque de código monoespaciado y "Campeón"/"Champion" caben los
        # dos en 10, así que la tabla no se descuadra al cambiar de idioma.
        col_champ = _("partida.col_campeon")[:10]
        col_acc = _("partida.col_cuenta")[:16]
        table1_lines = [
            f"{col_champ:<10} | {col_acc:<16}",
            "-" * 29
        ]
        for champ, acc in zip(champion_row, account_row):
            champ_txt = champ[:10]
            acc_txt = acc[:16]
            table1_lines.append(f"{champ_txt:<10} | {acc_txt:<16}")

        table2_lines = [_("partida.col_rango"), "-" * 16]
        for rank in rank_row:
            table2_lines.append(rank)

        embed.add_field(
            name=_("partida.jugadores_seguidos"),
            value="```\n" + "\n".join(table1_lines) + "\n```",
            inline=False
        )
        embed.add_field(
            name="",
            value="```\n" + "\n".join(table2_lines) + "\n```",
            inline=False
        )


    
    # Separar jugadores por equipo
    blue_team = [p for p in participants if p.team_id == 100]
    red_team = [p for p in participants if p.team_id == 200]

    # Ordenar cada equipo por rol según ROLE_ORDER
    blue_team.sort(key=lambda p: ROLE_ORDER.get(p.role or "", 99))
    red_team.sort(key=lambda p: ROLE_ORDER.get(p.role or "", 99))

    # Crear listas para mostrar en embed con formato.
    # Antes este bloque estaba duplicado (una copia para cada equipo) y solo
    # marcaba en negrita a los trackeados.
    mapas = (
        tracked_puuid_to_player, all_puuid_to_player,
        tracked_riot_to_player, all_riot_to_player,
    )
    blue_side = [linea_participante(p, *mapas) for p in blue_team]
    red_side = [linea_participante(p, *mapas) for p in red_team]
    vacio = _("partida.sin_jugadores")

    if red_side:
        embed.add_field(name=_("partida.lado_azul"),
                        value="\n".join(blue_side) or vacio, inline=False)
        embed.add_field(name=_("partida.lado_rojo"),
                        value="\n".join(red_side) or vacio, inline=False)
    else:
        # Arena manda los 18 jugadores con `teamId` 100, así que salía un
        # "🔵 Blue Team" con 18 nombres y un "🔴 Red Team — No players".
        embed.add_field(
            name=_("partida.jugadores_n", n=len(blue_side)),
            value="\n".join(blue_side) or vacio,
            inline=False,
        )


    # Espectate .bat
    
    game_id = match.game_id
    platform_id = match.datos_extra.get("platformId") if hasattr(match, "datos_extra") else None
    encryption_key = match.datos_extra.get("observers", {}).get("encryptionKey") if hasattr(match, "datos_extra") else None
    if game_id and platform_id and encryption_key:
        bat_path = generar_bat_spectate(
            server=f"spectator.{platform_id.lower()}.lol.pvp.net:8080",
            key=encryption_key,
            match_id=game_id,
            region=platform_id
        )
        files.append(nextcord.File(bat_path, filename="spectate_lol.bat"))

        valor_espectar = _("partida.espectar_bat")
        # Ejecutar el .bat antes de que pase el delay deja el cliente esperando
        # sin imagen, y parecía un fallo del bot. Ahora se avisa.
        if not reloj.espectable:
            valor_espectar = _(
                "partida.espectar_espera",
                falta=humano(reloj.falta_para_espectar, idioma),
                reloj=mmss(-reloj.falta_para_espectar, con_signo=True),
            ) + "\n\n" + valor_espectar

        embed.add_field(name=_("partida.espectar"), value=valor_espectar, inline=False)
        embed.add_field(
            name=_("partida.info_titulo"),
            value=_("partida.info_valor"),
            inline=False
        )
    else:
        embed.add_field(
            name=_("partida.espectar"),
            value=_("partida.espectar_no"),
            inline=False
        )

    # El descargo de Riot va en el pie y se pone al final, después de todos los
    # `add_field`: la política pide que esté "readily visible to players" y este
    # embed es la superficie que más se ve, porque se publica sola en el canal
    # cada vez que un pro entra en cola. Va la versión corta a propósito; la
    # completa está en `/help` y en la web.
    sellar_embed(embed, idioma)

    return embed, files

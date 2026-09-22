"""Resumen de arranque en la consola.

Por qué existe
--------------
El usuario lo pidió tal cual: *"que cuando abra la consola del bot esté todo
claro"*. Lo que había era una sola línea, `"Bot conectado como %s"`, y para
saber si el bot estaba realmente operativo había que ir a Discord y probar.

Tres preguntas que la consola no contestaba y ahora sí:

1. **¿Están todos los comandos?** Un fallo de importación en un módulo de
   comandos no impide arrancar: el bot conecta y simplemente le faltan
   comandos. Antes eso solo se veía escribiendo `/` en Discord.
2. **¿A quién está vigilando?** Un `accounts.json` vacío o a medias deja el bot
   vivo y sin seguir a nadie. Es el fallo silencioso que el usuario avisó de
   evitar: *"ojo con eso no me vayas a estar tomando data y despues se rompa"*.
3. **¿Qué tareas están corriendo y cada cuánto?** El intervalo real sale de
   `config`/entorno, así que leerlo del código no sirve.

Se imprime **una sola vez**, en `on_ready`, y en `INFO`: es lo primero que se ve
al abrir la consola y no se repite en cada reconexión.
"""

from __future__ import annotations

import nextcord
from nextcord.ext import commands

import config
from utils.logger import get_logger

log = get_logger("core.arranque")

ANCHO = 66

#: Lo que el bot necesita para funcionar de verdad en un canal. Si falta alguno,
#: los comandos responden a medias o no responden, y conviene decirlo aquí en vez
#: de dejar que el usuario lo descubra con un comando que no contesta.
PERMISOS_NECESARIOS = (
    ("Enviar mensajes", "send_messages"),
    ("Insertar enlaces", "embed_links"),
    ("Adjuntar archivos", "attach_files"),
    ("Usar comandos de aplicación", "use_slash_commands"),
)

_ya_mostrado = False


def _linea(texto: str = "") -> str:
    return texto


def _titulo(texto: str) -> list[str]:
    return ["", texto, "-" * len(texto)]


def _comandos(bot: commands.Bot) -> list[str]:
    """Comandos registrados, en las dos formas, contados y listados.

    Sobre el cotejo slash/prefijo
    -----------------------------
    `get_application_commands()` **sin** `rollout` solo devuelve los comandos que
    ya tienen id de Discord, y ese id llega uno a uno, a lo largo de ~45 s
    después de conectar (`Registering command with signature (...)` en el log).
    `on_ready` se dispara mucho antes, así que preguntarlo ahí daba 0 y el banner
    avisaba de "sin forma slash: help, historial, ..." **mientras la línea de
    arriba listaba los 15**. Se contradecía a sí mismo en pantalla.

    `rollout=True` lee `state._application_commands`, que ya está lleno: lo
    rellena `Client.on_connect` con `add_all_application_commands()` antes de
    empezar a hablar con Discord. Verificado sin red: 0 sin rollout, 15 con él.
    """
    prefijo = sorted({c.name for c in bot.commands})

    slash = sorted(
        {
            c.name
            for c in bot.get_application_commands(rollout=True)
            if isinstance(c, nextcord.SlashApplicationCommand)
        }
    )
    if not slash:
        # Fuera de `on_ready` (p. ej. inspección offline) el estado está vacío y
        # los comandos siguen en la lista de pendientes del cliente.
        slash = sorted(
            {
                c.name
                for c in (getattr(bot, "_application_commands_to_add", None) or [])
                if getattr(c, "name", None)
            }
        )

    lineas = [f"  {len(prefijo)} comandos, disponibles como /nombre y !nombre:"]
    # De 4 en 4 para que quepa en una consola estrecha sin recortar nombres.
    for i in range(0, len(prefijo), 4):
        lineas.append("    " + "  ".join(f"/{n}" for n in prefijo[i : i + 4]))

    solo_prefijo = set(prefijo) - set(slash)
    solo_slash = set(slash) - set(prefijo)
    if solo_prefijo:
        lineas.append(
            f"  ⚠️ sin forma slash: {', '.join(sorted(solo_prefijo))}"
        )
    if solo_slash:
        lineas.append(
            f"  ⚠️ sin forma de prefijo: {', '.join(sorted(solo_slash))}"
        )
    if not solo_prefijo and not solo_slash:
        lineas.append("  ✔ las dos formas coinciden")
    return lineas


def _seguimiento() -> list[str]:
    """A cuánta gente está vigilando el bot. Un 0 aquí es una avería."""
    try:
        from utils.load_accounts import load_all_accounts

        jugadores = load_all_accounts()
    except Exception:
        log.exception("No se pudieron leer las cuentas seguidas.")
        return ["  ❌ no se pudo leer accounts.json / accounts_from_teams.json"]

    cuentas = [c for j in jugadores for c in (j.get("accounts") or [])]
    con_puuid = sum(1 for c in cuentas if c.get("puuid"))
    equipos = {j.get("team") for j in jugadores if j.get("team")}

    if not jugadores:
        return [
            "  ❌ 0 jugadores: el bot no está vigilando a nadie.",
            "     Revisa la descarga de dpm.lol (tarea 'Plantillas y cuentas').",
        ]

    lineas = [
        f"  {len(jugadores)} jugadores · {len(cuentas)} cuentas · "
        f"{len(equipos)} equipos"
    ]
    if con_puuid < len(cuentas):
        faltan = len(cuentas) - con_puuid
        lineas.append(
            f"  ⚠️ {faltan} cuenta(s) sin PUUID: no se pueden consultar en Riot "
            "hasta que la tarea de reparación las resuelva."
        )
    return lineas


def _tareas() -> list[str]:
    """Tareas de fondo con su cadencia real y si están corriendo."""
    from core import background_tasks as bg

    definicion = (
        ("Partidas SoloQ en curso", bg.check_games_loop, f"{bg.CHECK_INTERVAL}s"),
        ("Reparación de PUUIDs", bg.actualizar_puuids_periodico, "6 h"),
        ("Plantillas y cuentas", bg.actualizar_accounts_diario, "24 h"),
        ("Pickrates por línea", bg.actualizar_pickrates_semanal, "7 d"),
        ("Infoplayers", bg.actualizar_infoplayers_por_lotes, "1 h"),
        (
            "Historial precalentado",
            bg.precalentar_historial,
            f"{config.HISTORIAL_WARM_INTERVAL}s" if config.HISTORIAL_WARM else None,
        ),
        (
            "Rangos precalentados",
            bg.refrescar_rangos,
            f"{config.RANK_WARM_INTERVAL}s" if config.RANK_WARM else None,
        ),
    )

    lineas = []
    for nombre, loop, cadencia in definicion:
        if cadencia is None:
            lineas.append(f"  ⚪ {nombre:<24} desactivada por configuración")
        elif loop.is_running():
            lineas.append(f"  🟢 {nombre:<24} cada {cadencia}")
        else:
            lineas.append(f"  🔴 {nombre:<24} DETENIDA (debería ir cada {cadencia})")
    return lineas


def _servidores(bot: commands.Bot) -> list[str]:
    """Servidores, canales de notificación y permisos que falten."""
    from esports_extension.services.storage import load_notification_channel
    from tracking.soloq.channel_config import load_channel_ids

    try:
        canales_soloq = load_channel_ids()
    except Exception:
        log.exception("No se pudo leer la configuración de canales de SoloQ.")
        canales_soloq = {}

    lineas = [f"  {len(bot.guilds)} servidor(es)"]
    if not bot.guilds:
        lineas.append("  ⚠️ el bot no está en ningún servidor todavía.")
        return lineas

    # Se listan como máximo 10: con el bot en muchos servidores esto se
    # convertiría en el bloque más largo del arranque y taparía lo demás.
    for guild in list(bot.guilds)[:10]:
        soloq = canales_soloq.get(guild.id)
        try:
            esports = load_notification_channel(guild.id)
        except Exception:
            esports = None

        avisos = []
        if not soloq:
            avisos.append("SoloQ sin canal (/setchannel)")
        if not esports:
            avisos.append("esports sin canal (/setlivechannel)")

        # Permisos: se comprueban en el canal configurado, que es donde el bot
        # tiene que poder escribir sin que nadie se lo pida.
        for etiqueta, canal_id in (("SoloQ", soloq), ("esports", esports)):
            if not canal_id:
                continue
            canal = bot.get_channel(canal_id)
            if canal is None:
                avisos.append(f"el canal de {etiqueta} ya no existe")
                continue
            if guild.me is None:
                continue
            permisos = canal.permissions_for(guild.me)
            faltan = [
                nombre
                for nombre, attr in PERMISOS_NECESARIOS
                if not getattr(permisos, attr, True)
            ]
            if faltan:
                avisos.append(f"en {etiqueta} faltan: {', '.join(faltan)}")

        marca = "⚠️" if avisos else "✔"
        lineas.append(f"  {marca} {guild.name}")
        for aviso in avisos:
            lineas.append(f"      · {aviso}")

    if len(bot.guilds) > 10:
        lineas.append(f"  ... y {len(bot.guilds) - 10} más")
    return lineas


def construir(bot: commands.Bot) -> str:
    """El texto completo del resumen. Aparte para poder verlo sin conectar."""
    partes: list[str] = ["", "=" * ANCHO, "  JetaDirectaBot — listo", "=" * ANCHO]

    if bot.user is not None:
        partes.append(f"  Cuenta: {bot.user} (id {bot.user.id})")
    partes.append(f"  Nivel de log: {config.LOG_LEVEL}")

    partes += _titulo("COMANDOS") + _comandos(bot)
    partes += _titulo("SEGUIMIENTO") + _seguimiento()
    partes += _titulo("TAREAS AUTOMÁTICAS") + _tareas()
    partes += _titulo("SERVIDORES") + _servidores(bot)
    partes += [
        "",
        "  Estado en vivo de las fuentes de datos: /health",
        "=" * ANCHO,
    ]
    return "\n".join(partes)


def mostrar(bot: commands.Bot) -> None:
    """Imprime el resumen una sola vez por proceso.

    `on_ready` se dispara también en cada reconexión (Discord corta la sesión
    cada pocas horas), y repetir 40 líneas cada vez sería exactamente el ruido
    que se está intentando quitar.
    """
    global _ya_mostrado
    if _ya_mostrado:
        log.info("Reconectado como %s.", bot.user)
        return
    _ya_mostrado = True

    try:
        for linea in construir(bot).split("\n"):
            log.info("%s", linea)
    except Exception:
        # Un resumen que revienta el arranque sería peor que no tenerlo.
        log.exception("No se pudo construir el resumen de arranque.")
        log.info("Bot conectado como %s", bot.user)

"""`!health` / `/health` — estado del bot y de sus fuentes de datos.

Por qué existe
--------------
El bot **nunca dice que algo va mal**. Cuando dpm.lol deja de responder o Riot
devuelve 403 con una clave caducada, los comandos siguen contestando con lo
último que hay en disco: eso es lo correcto, pero significa que una avería puede
durar días sin que nadie lo note. El usuario lo pidió explícitamente: *"ojo con
eso no me vayas a estar tomando data y despues se rompa"*.

Este comando responde a tres preguntas concretas:

1. ¿Cada fuente ha funcionado la última vez que se intentó, y cuándo fue eso?
2. ¿Cuántos jugadores y cuentas está siguiendo el bot ahora mismo? Un 0 aquí
   significa que el bot parece vivo y no está vigilando nada.
3. ¿Están corriendo las tareas de fondo? Una tarea que muere por una excepción
   no vuelve, y hasta ahora eso solo se veía leyendo el log.

Es público a propósito: cualquiera que use el bot puede comprobar si los datos
que ve son de hace 5 minutos o de hace tres días. Y justo por eso los textos
pasan por `utils.i18n`: lo lee cualquiera del servidor, no solo el dueño. El
`detalle` de cada fuente sigue en español porque lo escribe la tarea que falló;
es un dato de operador que se cuela aquí.
"""

from __future__ import annotations

import time

import nextcord
from nextcord.ext import commands

import config
from core import health as salud
from core.dual_command import dual
from core.responder import Respuesta
from utils.i18n import idioma_de, tr
from utils.logger import get_logger

log = get_logger("core.health_cmd")

_ARRANQUE = time.time()


def _tiempo_encendido(idioma: str | None = None) -> str:
    from utils.i18n import t

    segundos = int(time.time() - _ARRANQUE)
    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    if dias:
        return t("health.uptime_dias", idioma, dias=dias, horas=horas)
    if horas:
        return t("health.uptime_horas", idioma, horas=horas, minutos=minutos)
    return t("health.uptime_minutos", idioma, minutos=minutos)


def _resumen_seguimiento(idioma: str | None = None) -> tuple[str, bool]:
    """Cuántos jugadores y cuentas se siguen. El bool es "esto está bien".

    Ojo con la forma del dato: el PUUID **no** está en el jugador, está en cada
    cuenta suya (`jugador["accounts"][i]["puuid"]`). Un jugador puede tener
    varias cuentas y el bot vigila todas.
    """
    from utils.i18n import t

    try:
        from utils.load_accounts import load_all_accounts

        jugadores = load_all_accounts()
        cuentas = [c for j in jugadores for c in (j.get("accounts") or [])]
        con_puuid = sum(1 for c in cuentas if c.get("puuid"))
        equipos = {j.get("team") for j in jugadores if j.get("team")}
        sin_cuenta = sum(1 for j in jugadores if not (j.get("accounts") or []))
    except Exception:
        log.exception("No se pudo contar las cuentas seguidas.")
        return t("health.cuentas_ilegibles", idioma), False

    if not jugadores:
        return t("health.cero_jugadores", idioma), False
    if not cuentas:
        return t("health.cero_cuentas", idioma, jugadores=len(jugadores)), False

    avisos = []
    if con_puuid < len(cuentas):
        # Sin PUUID una cuenta no se puede consultar en Riot: está muerta hasta
        # que la tarea de reparación la resuelva.
        avisos.append(t("health.sin_puuid", idioma, n=len(cuentas) - con_puuid))
    if sin_cuenta:
        avisos.append(t("health.jugadores_sin_cuenta", idioma, n=sin_cuenta))

    cola = ("\n" + " · ".join(avisos)) if avisos else ""
    return (
        t("health.resumen", idioma, jugadores=len(jugadores),
          cuentas=len(cuentas), equipos=len(equipos)) + cola,
        True,
    )


def _estado_tareas(idioma: str | None = None) -> list[str]:
    """Una línea por tarea de fondo, con su intervalo y si está corriendo."""
    from core import background_tasks as bg
    from utils.i18n import t

    # La cadencia se compone por clave y no con una f-string: "cada 6 h" en
    # inglés es "every 6 h", y el número tiene que quedar dentro de la
    # plantilla para que el orden lo decida el idioma.
    desactivado = t("health.cadencia_desactivado", idioma)
    definicion = (
        ("health.tarea_partidas", bg.check_games_loop,
         t("health.cadencia_segundos", idioma, n=bg.CHECK_INTERVAL)),
        ("health.tarea_puuids", bg.actualizar_puuids_periodico,
         t("health.cadencia_horas", idioma, n=6)),
        ("health.tarea_plantillas", bg.actualizar_accounts_diario,
         t("health.cadencia_horas", idioma, n=24)),
        ("health.tarea_pickrates", bg.actualizar_pickrates_semanal,
         t("health.cadencia_dias", idioma, n=7)),
        ("health.tarea_infoplayers", bg.actualizar_infoplayers_por_lotes,
         t("health.cadencia_horas", idioma, n=1)),
        (
            "health.tarea_historial",
            bg.precalentar_historial,
            t("health.cadencia_segundos", idioma, n=config.HISTORIAL_WARM_INTERVAL)
            if config.HISTORIAL_WARM else desactivado,
        ),
        (
            "health.tarea_rangos",
            bg.refrescar_rangos,
            t("health.cadencia_segundos", idioma, n=config.RANK_WARM_INTERVAL)
            if config.RANK_WARM else desactivado,
        ),
    )

    lineas = []
    for clave, loop, cadencia in definicion:
        if loop.is_running():
            # Un fallo actual no mata el loop (todos capturan), pero conviene verlo.
            marca = "🟡" if loop.failed() else "🟢"
            estado = t(
                "health.estado_parada_error" if loop.failed()
                else "health.estado_activa", idioma,
            )
        elif cadencia == desactivado:
            marca = "⚪"
            estado = t("health.estado_desactivada", idioma)
        else:
            marca = "🔴"
            estado = t("health.estado_detenida", idioma)
        lineas.append(t(
            "health.tarea_linea", idioma,
            marca=marca, nombre=t(clave, idioma),
            estado=estado, cadencia=cadencia,
        ))
    return lineas


async def _cuerpo_health(res: Respuesta) -> None:
    _ = tr(res.guild_id)
    idioma = idioma_de(res.guild_id)

    await res.esperando(_("health.comprobando"))

    seguimiento, _ok = _resumen_seguimiento(idioma)
    averias = salud.hay_averias(idioma)

    color = 0xE74C3C if averias else 0x2ECC71
    embed = nextcord.Embed(
        title=_("health.titulo"),
        description=(
            _("health.encendido", tiempo=_tiempo_encendido(idioma))
            + f"\n{seguimiento}"
        ),
        color=color,
    )

    fuentes = "\n".join(
        salud.linea(clave, estado, idioma)
        for clave, estado in salud.todo().items()
    )
    embed.add_field(name=_("health.campo_fuentes"), value=fuentes, inline=False)
    embed.add_field(
        name=_("health.campo_tareas"),
        value="\n".join(_estado_tareas(idioma)),
        inline=False,
    )

    if averias:
        embed.add_field(
            name=_("health.campo_atencion"),
            value=_("health.averias", fuentes=", ".join(averias)),
            inline=False,
        )

    embed.set_footer(text=_("health.pie"))

    try:
        await res.send(embed=embed)
    except nextcord.HTTPException:
        # Igual que en /help: el comando que informa del estado no puede ser el
        # que se queda callado.
        await res.enviar_partido(
            _("health.respaldo_titulo", tiempo=_tiempo_encendido(idioma)) + "\n"
            + f"{seguimiento}\n\n{fuentes}\n\n"
            + "\n".join(_estado_tareas(idioma))
        )


def register_health_command(bot: commands.Bot) -> None:
    dual(bot, "health", "cmd.health.desc", _cuerpo_health)

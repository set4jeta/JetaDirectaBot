"""Comandos de ranking: `!ranking` y `/ranking`.

Qué se cambió
-------------
1. **Ahora es también `/ranking`,** con selector de liga: `/ranking liga:LCK`.
   Las opciones salen de `apis.dpm_api.LIGAS`, la misma lista que usa el
   backend, así que "todas las ligas" llega a Discord sin duplicarla.

2. **El backend ya no es el viejo.** `build_and_cache_ranking(liga)` pide una
   sola vez `/v1/esport/soloq/leagues/<liga>/leaderboard` y cachea por liga.
   Este comando era el último sitio que llamaba a la firma antigua sin
   argumento, así que el parámetro `liga` existía pero no se podía usar.

3. **Faltaba un `await`.** La versión anterior hacía `ranking = load_ranking_cache()`
   y, si estaba vacío, `ranking = await build_and_cache_ranking()`; el envío de
   la tabla se hacía dentro del decorador y no se podía probar sin Discord.
   Ahora el formateo es una función pura (`construir_tabla`) que sí se prueba.
"""

from __future__ import annotations

import nextcord
from nextcord import SlashOption
from nextcord.ext import commands

from apis.dpm_api import LIGAS
from core.dual_command import GLOBAL, ambito_de, nombre_de, textos_de
from core.rank_data import build_and_cache_ranking
from core.responder import Respuesta
from utils.cache_utils import load_ranking_cache
from utils.i18n import idioma_de, t

LIGA_POR_DEFECTO = "lec"

# El usuario ve el nombre largo y el bot recibe el código.
_LIGAS_CHOICES = {nombre: codigo for codigo, nombre in LIGAS.items()}

_ROLES_CORTOS = {
    "top": "TOP",
    "jungle": "JG",
    "mid": "MID",
    "bot": "ADC",
    "bottom": "ADC",
    "support": "SUPP",
    "utility": "SUPP",
}


def _rol_corto(valor) -> str:
    if not valor:
        return "?"
    return _ROLES_CORTOS.get(str(valor).lower(), str(valor).upper()[:4])


def construir_tabla(ranking: list[dict], limite: int = 20, idioma: str | None = None) -> str:
    """Tabla alineada con los `limite` primeros jugadores del ranking."""
    headers = [
        t("ranking.col_pos", idioma),
        t("ranking.col_jugador", idioma),
        t("ranking.col_equipo", idioma),
        t("ranking.col_rol", idioma),
        t("ranking.col_rango", idioma),
        t("ranking.col_lp", idioma),
        t("ranking.col_winrate", idioma),
        t("ranking.col_kda", idioma),
        t("ranking.col_champs", idioma),
    ]
    rows: list[list[str]] = []
    for i, p in enumerate(ranking[:limite], 1):
        division = (p.get("division") or "").upper()
        tier = (p.get("tier") or "?").capitalize()
        rows.append([
            str(i),
            str(p.get("player", "?")),
            str(p.get("team", "")),
            _rol_corto(p.get("role")),
            f"{tier} {division}".strip(),
            str(p.get("lp", 0)),
            f"{p.get('wins', 0)}W-{p.get('losses', 0)}L ({round(p.get('winrate') or 0)}%)",
            f"{(p.get('kda') or 0):.1f}",
            ", ".join(p.get("best_champions") or [])[:24],
        ])

    anchos = [len(h) for h in headers]
    for row in rows:
        for idx, celda in enumerate(row):
            anchos[idx] = max(anchos[idx], len(celda))

    def centrar(texto: str, ancho: int) -> str:
        hueco = ancho - len(texto)
        if hueco <= 0:
            return texto
        izq = hueco // 2
        return " " * izq + texto + " " * (hueco - izq)

    lineas = [
        "| " + " | ".join(centrar(h, anchos[i]) for i, h in enumerate(headers)) + " |",
        "|-" + "-|-".join("-" * a for a in anchos) + "-|",
    ]
    lineas += [
        "| " + " | ".join(centrar(c, anchos[i]) for i, c in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join(lineas)


async def obtener_ranking(liga: str) -> list[dict]:
    """Ranking de una liga: de la caché si está fresca, si no se recalcula."""
    ranking = load_ranking_cache(liga)
    if not ranking:
        ranking = await build_and_cache_ranking(liga)
    return ranking or []


async def _responder_ranking(res: Respuesta, liga: str) -> None:
    """Cuerpo único: lo usan la forma de prefijo y la de slash."""
    idioma = idioma_de(res.guild_id)
    liga = (liga or LIGA_POR_DEFECTO).lower().strip()
    if liga not in LIGAS:
        await res.error(t(
            "ranking.liga_desconocida", idioma,
            liga=liga,
            disponibles=", ".join(f"`{c}`" for c in LIGAS),
        ))
        return

    await res.esperando(t("ranking.calculando", idioma, liga=LIGAS[liga]))

    ranking = await obtener_ranking(liga)
    if not ranking:
        await res.error(t("ranking.sin_datos", idioma, liga=LIGAS[liga]))
        return

    await res.send(t("ranking.titulo", idioma, liga=LIGAS[liga], total=len(ranking)))
    await res.enviar_bloque(construir_tabla(ranking, idioma=idioma))


def register_ranking_command(bot: commands.Bot):
    @bot.command(name="ranking")
    async def ranking_prefijo(ctx: commands.Context, liga: str = LIGA_POR_DEFECTO):
        # `!ranking` sin argumento sigue dando LEC, como antes. `!ranking lck`
        # es nuevo y sale gratis del backend multi-liga.
        await _responder_ranking(Respuesta(ctx), liga)

    # `/ranking` no pasa por `dual_texto` porque su argumento es un desplegable
    # de ligas, no texto libre; la localización se monta a mano con las mismas
    # claves del catálogo que usa el resto.
    desc, desc_loc = textos_de("cmd.ranking.desc")
    arg, arg_loc = nombre_de("cmd.ranking.arg")
    ayuda, ayuda_loc = textos_de("cmd.ranking.arg_desc")

    @bot.slash_command(
        name="ranking",
        description=desc,
        description_localizations=desc_loc or None,
        # Mismo ámbito que los comandos registrados por `dual`: `/ranking` es de
        # consulta, así que tiene que funcionar también en el chat privado de
        # quien se instale el bot en su cuenta. Se pide el ámbito en vez de
        # escribir los enums aquí para que este comando no se quede atrás cuando
        # cambie la política de los demás.
        **ambito_de(GLOBAL),
    )
    async def ranking_slash(
        interaction: nextcord.Interaction,
        liga: str = SlashOption(
            name=arg,
            name_localizations=arg_loc or None,
            description=ayuda,
            description_localizations=ayuda_loc or None,
            choices=_LIGAS_CHOICES,
            required=False,
            default=LIGA_POR_DEFECTO,
        ),
    ):
        await _responder_ranking(Respuesta(interaction), liga)

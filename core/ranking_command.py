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

from nextcord.ext import commands

from apis.dpm_api import LIGAS, LIGAS_CHOICES
from core.dual_command import slash_opciones
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
    # La API de dpm.lol manda `MIDDLE` (y `BOTTOM`, `UTILITY`). Sin esta línea el
    # `get` fallaba y la tabla pintaba `MIDD` — y el filtro de rol por `mid` no
    # encontraba a nadie, que es peor: un filtro que no filtra se lee como avería.
    "middle": "MID",
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


#: Roles que se pueden pedir como filtro. El valor es el código que se manda y
#: la etiqueta es lo que se ve en el desplegable.
_ROLES: dict[str, str] = {
    "Top": "top",
    "Jungle": "jungle",
    "Mid": "mid",
    "Bot": "bot",
    "Support": "support",
}

#: Cuántas filas se pueden pedir. Son pocos y cerrados a propósito: la tabla es
#: texto monoespaciado y a partir de 20 se parte en varios mensajes.
_TOPES: tuple[str, ...] = ("5", "10", "15", "20")

async def _responder_ranking(res: Respuesta, valores: dict[str, str]) -> None:
    """Cuerpo de `/ranking <league> [role] [limit]`.

    El rol y el límite son **filtros locales**: la tabla de la liga ya se ha
    pedido entera (una llamada, cacheada) y esto solo recorta lo que se pinta. Por
    eso se pueden ofrecer sin tocar el rate limit, que era la duda razonable del
    dueño al pedirlos.
    """
    idioma = idioma_de(res.guild_id)
    liga = (valores.get("league") or "").strip().lower()
    rol = (valores.get("role") or "").strip().lower()
    limite = (valores.get("limit") or "").strip()

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

    total = len(ranking)

    if rol:
        # Se compara con `_rol_corto` en los dos lados y no con un mapa aparte:
        # así el filtro habla exactamente el vocabulario de la tabla y no hay dos
        # listas de roles que se puedan desincronizar.
        corto = _rol_corto(rol)
        ranking = [p for p in ranking if _rol_corto(p.get("role")) == corto]
        if not ranking:
            await res.error(t(
                "ranking.sin_rol", idioma, rol=rol, liga=LIGAS[liga],
            ))
            return

    try:
        filas = int(limite)
    except ValueError:
        filas = 20

    await res.send(t("ranking.titulo", idioma, liga=LIGAS[liga], total=total))
    if rol or filas < len(ranking):
        aviso = t(
            "ranking.mostrando", idioma,
            n=min(filas, len(ranking)), total=len(ranking),
        )
        if rol:
            aviso += t("ranking.solo_rol", idioma, rol=rol.upper())
        await res.send(aviso)
    await res.enviar_bloque(construir_tabla(ranking, limite=filas, idioma=idioma))


def register_ranking_command(bot: commands.Bot) -> None:
    # Ya no necesita registro a mano: `slash_opciones` cubre los tres argumentos
    # (liga obligatoria, rol y límite) y le pone el mismo ámbito que a los demás.
    slash_opciones(
        bot,
        "cmd.ranking.name",
        "cmd.ranking.desc",
        _responder_ranking,
        opciones=(
            ("cmd.ranking.arg", "cmd.ranking.arg_desc", LIGAS_CHOICES, None),
            ("cmd.ranking.rol", "cmd.ranking.rol_desc", _ROLES, ""),
            ("cmd.ranking.limite", "cmd.ranking.limite_desc", _TOPES, "20"),
        ),
    )

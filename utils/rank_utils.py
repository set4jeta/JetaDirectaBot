"""Comparación y formateo de rangos de SoloQ.

`!team` mostraba siempre la primera cuenta de cada jugador sin mirar su Elo,
así que un pro podía aparecer con su cuenta secundaria de Diamante teniendo la
principal en Challenger. Aquí está la lógica para elegir la mejor.

Escalas
-------

Los rangos se comparan convirtiéndolos a un entero:

    liga * 1_000_000 + division * 10_000 + LP

La liga pesa mucho más que la división y esta más que los LP, así que el
orden natural de los enteros coincide con el orden competitivo. En Maestro,
Gran Maestro y Challenger no hay división (vale 0) y los LP pueden pasar de
1000, por eso el hueco entre ligas es tan grande.
"""

from __future__ import annotations

# De menor a mayor. El índice dentro de la tupla es el peso de la liga.
LIGAS = (
    "UNRANKED", "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD",
    "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER",
)

# La división I es la más alta dentro de una liga.
DIVISIONES = {"IV": 1, "III": 2, "II": 3, "I": 4}

_PESO_LIGA = {nombre: i for i, nombre in enumerate(LIGAS)}


def valor_liga(tier: str | None) -> int:
    if not tier:
        return 0
    return _PESO_LIGA.get(str(tier).strip().upper(), 0)


def valor_rank(rank: dict | None) -> int:
    """Entero comparable. 0 si no hay rango o es desconocido."""
    if not isinstance(rank, dict):
        return 0

    tier = str(rank.get("tier", "")).strip().upper()
    if not tier or tier in ("DESCONOCIDO", "UNRANKED", "NONE"):
        return 0

    liga = valor_liga(tier)
    if liga == 0:
        return 0

    division = str(rank.get("division", "") or "").strip().upper()
    peso_division = DIVISIONES.get(division, 0)

    try:
        lp = int(rank.get("lp") or 0)
    except (TypeError, ValueError):
        lp = 0

    return liga * 1_000_000 + peso_division * 10_000 + max(0, lp)


def formatear_rank(rank: dict | None, idioma: str | None = None) -> str:
    """`Master I (503 LP)`, `Oro IV (42 LP)` o `Sin datos`.

    El único texto que hay aquí es el "Sin datos", que sale en `/team`: el tier
    y la división son nombres propios de Riot y no se traducen. `idioma` va al
    final y por defecto en `None` (= español) para no romper a
    `scripts/test_team.py`, que llama `formatear_rank(rango)`.
    """
    from utils.i18n import t

    if not isinstance(rank, dict):
        return t("team.sin_datos", idioma)

    tier = rank.get("tier")
    if not tier or str(tier).strip().upper() in ("DESCONOCIDO", "UNRANKED"):
        return t("team.sin_datos", idioma)

    division = rank.get("division", "")
    lp = rank.get("lp", 0)
    texto = f"{tier} {division}".strip()
    if lp is not None:
        texto += f" ({lp} LP)"
    return texto


def es_rank_valido(rank: dict | None) -> bool:
    return valor_rank(rank) > 0


def mejor_cuenta(cuentas_con_rank: list[tuple]) -> tuple | None:
    """De una lista de (cuenta, rank) devuelve la del Elo más alto.

    Solo se consideran las que tienen un rango válido; si ninguna lo tiene
    devuelve None y el llamador decide qué hacer.
    """
    validas = [(c, r) for c, r in cuentas_con_rank if es_rank_valido(r)]
    if not validas:
        return None
    return max(validas, key=lambda par: valor_rank(par[1]))

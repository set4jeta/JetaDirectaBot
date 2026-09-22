## utils/constants.py


TEAM_TRICODES = {
    "FNC": "Fnatic",
    "G2": "G2 Esports",
    "GX": "GIANTX",
    "KC": "Karmine Corp",
    "MKOI": "Movistar KOI",
    "NAVI": "Natus Vincere",
    "SK": "SK Gaming",
    "BDS": "Team BDS",
    "TH": "Team Heretics",
    "VIT": "Team Vitality",
    "LR": "Los Ratones",
    "MKF": "Movistar KOI Fénix",
}


QUEUE_ID_TO_NAME: dict[int, str] = {
    400: "Normal Draft",
    420: "Clasificatoria Solo/Duo",
    430: "Normal Blind",
    440: "Clasificatoria Flex",
    450: "ARAM",
    700: "Clash",
    900: "URF",
    1700: "Arena",
    # 1750 es el id que devuelve `spectator-v5` de verdad para Arena (verificado
    # con `scripts/probe_spectator_timing.py`: `[CHERRY / cola 1750]`). Sin esta
    # línea el embed de una partida de Arena decía «Desconocida (1750)».
    1710: "Arena",
    1750: "Arena",
    1300: "Nexus Blitz",
    1090: "TFT Normal",
    1100: "TFT Ranked",
    0: "Personalizada",
    830: "Tutorial",
    840: "Bots",
}

# Solo las colas cuyo nombre cambia de idioma. Riot llama "Normal Draft",
# "ARAM" o "Clash" igual en los dos, así que repetirlas aquí sería ruido: lo
# que no esté en este mapa se coge de `QUEUE_ID_TO_NAME`.
QUEUE_ID_TO_NAME_EN: dict[int, str] = {
    420: "Ranked Solo/Duo",
    440: "Ranked Flex",
    0: "Custom",
    840: "Co-op vs AI",
}


def nombre_cola(queue_id, idioma: str | None = None) -> str:
    """Nombre de la cola en el idioma pedido.

    Con `queue_id` desconocido devuelve «Desconocida (1234)» / «Unknown (1234)»
    en vez de un hueco: saber que la cola existe pero no la reconocemos es más
    útil que no decir nada, y el número es lo que hace falta para añadirla.
    """
    from utils.i18n import t

    if not isinstance(queue_id, int):
        return t("partida.desconocida", idioma)
    if idioma == "en" and queue_id in QUEUE_ID_TO_NAME_EN:
        return QUEUE_ID_TO_NAME_EN[queue_id]
    nombre = QUEUE_ID_TO_NAME.get(queue_id)
    if nombre:
        return nombre
    return t("partida.desconocida_id", idioma, id=queue_id)


ROLE_ORDER = {
    "TOP": 0,
    "JUNGLE": 1,
    "MIDDLE": 2,
    "BOTTOM": 3,
    "UTILITY": 4,
    # `utils/role_assigner.assign_roles` devuelve "SUPPORT", no "UTILITY", así que
    # sin esta línea el soporte caía al 99. Salía último de todas formas —que es
    # su sitio— pero por accidente, no porque estuviera ordenado.
    "SUPPORT": 4,
    "FLEX": 99,
}


# Hay tres vocabularios de roles en el proyecto y no coinciden:
#
#   * Riot / `match-v5`      -> TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY
#   * `assign_roles`         -> TOP, JUNGLE, MIDDLE, BOTTOM, SUPPORT
#   * ficheros de equipos    -> Top, Jungle, Mid, Bot, Support (y "ADC")
#
# `normalizar_rol` los unifica en la forma de `assign_roles`, que es la que
# usan los embeds. Sin esto, `!live` mezclaba MID/MIDDLE y BOT/BOTTOM según el
# rol viniera de la partida o del fichero del equipo.
ROLE_ALIASES = {
    "TOP": "TOP", "TOPLANE": "TOP",
    "JUNGLE": "JUNGLE", "JGL": "JUNGLE", "JG": "JUNGLE", "JUNGLA": "JUNGLE",
    "MIDDLE": "MIDDLE", "MID": "MIDDLE", "MIDLANE": "MIDDLE",
    "BOTTOM": "BOTTOM", "BOT": "BOTTOM", "ADC": "BOTTOM", "BOTLANE": "BOTTOM",
    "SUPPORT": "SUPPORT", "UTILITY": "SUPPORT", "SUP": "SUPPORT",
    "SUPP": "SUPPORT", "SOPORTE": "SUPPORT",
}

# Etiquetas cortas para listados densos como `!live`.
ROLE_SHORT = {
    "TOP": "TOP",
    "JUNGLE": "JGL",
    "MIDDLE": "MID",
    "BOTTOM": "BOT",
    "SUPPORT": "SUP",
}


def normalizar_rol(rol: str | None) -> str:
    """`'Mid'` -> `'MIDDLE'`, `'UTILITY'` -> `'SUPPORT'`. `'?'` si no se sabe."""
    if not rol:
        return "?"
    return ROLE_ALIASES.get(str(rol).strip().upper(), str(rol).strip().upper())


def rol_corto(rol: str | None) -> str:
    """Forma corta y normalizada: `'Support'` -> `'SUP'`."""
    canonico = normalizar_rol(rol)
    return ROLE_SHORT.get(canonico, canonico)



SPELL_ROLE_PRIORITY = {
    "Ignite":   {"top": 0.4, "mid": 0.8, "support": 0.6, "adc": 0.1},
    "Teleport": {"top": 1.0, "mid": 0.5},
    "Heal":     {"adc": 1.0, "support": 0.6},
    "Barrier":  {"mid": 0.5, "adc": 0.2},
    "Cleanse":  {"adc": 0.9, "mid": 0.1},
    "Exhaust":  {"support": 0.9, "adc": 0.2, "mid": 0.1},
    "Ghost":    {"top": 0.6, "mid": 0.3, "adc": 0.5},
}


SPELL_ID_TO_NAME = {
    1: "Cleanse",
    3: "Exhaust",
    4: "Flash",
    6: "Ghost",
    7: "Heal",
    11: "Smite",
    12: "Teleport",
    13: "Clarity",
    14: "Ignite",
    21: "Barrier",
}
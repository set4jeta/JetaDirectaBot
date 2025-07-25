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
    1300: "Nexus Blitz",
    1090: "TFT Normal",
    1100: "TFT Ranked",
    0: "Personalizada",
    830: "Tutorial",
    840: "Bots",
}

ROLE_ORDER = {
    "TOP": 0,
    "JUNGLE": 1,
    "MIDDLE": 2,
    "BOTTOM": 3,
    "UTILITY": 4,
    "FLEX":99
}



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
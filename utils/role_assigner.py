"""Deduce qué rol juega cada participante a partir de su campeón.

`spectator-v5` **no dice el rol**: sus participantes solo traen `championId`,
`spell1Id`, `spell2Id`, `teamId`, `puuid` y `riotId`. El rol se infiere de los
pickrates por línea de cada campeón (`champion_lane_pickrates.json`) resolviendo
una asignación óptima equipo por equipo, más un par de pistas de los hechizos
(Smite ⇒ jungla, etc.).

Qué se cambió
-------------

1. **El JSON se lee una vez, no una por consulta.** `get_pickrates_for_id`
   llamaba a `load_champion_pickrates()`, que abría y parseaba los 36 KB del
   fichero en cada llamada. Con dos equipos son ~15 llamadas por embed, es
   decir ~15 lecturas de disco para el mismo dato inmutable. Ahora se cachea y
   se recarga solo si cambia la fecha de modificación.

2. **Los avisos van al log, no a `stdout`.** Eran tres `print("[ROLE] ...")`;
   uno de ellos imprimía el `repr` del objeto (`<models.soloq_match.
   SoloQParticipant object at 0x...>`) porque `SoloQParticipant` no tiene
   `.name`. En Render eso acababa en el log de stdout sin nivel ni contexto.

3. **Los modos que no son 5v5 ya no se fuerzan a líneas.** Arena manda 18
   participantes, todos con `teamId` 100. El código los metía en
   `assign_roles_team_greedy`, que reparte TOP/MID/BOT/SUPPORT entre los
   primeros y deja al resto en TOP «por defecto (muy raro)» — que en Arena no
   es raro, son 14 jugadores. Ahora en esos modos se deja el rol a `None` y
   quien pinta decide qué hacer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from utils.logger import get_logger

log = get_logger("utils.role_assigner")

PICKRATE_PATH = Path(__file__).resolve().parent.parent / "champion_lane_pickrates.json"

ROLES_STANDARD = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"]
SMITE = 11

# El fichero usa el vocabulario de Riot (`UTILITY`); el resto del bot usa
# `SUPPORT`. Se traduce al cargar, una sola vez, en vez de en cada consulta.
_TRADUCE_ROL = {"UTILITY": "SUPPORT"}

_cache: dict[str, dict[str, float]] = {}
_cache_mtime: float | None = None


def load_champion_pickrates() -> dict[str, dict[str, float]]:
    """Pickrates por campeón y línea, cacheados y con recarga por mtime."""
    global _cache, _cache_mtime

    try:
        mtime = os.path.getmtime(PICKRATE_PATH)
    except OSError:
        if _cache_mtime is None:
            log.warning("No existe %s: los roles saldrán sin deducir.", PICKRATE_PATH)
            _cache_mtime = 0.0
        return _cache

    if _cache_mtime == mtime:
        return _cache

    try:
        with open(PICKRATE_PATH, "r", encoding="utf-8") as fh:
            crudo = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.error("No se pudo leer %s: %s", PICKRATE_PATH, exc)
        return _cache

    _cache = {
        str(champ): {_TRADUCE_ROL.get(rol, rol): float(valor) for rol, valor in filas.items()}
        for champ, filas in crudo.items()
    }
    _cache_mtime = mtime
    log.debug("Pickrates cargados: %d campeones", len(_cache))
    return _cache


def get_pickrates_for_id(champion_id: int | str) -> dict[str, float]:
    return load_champion_pickrates().get(str(champion_id), {})


def _hechizos(p) -> tuple[int | None, int | None]:
    """`(spell1Id, spell2Id)` del participante, o `(None, None)`."""
    extra = getattr(p, "datos_extra", None)
    if not isinstance(extra, dict):
        return None, None
    return extra.get("spell1Id"), extra.get("spell2Id")


def get_role_spell_bonus(spell_id) -> dict[str, float]:
    """Bonos por hechizo de invocador. Ayudan en los casos ambiguos."""
    if spell_id == 14:  # Ignite
        return {"MIDDLE": 0.3, "TOP": 0.2, "SUPPORT": 0.1}
    if spell_id == 6:  # Ghost
        return {"BOTTOM": 0.2, "TOP": 0.1}
    return {}


def assign_roles(participants, puuid_to_player=None):
    """Asigna `p.role` a cada participante. Devuelve azules + rojos.

    En los modos que no son 5v5 (Arena manda 18 jugadores en un solo equipo) no
    hay líneas que repartir: se deja `role` a `None` y se devuelve la lista tal
    cual, sin inventar un TOP por descarte.
    """
    blue = [p for p in participants if p.team_id == 100]
    red = [p for p in participants if p.team_id == 200]

    if len(blue) > 5 or len(red) > 5:
        log.debug(
            "Modo sin líneas (%d/%d participantes por equipo): no se asignan roles.",
            len(blue), len(red),
        )
        for p in blue + red:
            p.role = None
        return blue + red

    assign_roles_team_optimal(blue, puuid_to_player)
    assign_roles_team_optimal(red, puuid_to_player)
    return blue + red


def assign_roles_team_optimal(team, puuid_to_player=None):
    if len(team) != 5:
        return assign_roles_team_greedy(team)

    # Pista opcional: el rol que el jugador ocupa en su equipo profesional.
    # `!live` no la pasa a propósito, porque en SoloQ puede estar jugando otra
    # línea y la pista sesgaría el resultado hacia la equivocada.
    if puuid_to_player:
        for p in team:
            player_obj = puuid_to_player.get(getattr(p, "puuid", None))
            if player_obj and getattr(player_obj, "role", None):
                p.role = player_obj.role

    pickrate_matrix = np.zeros((5, 5))
    spell_hint_bonus = np.zeros((5, 5))
    forced_jungle_index = None

    # 1. El jungla es quien lleva Smite; si hay varios, el mejor jungla.
    best_jungle_score = -1.0
    for i, p in enumerate(team):
        if SMITE not in _hechizos(p):
            continue
        jungle_score = get_pickrates_for_id(p.champion_id).get("JUNGLE", 0)
        if jungle_score > best_jungle_score:
            best_jungle_score = jungle_score
            forced_jungle_index = i

    # 2. Matriz de puntuaciones.
    for i, p in enumerate(team):
        pickrates = get_pickrates_for_id(p.champion_id)
        max_pr = max(pickrates.values(), default=0.0001) or 0.0001

        spell1, spell2 = _hechizos(p)
        bonus_1 = get_role_spell_bonus(spell1)
        bonus_2 = get_role_spell_bonus(spell2)
        es_jungla_forzado = forced_jungle_index is not None and i == forced_jungle_index

        for j, role in enumerate(ROLES_STANDARD):
            if es_jungla_forzado:
                pickrate_matrix[i, j] = (
                    pickrates.get(role, 0) or 0.0001 if role == "JUNGLE" else -1e9
                )
            elif forced_jungle_index is not None and role == "JUNGLE":
                pickrate_matrix[i, j] = -1e9
            else:
                pickrate_matrix[i, j] = pickrates.get(role, 0) / max_pr

            bonus = bonus_1.get(role, 0) + bonus_2.get(role, 0)

            # Si ya traía un rol (la pista del equipo) y coincide con el que se
            # evalúa, se le sube hasta empatar con su mejor línea.
            if getattr(p, "role", None) == role and not es_jungla_forzado:
                actual_pr = pickrates.get(role, 0)
                bonus += (max_pr - actual_pr) / max_pr

            spell_hint_bonus[i, j] = bonus

    # 3. Asignación óptima (húngaro) sobre pickrate + bonos.
    _row_ind, col_ind = linear_sum_assignment(-(pickrate_matrix + spell_hint_bonus))

    for i, p in enumerate(team):
        p.role = ROLES_STANDARD[col_ind[i]]


def assign_roles_team_greedy(team):
    """Respaldo para equipos incompletos (menos de 5): mejor pickrate primero."""
    asignados: set[str] = set()

    # 1. Jungla por Smite.
    mejor_jungla = None
    mejor_score = -1.0
    for p in team:
        if SMITE not in _hechizos(p):
            continue
        score = get_pickrates_for_id(p.champion_id).get("JUNGLE", 0)
        if score > mejor_score:
            mejor_score = score
            mejor_jungla = p

    if mejor_jungla is not None:
        mejor_jungla.role = "JUNGLE"
        asignados.add("JUNGLE")

    # 2. El resto, por pickrate en cada línea.
    for role in ROLES_STANDARD:
        if role in asignados:
            continue
        mejor_p = None
        mejor_pr = -1.0
        for p in team:
            if getattr(p, "role", None):
                continue
            pr = get_pickrates_for_id(p.champion_id).get(role, 0)
            if pr > mejor_pr:
                mejor_pr = pr
                mejor_p = p
        if mejor_p is not None and mejor_pr > 0:
            mejor_p.role = role
            asignados.add(role)

    # 3. A quien quede sin rol se le deja sin rol. Antes se le ponía "TOP" con un
    #    comentario de «muy raro»; en Arena pasaba con 14 jugadores de 18.
    sin_rol = [p for p in team if not getattr(p, "role", None)]
    if sin_rol:
        log.debug("%d participante(s) sin rol deducible en un equipo de %d.",
                  len(sin_rol), len(team))

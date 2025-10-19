import os
import json
import numpy as np
from scipy.optimize import linear_sum_assignment

PICKRATE_PATH = os.path.join(os.path.dirname(__file__), "..", "champion_lane_pickrates.json")

def load_champion_pickrates():
    if not os.path.exists(PICKRATE_PATH):
        print(f"[ROLE] No existe {PICKRATE_PATH}")
        return {}
    with open(PICKRATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_pickrates_for_id(champion_id: int | str):
    return load_champion_pickrates().get(str(champion_id), {})

def assign_roles(participants, puuid_to_player=None):
    blue = [p for p in participants if p.team_id == 100]
    red = [p for p in participants if p.team_id == 200]
    assign_roles_team_optimal(blue, puuid_to_player)
    assign_roles_team_optimal(red, puuid_to_player)
    return blue + red

# 🧠 Bonos por hechizos de invocador (ayudan en casos ambiguos)
def get_role_spell_bonus(spell_id):
    if spell_id == 14:  # Ignite
        return {"MIDDLE": 0.3, "TOP": 0.2, "SUPPORT": 0.1}
    if spell_id == 6:   # Ghost
        return {"BOTTOM": 0.2, "TOP": 0.1}
    return {}

def assign_roles_team_optimal(team, puuid_to_player=None):
    roles_standard = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"]
    n = len(team)
    if n != 5:
        return assign_roles_team_greedy(team)


    if puuid_to_player:
        for p in team:
            player_obj = puuid_to_player.get(getattr(p, "puuid", None))
            if player_obj and getattr(player_obj, "role", None):
                p.role = player_obj.role

    
    
    
    pickrate_matrix = np.zeros((5, 5))
    spell_hint_bonus = np.zeros((5, 5))  # Bonificación por hechizos
    forced_jungle_index = None

    # 1. Identificar al mejor jungla entre los que tienen Smite
    smite_candidates = []
    for i, p in enumerate(team):
        spell1 = getattr(p.datos_extra, "get", lambda k: None)("spell1Id") if hasattr(p, "datos_extra") else None
        spell2 = getattr(p.datos_extra, "get", lambda k: None)("spell2Id") if hasattr(p, "datos_extra") else None
        if spell1 == 11 or spell2 == 11:
            smite_candidates.append(i)

    best_jungle_score = -1
    for i in smite_candidates:
        champ_id = team[i].champion_id
        pickrates = get_pickrates_for_id(champ_id)
        jungle_score = pickrates.get("JUNGLE", 0)
        if jungle_score > best_jungle_score:
            best_jungle_score = jungle_score
            forced_jungle_index = i

    # 2. Construir la matriz
    for i, p in enumerate(team):
        champ_id = p.champion_id
        pickrates = get_pickrates_for_id(champ_id)
        pickrates = {("SUPPORT" if k == "UTILITY" else k): v for k, v in pickrates.items()}
        max_pr = max(pickrates.values(), default=0.0001)

        spell1 = getattr(p.datos_extra, "get", lambda k: None)("spell1Id") if hasattr(p, "datos_extra") else None
        spell2 = getattr(p.datos_extra, "get", lambda k: None)("spell2Id") if hasattr(p, "datos_extra") else None

        bonus_dict_1 = get_role_spell_bonus(spell1)
        bonus_dict_2 = get_role_spell_bonus(spell2)

        for j, role in enumerate(roles_standard):
            if forced_jungle_index is not None and i == forced_jungle_index:
                if role == "JUNGLE":
                    pr = pickrates.get(role, 0) or 0.0001
                    pickrate_matrix[i, j] = pr
                else:
                    pickrate_matrix[i, j] = -1e9
            else:
                if forced_jungle_index is not None and role == "JUNGLE":
                    pickrate_matrix[i, j] = -1e9
                else:
                    pr = pickrates.get(role, 0)
                    relative_score = pr / max_pr if max_pr > 0 else 0
                    pickrate_matrix[i, j] = relative_score

            bonus = bonus_dict_1.get(role, 0) + bonus_dict_2.get(role, 0)

            # 💡 Bonus dinámico si player.role coincide con el rol evaluado
            if hasattr(p, "role") and p.role == role and not (forced_jungle_index is not None and i == forced_jungle_index):
                top_pr = max(pickrates.values(), default=0.0001)
                actual_pr = pickrates.get(role, 0)
                bonus_needed = (top_pr - actual_pr) / top_pr
                bonus += bonus_needed

            spell_hint_bonus[i, j] += bonus

    # 3. Asignación óptima usando pickrate + bonus
    total_score_matrix = pickrate_matrix + spell_hint_bonus
    row_ind, col_ind = linear_sum_assignment(-total_score_matrix)

    # 4. Asignar roles SIN usar "FLEX"
    assigned_roles = set()
    for i, p in enumerate(team):
        assigned_role = roles_standard[col_ind[i]]
        # No asignar FLEX, si pickrate bajo, asignar rol igualmente (puede ser bajo pero lo asignamos)
        p.role = assigned_role
        assigned_roles.add(assigned_role)

    # Si sobra alguien sin rol, asignarle rol libre (poco probable)
    remaining_roles = [r for r in roles_standard if r not in assigned_roles]
    for p in team:
        if not getattr(p, "role", None):
            if remaining_roles:
                p.role = remaining_roles.pop(0)
            else:
                print(f"[ROLE] Jugador sin rol asignado (TOP): {p.name if hasattr(p, 'name') else p}")
                p.role = "TOP"  # Por defecto (muy raro)

def assign_roles_team_greedy(team):
    roles_standard = ["TOP", "MIDDLE", "BOTTOM", "SUPPORT"]
    assigned_roles = set()
    # 1. JUNGLE por Smite
    smite_players = []
    for p in team:
        spell1 = getattr(p.datos_extra, "get", lambda k: None)("spell1Id") if hasattr(p, "datos_extra") else None
        spell2 = getattr(p.datos_extra, "get", lambda k: None)("spell2Id") if hasattr(p, "datos_extra") else None
        if spell1 == 11 or spell2 == 11:
            smite_players.append(p)

    best_jungle = None
    best_score = -1
    for p in smite_players:
        champ_id = p.champion_id
        pickrates = get_pickrates_for_id(champ_id)
        jungle_pr = pickrates.get("JUNGLE", 0)
        if jungle_pr > best_score:
            best_score = jungle_pr
            best_jungle = p

    if best_jungle:
        best_jungle.role = "JUNGLE"
        assigned_roles.add("JUNGLE")

    # 2. Resto por pickrate
    for role in roles_standard:
        if role in assigned_roles:
            continue
        best_p = None
        best_pickrate = -1
        for p in team:
            if getattr(p, "role", None):
                continue
            champ_id = p.champion_id
            pickrates = get_pickrates_for_id(champ_id)
            pickrates = {("SUPPORT" if k == "UTILITY" else k): v for k, v in pickrates.items()}
            pr = pickrates.get(role, 0)
            if pr > best_pickrate:
                best_pickrate = pr
                best_p = p
        if best_p and best_pickrate > 0:
            best_p.role = role
            assigned_roles.add(role)

    # 3. ASIGNAR ROL A LOS QUE QUEDEN SIN ROL SIN USAR FLEX
    remaining_roles = list(set(roles_standard) - assigned_roles)
    for p in team:
        if not getattr(p, "role", None):
            print(f"[ROLE] Jugador sin rol tras asignación óptima: {p.name if hasattr(p, 'name') else p}")
            if remaining_roles:
                p.role = remaining_roles.pop()
            else:
                p.role = "TOP"  # Por defecto si no quedan roles (muy raro)

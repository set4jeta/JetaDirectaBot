TRACKED_TEAMS = {"G2", "FNC", "VIT", "TH", "KC", "NAVI", "GX", "BDS", "SK", "MKOI", "KOI", "LR"}  # Modifica según tus equipos

def get_tracked_players(players):
    tracked = [p for p in players if (p.team or "").upper() in TRACKED_TEAMS]
    equipos_encontrados = sorted({(p.team or "").upper() for p in tracked if p.team})
    total_cuentas = sum(len(p.accounts) for p in tracked)
    print(f"🔎 Trackeando {len(tracked)} jugadores ({total_cuentas} cuentas) de {len(players)} jugadores totales.")
    print(f"🟢 Jugadores encontrados en equipos: {', '.join(equipos_encontrados) if equipos_encontrados else 'Ninguno'}")
    return tracked
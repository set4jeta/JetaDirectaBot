"""Sonda de un solo uso: qué ligas acepta el leaderboard de esports de dpm.lol.

`/v1/esport/soloq/leagues/<liga>/leaderboard` devuelve, en **una** petición y por
cloudscraper (HTTP 200): puuid, displayName, team, lane, tier, rank,
leaguePoints, wins, losses, kda y mostChamps de todos los jugadores de la liga.
Esta sonda comprueba qué códigos de liga existen de verdad.
"""

import sys

import cloudscraper

CANDIDATAS = [
    "lec", "lfl", "superliga", "prime", "nlc", "ultraliga", "hitpoint", "esls",
    "lck", "lck-cl", "lcp", "lpl", "lta", "lta-n", "lta-s", "lcs", "cblol",
    "ljl", "vcs", "pcs", "lla", "emea-masters", "nacl", "tcl", "arabian",
]


def main() -> None:
    ligas = sys.argv[1:] or CANDIDATAS
    scraper = cloudscraper.create_scraper(browser={"custom": "Chrome"}, delay=10)
    vivas: list[tuple[str, int, set[str]]] = []

    for liga in ligas:
        url = f"https://dpm.lol/v1/esport/soloq/leagues/{liga}/leaderboard"
        try:
            resp = scraper.get(url, timeout=20)
        except Exception as exc:
            print(f"{liga:<14} ERROR {type(exc).__name__}")
            continue

        if resp.status_code != 200:
            print(f"{liga:<14} HTTP {resp.status_code}")
            continue

        try:
            datos = resp.json()
        except ValueError:
            print(f"{liga:<14} HTTP 200 pero no-JSON")
            continue

        if not isinstance(datos, list) or not datos:
            print(f"{liga:<14} HTTP 200, vacío")
            continue

        equipos = {d.get("team") for d in datos if d.get("team")}
        vivas.append((liga, len(datos), equipos))
        print(f"{liga:<14} {len(datos):>4} jugadores | {len(equipos)} equipos: "
              f"{', '.join(sorted(equipos)[:14])}")

    print(f"\nLigas vivas: {len(vivas)} -> {', '.join(l for l, _, _ in vivas)}")
    print(f"Jugadores totales: {sum(n for _, n, _ in vivas)}")


if __name__ == "__main__":
    main()

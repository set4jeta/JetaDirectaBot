"""Sonda de un solo uso: qué ligas y equipos publica dpm.lol."""

import json
import re
import sys

import cloudscraper

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])

from apis.dpm_payload import reconstruir_payload  # noqa: E402


def main() -> None:
    scraper = cloudscraper.create_scraper(browser={"custom": "Chrome"}, delay=10)

    for url in (
        "https://dpm.lol/esport/soloq",
        "https://dpm.lol/esport/soloq/leagues/lec",
    ):
        resp = scraper.get(url, timeout=25)
        print(f"\n=== {url} -> HTTP {resp.status_code} ({len(resp.text)} bytes) ===")
        if resp.status_code != 200:
            continue
        flujo = reconstruir_payload(resp.text)
        print(f"payload: {len(flujo)} caracteres")
        for campo in ("teams", "league", "leagues", "tag", "slug", "code", "name"):
            vals = sorted(set(re.findall(rf'"{campo}":"?([^",}}\]]{{1,40}})', flujo)))
            if vals:
                print(f"  {campo} ({len(vals)}): {vals[:40]}")

    for endpoint in (
        "https://dpm.lol/v1/esport/soloq/leagues",
        "https://dpm.lol/v1/esport/soloq/leagues/lec/teams",
        "https://dpm.lol/v1/esport/soloq/leagues/lec/leaderboard",
        "https://dpm.lol/v1/esport/teams",
        "https://dpm.lol/v1/leagues",
    ):
        try:
            r = scraper.get(endpoint, timeout=20)
            cuerpo = r.text[:300].replace("\n", " ")
            print(f"\n{endpoint} -> HTTP {r.status_code} | {cuerpo}")
        except Exception as exc:
            print(f"\n{endpoint} -> ERROR {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()

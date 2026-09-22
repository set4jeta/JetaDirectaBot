"""Sonda de un solo uso: forma exacta de los objetos de jugador en el payload RSC."""

import json
import re
import sys

import cloudscraper


def extraer_payload(html: str) -> str:
    trozos = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)', html)
    return "".join(json.loads(f'"{t}"') for t in trozos)


def main() -> None:
    equipo = sys.argv[1] if len(sys.argv) > 1 else "G2"
    scraper = cloudscraper.create_scraper(browser={"custom": "Chrome"}, delay=10)
    resp = scraper.get(f"https://dpm.lol/esport/soloq/teams/{equipo}", timeout=25)
    flujo = extraer_payload(resp.text)

    pos = flujo.find('"gameName"')
    print(f"primera aparición de gameName en {pos}")
    print("--- contexto (1200 caracteres antes) ---")
    print(flujo[max(0, pos - 1200):pos + 900])


if __name__ == "__main__":
    main()

"""Sonda de un solo uso: qué hay dentro del payload embebido de dpm.lol.

La página de equipo de dpm.lol es un Next.js con React Server Components: el HTML
lleva el estado serializado en llamadas `self.__next_f.push([1,"..."])`. Ahí van
los datos reales (gameName, tagLine, platform, rol...), no solo los nombres
pintados. Esta sonda los saca para decidir si sirven como segunda vía de
extracción, independiente de las clases de Tailwind.
"""

import json
import re
import sys

import cloudscraper


def extraer_payload(html: str) -> str:
    """Reconstruye el flujo RSC concatenando todos los `__next_f.push`."""
    trozos = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)', html)
    return "".join(json.loads(f'"{t}"') for t in trozos)


def main() -> None:
    equipos = sys.argv[1:] or ["G2", "FNC"]
    scraper = cloudscraper.create_scraper(browser={"custom": "Chrome"}, delay=10)

    for equipo in equipos:
        url = f"https://dpm.lol/esport/soloq/teams/{equipo}"
        resp = scraper.get(url, timeout=25)
        print(f"\n=== {equipo}: HTTP {resp.status_code} ===")
        if resp.status_code != 200:
            continue

        flujo = extraer_payload(resp.text)
        print(f"payload reconstruido: {len(flujo)} caracteres")

        objetos = re.findall(r'\{"gameName":.*?\}', flujo)
        print(f"objetos con gameName: {len(objetos)}")
        for obj in objetos[:3]:
            print(f"  crudo: {obj[:400]}")

        for campo in (
            "gameName", "tagLine", "platform", "puuid", "role", "position",
            "team", "displayName", "summonerName", "tier", "lp", "rank",
        ):
            valores = sorted(set(re.findall(rf'"{campo}":"?([^",}}]{{1,40}})', flujo)))
            if valores:
                print(f"  {campo} ({len(valores)}): {valores[:12]}")


if __name__ == "__main__":
    main()

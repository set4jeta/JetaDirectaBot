"""Sonda de un solo uso: comprueba cómo salen los nombres de la página de equipo.

Se ejecuta a mano cuando se sospecha que dpm.lol cambió el HTML. No forma parte
del bot ni de ninguna tarea de fondo.
"""

import re
import sys

import cloudscraper
from bs4 import BeautifulSoup

SELECTOR_ACTUAL = "font-semibold text-bm lg:text-bxl"


def main() -> None:
    equipos = sys.argv[1:] or ["G2 Esports", "Fnatic"]
    scraper = cloudscraper.create_scraper(browser={"custom": "Chrome"}, delay=10)

    for equipo in equipos:
        url = f"https://dpm.lol/esport/soloq/teams/{equipo}"
        try:
            resp = scraper.get(url, timeout=25)
        except Exception as exc:
            print(f"{equipo}: ERROR {type(exc).__name__}: {exc}")
            continue

        print(f"{equipo}: HTTP {resp.status_code}, {len(resp.text)} bytes")
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        exacto = [
            s.get_text(strip=True)
            for s in soup.find_all("span", class_=SELECTOR_ACTUAL)
        ]
        print(f"  selector actual  -> {sorted(set(exacto))}")

        semi = [
            s.get_text(strip=True)
            for s in soup.find_all("span", class_=lambda c: c and "font-semibold" in c)
        ]
        print(f"  solo font-semibold ({len(semi)}) -> {sorted(set(semi))[:25]}")

        for etiqueta, patron in (
            ("gameName escapado", r'\\"gameName\\":\\"([^"\\]+)'),
            ("gameName plano", r'"gameName":"([^"]+)"'),
            ("nickname", r'"nickname":"([^"]+)"'),
            ("name", r'"name":"([^"]{2,20})"'),
        ):
            encontrado = sorted(set(re.findall(patron, resp.text)))
            if encontrado:
                print(f"  {etiqueta} ({len(encontrado)}) -> {encontrado[:25]}")

        print(f"  __NEXT_DATA__: {bool(soup.find('script', id='__NEXT_DATA__'))}")
        print(f"  next_f pushes: {resp.text.count('self.__next_f.push')}")


if __name__ == "__main__":
    main()

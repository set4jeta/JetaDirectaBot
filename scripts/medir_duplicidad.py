"""Mide cuanto texto se repite entre las paginas de la web ya generada.

Por que existe
--------------
Google castigo en la actualizacion de spam de agosto de 2026 el
`scaled content abuse`: muchas paginas generadas por plantilla donde cada una
no aporta nada que las otras no tengan. Tenemos 20 paginas de liga hechas con
la misma plantilla, asi que la pregunta no es teorica: hace falta el numero.

Como lo mide
------------
Extrae el texto visible de cada HTML (sin etiquetas, sin scripts), lo parte en
frases y calcula:

1. Que porcentaje de las frases de cada pagina aparece **identica** en otra.
2. Que frases son las mas repetidas del sitio, con en cuantas paginas salen.

El umbral que uso: por encima del 50 % de frases compartidas, la pagina es
sospechosa de ser relleno. Entre 30 y 50 %, aceptable si lo compartido es
navegacion y legal. Por debajo de 30 %, bien.

Uso:
    python scripts/medir_duplicidad.py [carpeta_web]
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict

WEB = "C:/jetabot res 8/JetaDirectaBot/web"

_SCRIPTS = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
_ETIQUETAS = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"\s+")


def texto_visible(html: str) -> str:
    """El texto que un lector ve, sin marcado ni JSON-LD."""
    limpio = _SCRIPTS.sub(" ", html)
    limpio = _ETIQUETAS.sub(" ", limpio)
    for ent, car in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                     ("&gt;", ">"), ("&quot;", '"'), ("&#x27;", "'")):
        limpio = limpio.replace(ent, car)
    return _ESPACIOS.sub(" ", limpio).strip()


def frases(texto: str) -> list[str]:
    """Corta por punto, interrogacion y salto logico. Descarta lo muy corto.

    El minimo de 40 caracteres deja fuera 'Inicio', 'Ligas', los nombres de
    equipo y las celdas de tabla, que se repiten por fuerza y no son contenido.
    """
    trozos = re.split(r"(?<=[.!?])\s+|\s{2,}|·", texto)
    return [t.strip() for t in trozos if len(t.strip()) >= 40]


def main(argv: list[str]) -> int:
    carpeta = argv[1] if len(argv) > 1 else WEB
    paginas = sorted(f for f in os.listdir(carpeta) if f.endswith(".html"))
    if not paginas:
        print(f"No hay HTML en {carpeta}")
        return 1

    por_pagina: dict[str, list[str]] = {}
    for nombre in paginas:
        with open(os.path.join(carpeta, nombre), encoding="utf-8") as f:
            por_pagina[nombre] = frases(texto_visible(f.read()))

    # En cuantas paginas distintas aparece cada frase.
    presencia: Counter[str] = Counter()
    for fs in por_pagina.values():
        for frase in set(fs):
            presencia[frase] += 1

    print(f"{len(paginas)} paginas analizadas en {carpeta}\n")
    print(f"{'pagina':<44} {'frases':>7} {'compart.':>9} {'%':>6}")
    print("-" * 70)

    peores: list[tuple[float, str]] = []
    for nombre, fs in por_pagina.items():
        unicas = set(fs)
        compartidas = sum(1 for f in unicas if presencia[f] > 1)
        pct = 100.0 * compartidas / len(unicas) if unicas else 0.0
        peores.append((pct, nombre))
        print(f"{nombre:<44} {len(unicas):>7} {compartidas:>9} {pct:>5.1f}%")

    peores.sort(reverse=True)
    print("\n== las 5 paginas con mas texto compartido ==")
    for pct, nombre in peores[:5]:
        print(f"  {pct:5.1f}%  {nombre}")

    print("\n== frases presentes en 5 o mas paginas ==")
    repetidas = [(n, f) for f, n in presencia.items() if n >= 5]
    repetidas.sort(reverse=True)
    for n, frase in repetidas[:30]:
        corte = frase[:110] + ("..." if len(frase) > 110 else "")
        print(f"  x{n:<3} {corte}")

    # Las paginas de liga aparte: son la plantilla repetida 20 veces y el
    # numero que importa es cuanto se parecen entre ellas, no al resto.
    ligas = {n: f for n, f in por_pagina.items() if n.startswith("liga-")}
    if len(ligas) > 1:
        pres_liga: Counter[str] = Counter()
        for fs in ligas.values():
            for frase in set(fs):
                pres_liga[frase] += 1
        totales = []
        for nombre, fs in ligas.items():
            unicas = set(fs)
            comp = sum(1 for f in unicas if pres_liga[f] > 1)
            totales.append(100.0 * comp / len(unicas) if unicas else 0.0)
        media = sum(totales) / len(totales)
        print(f"\n== solo entre las {len(ligas)} paginas de liga ==")
        print(f"  media de frases compartidas entre ellas: {media:.1f}%")
        print("  frases en 15+ paginas de liga:")
        for frase, n in pres_liga.most_common(40):
            if n >= 15:
                corte = frase[:100] + ("..." if len(frase) > 100 else "")
                print(f"    x{n:<3} {corte}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Cosecha publicaciones de SEO desde X (Twitter) para construir conocimiento propio.

Por que no se usa `twitter search`:
    El subcomando `search` de twitter-cli 0.8.5 devuelve HTTP 404 contra el
    endpoint interno de X (el GraphQL de busqueda cambio de id). En cambio
    `user-posts` si funciona. Ademas, leer los timelines de referentes da
    mucha mejor senal que buscar la palabra "SEO", que esta saturada de spam
    de agencias y de bots de "SEO services $5".

Requiere las cookies de la sesion de Opera GX en el entorno:
    source scripts/x_sesion.sh

Uso:
    python scripts/cosechar_seo_x.py            # cosecha todas las cuentas
    python scripts/cosechar_seo_x.py --lote 1   # solo el primer lote
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any

VENV = "C:/Users/Chino/.workbuddy-ai/binaries/python/envs/default"
TWITTER = f"{VENV}/Scripts/twitter.exe"
SALIDA = "C:/jetabot res 8/JetaDirectaBot/docs/seo/_datos"

# Referentes en ingles. El usuario quiere orientar la web al publico anglo
# porque tiene mas capacidad de pago, asi que este bloque es el mas grande.
CUENTAS_EN = [
    "randfish",         # Rand Fishkin, ex-Moz, SparkToro
    "aleyda",           # Aleyda Solis, SEO internacional y hreflang
    "glenngabe",        # Glenn Gabe, analisis de actualizaciones de algoritmo
    "rustybrick",       # Barry Schwartz, Search Engine Roundtable
    "lilyraynyc",       # Lily Ray, E-E-A-T y calidad
    "Kevin_Indig",      # Kevin Indig, Growth Memo
    "patrickstox",      # Patrick Stox, Ahrefs
    "iPullRank",        # Mike King, SEO tecnico y busqueda con IA
    "searchliaison",    # cuenta oficial de Google Search
    "cyrusshepard",     # Cyrus Shepard, Zyppy
    "MarieHaynes",      # Marie Haynes, calidad y actualizaciones
    "willreynolds",     # Wil Reynolds, Seer Interactive
    "dan_shure",        # Dan Shure, Evolving SEO
    "ryanjones",        # Ryan Jones, SEO tecnico
    "methode",          # Gary Illyes, Google
    "JonHenshaw",       # Jon Henshaw, Coywolf
    "TomekRudzki",      # Tomek Rudzki, indexacion (Onely)
    "bartoszgoralew",   # Bartosz Goralewicz, JavaScript SEO
    "eliasdabbas",      # Elias Dabbas, SEO con datos
    "AndrewOptimisey",  # Andrew Charlton, SEO tecnico
]

# Referentes en espanol. Sirven para la version en castellano y para entender
# que consultas usa el publico hispano.
#
# Ojo: X limita por ventana de tiempo, no por cuenta. Tras ~20 cuentas seguidas
# empieza a devolver `rate_limited` para todo. Si eso pasa, reintenta con
# `--cuentas a,b,c --espera 25 --fusionar` en vez de repetir el lote entero.
CUENTAS_ES = [
    "mjcachon",         # MJ Cachon, SEO tecnico y query fan-out
    "luismvillanueva",  # Luis M Villanueva
    "ikhuerta",         # Inaki Huerta, IKAUE
    "natzir9",          # Natzir Turrado, analitica y SEO
    "JuanGonzalezVil",  # Juan Gonzalez Villa, USEO
    "dean_romero",      # Dean Romero, Blogger3cero
    "Fernando_Angulo",  # Fernando Angulo, Semrush
    "alvarosaezz",      # Alvaro Saez, SEO
    "Chuiso",           # Chuiso, blackhat
    "seomanuel",        # Manuel Marino
    "lopezaira",        # Aira, agencia
    "sicoinformatica",  # Alvaro Peña
]

# Palabras que indican que un post trae informacion util y no autopromocion.
SENALES = (
    "google", "serp", "ranking", "rank", "index", "crawl", "backlink",
    "keyword", "schema", "structured data", "core web vitals", "canonical",
    "hreflang", "sitemap", "robots.txt", "algorithm", "update", "e-e-a-t",
    "eeat", "llm", "chatgpt", "aio", "ai overview", "geo", "aeo", "traffic",
    "ctr", "impressions", "search console", "gsc", "programmatic",
    "internal link", "title tag", "meta description", "content",
    "indexacion", "enlazado", "contenido", "busqueda", "consulta",
    "posicionamiento", "arana", "rastreo", "etiqueta",
)


def cosechar(cuenta: str, maximo: int = 40) -> list[dict[str, Any]]:
    """Descarga los ultimos posts de una cuenta. Devuelve [] si algo falla."""
    try:
        proc = subprocess.run(
            [TWITTER, "user-posts", cuenta, "-n", str(maximo), "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        print(f"  {cuenta}: timeout", flush=True)
        return []

    salida = proc.stdout or ""
    inicio = salida.find("{")
    if inicio < 0:
        print(f"  {cuenta}: sin JSON en la salida", flush=True)
        return []

    try:
        datos = json.loads(salida[inicio:])
    except json.JSONDecodeError as exc:
        print(f"  {cuenta}: JSON invalido ({exc})", flush=True)
        return []

    if not datos.get("ok"):
        err = (datos.get("error") or {}).get("code", "?")
        print(f"  {cuenta}: error {err}", flush=True)
        return []

    return datos.get("data") or []


def util(post: dict[str, Any]) -> bool:
    """Filtra ruido: retweets, posts sin senal tematica y cosas sin traccion."""
    if post.get("isRetweet"):
        return False
    texto = (post.get("text") or "").lower()
    if len(texto) < 60:
        return False
    if not any(s in texto for s in SENALES):
        return False
    m = post.get("metrics") or {}
    return (m.get("likes") or 0) >= 3 or (m.get("bookmarks") or 0) >= 2


def aplanar(post: dict[str, Any], idioma: str) -> dict[str, Any]:
    m = post.get("metrics") or {}
    return {
        "id": post.get("id"),
        "autor": (post.get("author") or {}).get("screenName"),
        "idioma_cuenta": idioma,
        "lang": post.get("lang"),
        "fecha": post.get("createdAtISO"),
        "texto": post.get("text"),
        "likes": m.get("likes") or 0,
        "rts": m.get("retweets") or 0,
        "guardados": m.get("bookmarks") or 0,
        "vistas": m.get("views") or 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote", type=int, default=0, help="1=EN, 2=ES, 0=ambos")
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument(
        "--cuentas",
        default="",
        help="lista separada por comas; sustituye al lote (para reintentos)",
    )
    ap.add_argument(
        "--espera",
        type=float,
        default=1.5,
        help="segundos entre cuentas. Subir a 20+ si X devuelve rate_limited",
    )
    ap.add_argument(
        "--fusionar",
        action="store_true",
        help="anade al JSON existente en vez de reemplazarlo (deduplica por id)",
    )
    args = ap.parse_args()

    if not os.environ.get("TWITTER_AUTH_TOKEN"):
        print("Falta TWITTER_AUTH_TOKEN. Ejecuta: source scripts/x_sesion.sh")
        return 1

    os.makedirs(SALIDA, exist_ok=True)
    grupos: list[tuple[str, list[str]]] = []
    if args.cuentas:
        # Reintento manual: el idioma se toma del lote para saber en que
        # fichero escribir. X limita por ventana de tiempo, no por cuenta, asi
        # que un lote entero puede morir y hay que repescarlo por partes.
        idioma = "es" if args.lote == 2 else "en"
        grupos.append((idioma, [c.strip() for c in args.cuentas.split(",") if c.strip()]))
    else:
        if args.lote in (0, 1):
            grupos.append(("en", CUENTAS_EN))
        if args.lote in (0, 2):
            grupos.append(("es", CUENTAS_ES))

    total_bruto = 0
    for idioma, cuentas in grupos:
        acumulado: list[dict[str, Any]] = []
        print(f"== bloque {idioma}: {len(cuentas)} cuentas ==", flush=True)
        for cuenta in cuentas:
            posts = cosechar(cuenta, args.max)
            total_bruto += len(posts)
            buenos = [aplanar(p, idioma) for p in posts if util(p)]
            acumulado.extend(buenos)
            print(f"  {cuenta}: {len(posts)} leidos, {len(buenos)} utiles", flush=True)
            time.sleep(args.espera)

        ruta = os.path.join(SALIDA, f"x_seo_{idioma}.json")
        if args.fusionar and os.path.exists(ruta):
            try:
                with open(ruta, encoding="utf-8") as f:
                    previos = json.load(f)
            except (OSError, json.JSONDecodeError):
                previos = []
            vistos = {p["id"] for p in acumulado}
            acumulado.extend(p for p in previos if p.get("id") not in vistos)

        acumulado.sort(key=lambda p: p["likes"] + p["guardados"] * 2, reverse=True)
        with open(ruta + ".tmp", "w", encoding="utf-8") as f:
            json.dump(acumulado, f, ensure_ascii=False, indent=1)
        os.replace(ruta + ".tmp", ruta)
        print(f"-> {len(acumulado)} posts utiles en {ruta}", flush=True)

    print(f"total bruto leido: {total_bruto}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Puente entre el bot y la web estática: genera web/api/live.json.

Por qué existe este fichero (y no se toca generar_web.py)
----------------------------------------------------------
`scripts/generar_web.py` ya genera toda la web estática (HTML, sitemap, OG…)
desde el código del bot. Pero la web "en vivo" —la tira de equipos y el feed
de «partidas recientes» que pinta live.js en index.html— necesita un JSON
ligero que el navegador pueda pedir sin exponer la API de Riot.

Ese JSON es `web/api/live.json` y se genera AQUÍ, en un script aparte, por
tres razones prácticas:

1. Separación de ciclos. El generador de HTML se corre cuando cambia el
   catálogo (ligas/planes). El live.json se regenera en cuanto el bot publica
   un aviso, o periódicamente. No tienen por qué compartir ejecución.
2. No pisar lo ya hecho. `generar_web.py` son 1000+ líneas y el usuario lo
   valora; meterle el live.json habría sido duplicar lógica o romper algo.
3. Robustez. Si el bot no corre (despliegue estático en GitHub Pages), este
   script simplemente produce un live.json con avisos vacíos y la lista de
   equipos; live.js lo pinta igual y no rompe la página.

Qué lee
-------
* tracking/soloq/avisos.jsonl  — el registro de avisos (lo escribe
  tracking/soloq/avisos_log.py). Formato documentado en ese módulo.
* tracking/soloq/accounts_from_teams.json — la plantilla de jugadores; de ahí
  se saca la lista de equipos únicos para la tira de logos.

Qué escribe
-----------
web/api/live.json con la forma que espera web/live.js:

    {
      "generado": 1690000000,
      "total_avisos": 123,
      "avisos": [ {...registrar... } x N ],   # crudos, live.js los recorta
      "equipos": [ {"code","nombre","imagen"} ]
    }

Uso
---
    python scripts/bridge_web.py            # escribe web/api/live.json
    python scripts/bridge_web.py --tope 100  # más avisos en el volcado

No levanta nunca: un fallo al leer un fichero produce un JSON vacío válido, no
una excepción. El contrato con live.js es «JSON o nada», y nada lo maneja.
"""

from __future__ import annotations

import json
import os
import time

log = None  # se importa perezosamente para no arrastrar el paquete si falla


def _logger():
    global log
    if log is None:
        try:
            from utils.logger import get_logger

            log = get_logger("scripts.bridge_web")
        except Exception:  # noqa: BLE001 — el bridge funciona sin logger
            log = None
    return log


RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVISOS_JSONL = os.path.join(RAIZ, "tracking", "soloq", "avisos.jsonl")
ACCOUNTS = os.path.join(RAIZ, "tracking", "soloq", "accounts_from_teams.json")
TEAMS_IMG = os.path.join(RAIZ, "web", "img", "teams")
SALIDA = os.path.join(RAIZ, "web", "api", "live.json")

TOPE_AVISOS = 50
EXT_LOGO = (".webp", ".png", ".svg")


def leer_avisos(tope: int = TOPE_AVISOS) -> list[dict]:
    """Últimos avisos del JSONL, del más reciente al más antiguo.

    Mantiene la misma lógica defensiva que tracking.soloq.avisos_log.leer:
    una línea a medias por un SIGTERM no aborta la lectura. Devuelve los
    objetos crudos tal cual los escribió avisos_log.registrar, porque live.js
    consume exactamente esos campos (jugador, equipo, liga, campeon, rango,
    servidor, ts).
    """
    try:
        with open(AVISOS_JSONL, encoding="utf-8") as fh:
            lineas = fh.readlines()
    except OSError:
        return []
    salida: list[dict] = []
    for linea in reversed(lineas):
        linea = linea.strip()
        if not linea:
            continue
        try:
            dato = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(dato, dict):
            salida.append(dato)
        if len(salida) >= tope:
            break
    return salida


def _logo_para(code: str) -> str | None:
    """Ruta relativa (desde la web) del logo si existe, si no None."""
    for ext in EXT_LOGO:
        ruta = os.path.join(TEAMS_IMG, f"{code}{ext}")
        if os.path.isfile(ruta):
            return f"img/teams/{code}{ext}"
    return None


def equipos() -> list[dict]:
    """Equipos únicos seguidos, para la tira de logos de index.html.

    El fichero de cuentas es una lista de jugadores; cada uno trae `team`
    (código, p.ej. FNC) y `team_name` (nombre, p.ej. Fnatic). Agrupamos por
    código y enlazamos el logo si está en web/img/teams.
    """
    try:
        with open(ACCOUNTS, encoding="utf-8") as fh:
            jugadores = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(jugadores, list):
        return []
    vistos: dict[str, dict] = {}
    for p in jugadores:
        if not isinstance(p, dict):
            continue
        code = str(p.get("team") or "").strip().upper()
        if not code or code in vistos:
            continue
        vistos[code] = {
            "code": code,
            "nombre": p.get("team_name") or code,
            "imagen": _logo_para(code),
        }
    return list(vistos.values())


def generar(tope: int = TOPE_AVISOS) -> dict:
    """Construye el diccionario live.json."""
    avisos = leer_avisos(tope)
    return {
        "generado": int(time.time()),
        "total_avisos": len(avisos),
        "avisos": avisos,
        "equipos": equipos(),
    }


def main(tope: int = TOPE_AVISOS) -> int:
    datos = generar(tope)
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    lg = _logger()
    if lg:
        lg.info(
            "live.json: %d equipos, %d avisos -> %s",
            len(datos["equipos"]),
            datos["total_avisos"],
            os.path.relpath(SALIDA, RAIZ),
        )
    print(
        f"live.json escrito: {len(datos['equipos'])} equipos, "
        f"{datos['total_avisos']} avisos -> {SALIDA}"
    )
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Genera web/api/live.json")
    parser.add_argument(
        "--tope", type=int, default=TOPE_AVISOS,
        help="Número máximo de avisos a incluir en el volcado",
    )
    args = parser.parse_args()
    raise SystemExit(main(args.tope))

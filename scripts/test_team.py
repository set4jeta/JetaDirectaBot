"""Prueba de `!team` sin Discord: usa las funciones reales del comando.

Comprueba que el comando enseña la cuenta con **más Elo** de cada jugador, que
el caché evita pedir a la API lo que ya está fresco, y que el mensaje se parte
correctamente.

No se copia la lógica: se importa `_mejor_cuenta_de` del propio
`core/register_team_commands.py` y `partir` de `core/responder.py`, así que si el
comando cambia, la prueba lo refleja.

`_partir_mensaje` vivía en `register_team_commands`; al unificar prefijo y slash
pasó a ser `Respuesta.enviar_partido`, que delega en `core.responder.partir`.
Esta prueba se quedó importando el nombre viejo y fallaba con `ImportError`
**antes** de comprobar nada, así que el comando entero estaba sin cobertura sin
que el resultado del test lo dijera.

Uso:
    python scripts/test_team.py            # un equipo de ejemplo
    python scripts/test_team.py NAVI TH    # los equipos que quieras
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import config  # noqa: E402
from apis.riot_client import close_riot_client, get_riot_client  # noqa: E402
from core import rank_store  # noqa: E402
from core.register_team_commands import (  # noqa: E402
    ROLE_ORDER,
    _mejor_cuenta_de,
)
from core.responder import partir  # noqa: E402
from tracking.soloq.accounts_io import load_tracked_accounts  # noqa: E402
from utils.rank_utils import (  # noqa: E402
    es_rank_valido,
    formatear_rank,
    valor_rank,
)


def _cuenta_str(cuenta) -> str:
    gn = cuenta.riot_id.get("game_name", "")
    tl = cuenta.riot_id.get("tag_line", "")
    return f"{gn}#{tl}" if gn else "(sin cuenta)"


async def probar_equipo(tag: str) -> tuple[int, int]:
    """Devuelve (jugadores, aciertos de 'mejor cuenta' verificados)."""
    jugadores = [
        p for p in load_tracked_accounts()
        if p.team and p.team.lower() == tag.lower()
    ]
    if not jugadores:
        print(f"   [AVISO] no hay jugadores para {tag.upper()}")
        return 0, 0

    jugadores.sort(
        key=lambda p: ROLE_ORDER.index(p.role) if p.role in ROLE_ORDER else len(ROLE_ORDER)
    )

    semaforo = asyncio.Semaphore(config.TRACKER_CONCURRENCY)
    t0 = time.perf_counter()
    resultados = await asyncio.gather(
        *[_mejor_cuenta_de(j, semaforo) for j in jugadores]
    )
    duracion = time.perf_counter() - t0

    verificados = 0
    for jugador, (cuenta, rango, total) in zip(jugadores, resultados):
        extra = f" · mejor de {total}" if total > 1 else ""
        print(f"   {jugador.role or '?':<8} {jugador.name:<12} "
              f"{_cuenta_str(cuenta):<28} {formatear_rank(rango)}{extra}")

        if total > 1:
            # La elegida debe ser >= que todas las demás del mismo jugador.
            elegido = valor_rank(rango)
            otros = []
            for c in jugador.accounts:
                if c is cuenta:
                    continue
                r = rank_store.obtener_crudo(getattr(c, "puuid", "") or "")
                otros.append((_cuenta_str(c), valor_rank(r), formatear_rank(r)))
            peor = [o for o in otros if o[1] > elegido]
            if peor:
                print(f"      [ERROR] hay una cuenta mejor sin elegir: {peor}")
            else:
                verificados += 1
                detalle = ", ".join(f"{n}={t}" for n, _v, t in otros)
                if detalle:
                    print(f"      otras: {detalle}")

    print(f"   -> {len(jugadores)} jugadores en {duracion:.2f}s")
    return len(jugadores), verificados


async def main() -> int:
    equipos = sys.argv[1:] or ["NAVI", "TH", "G2"]

    print("=" * 74)
    print("PRUEBA DE !team")
    print("=" * 74)

    st = rank_store.estado()
    print(f"   histórico: {st['entradas']} entradas ({st['frescas']} frescas)")
    print(f"   validez del caché: {config.RANK_CACHE_MAX_AGE}s "
          f"· concurrencia {config.TRACKER_CONCURRENCY}")

    client = await get_riot_client()
    peticiones_inicio = client.stats["requests"]

    total_jugadores = 0
    total_verificados = 0
    for tag in equipos:
        print()
        print(f"-- {tag.upper()} " + "-" * (70 - len(tag)))
        j, v = await probar_equipo(tag)
        total_jugadores += j
        total_verificados += v

    peticiones = client.stats["requests"] - peticiones_inicio

    # Segunda pasada: con el caché caliente no debería pedir nada.
    print()
    print("-- segunda pasada (caché) " + "-" * 48)
    antes = client.stats["requests"]
    t0 = time.perf_counter()
    for tag in equipos:
        jugadores = [p for p in load_tracked_accounts()
                     if p.team and p.team.lower() == tag.lower()]
        sem = asyncio.Semaphore(config.TRACKER_CONCURRENCY)
        await asyncio.gather(*[_mejor_cuenta_de(j, sem) for j in jugadores])
    print(f"   {time.perf_counter() - t0:.2f}s "
          f"· {client.stats['requests'] - antes} peticiones a Riot")

    # Partido de mensajes largos.
    print()
    print("-- partido de mensajes " + "-" * 51)
    texto = "\n".join(f"**Jugador {i}** (cuenta#EUW) - Master I (500 LP)" for i in range(90))
    trozos = partir(texto)
    print(f"   {len(texto)} caracteres -> {len(trozos)} trozos "
          f"(máx {max(len(t) for t in trozos)})")
    ok_limite = all(len(t) <= 1900 for t in trozos)
    ok_contenido = sum(t.count("**Jugador") for t in trozos) == 90

    print()
    print("=" * 74)
    print("RESUMEN")
    print("=" * 74)
    print(f"   jugadores mostrados        : {total_jugadores}")
    print(f"   multi-cuenta verificados   : {total_verificados}")
    print(f"   peticiones primera pasada  : {peticiones}")
    print(f"   troceado dentro del límite : {'sí' if ok_limite else 'NO'}")
    print(f"   ninguna línea perdida      : {'sí' if ok_contenido else 'NO'}")
    print(f"   riot: {client.rate_limit_report()}")

    await close_riot_client()
    return 0 if (ok_limite and ok_contenido and total_jugadores) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

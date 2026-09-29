"""Prueba headless del pipeline de tracking, sin conectar a Discord.

Comprueba lo que antes fallaba:

1. `ActiveGameTracker.run()` TERMINA. Antes era un `while True` dentro de un
   `tasks.loop`, así que no devolvía nunca. Aquí se mide con timeout: si la
   pasada no acaba en 90 s, la prueba falla.
2. Se detectan las partidas en curso reales.
3. Se respetan los PUUIDs marcados como stale.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from tracking.soloq import avisos_log, user_config  # noqa: E402
from tracking.soloq.active_game_checker import ActiveGameTracker  # noqa: E402
from apis.riot_client import close_riot_client  # noqa: E402

TIMEOUT = 90


class _UsuarioFalso:
    """Usuario de DM de mentira: acepta el envío y no hace nada."""

    def __init__(self, user_id: int):
        self.id = user_id

    async def send(self, **_kw) -> None:
        return None


class FakeBot:
    """Sustituye al bot de Discord: no hay canales, así que no envía nada.

    `get_user`/`fetch_user` están desde el 29-09-2026 y no son decorativos: la
    rama de avisos por DM los usa, y sin ellos la pasada moría con
    `AttributeError: 'FakeBot' object has no attribute 'get_user'` en cuanto
    hubiera **un solo** usuario con los DM activados. Se veía como un fallo del
    tracker y era del doble de prueba. `get_user` devuelve `None` a propósito,
    que es lo que hace el bot real cuando el usuario no está en la caché —el
    caso normal de quien se suscribe por DM—, para que se ejerza el `fetch_user`.
    """

    def get_channel(self, channel_id):
        return None

    def get_user(self, user_id):
        return None

    async def fetch_user(self, user_id):
        return _UsuarioFalso(user_id)


async def main() -> int:
    # Esta prueba corre una pasada **real** contra la API de Riot, así que toca
    # dos ficheros de estado de verdad y hay que desviarlos antes de empezar:
    #
    # * `users_config.json` — los avisos por DM escriben en él al entregar (marcan
    #   el estado del DM). Apuntando al fichero real, la pasada de prueba
    #   modificaba la configuración de usuarios de verdad y el resultado dependía
    #   de quién estuviera suscrito ese día.
    # * `avisos.jsonl` — es el registro de avisos **publicados**, y lo lee la web
    #   para pintar la página de avisos. La prueba lo escribía, así que después de
    #   ejecutarla `avisos.html` publicaba un aviso que nadie había recibido (y
    #   `test_web` empezaba a fallar por eso, sin relación aparente). Pasó el
    #   29-09-2026 y costó un rato entender de dónde salía esa línea.
    #
    # Se redirigen a un directorio temporal vacío: sin suscriptores no hay DM, que
    # es justo lo que esta prueba quiere medir (que la pasada termina, detecta
    # partidas y respeta los stale), y el estado real queda intacto.
    with tempfile.TemporaryDirectory() as tmp:
        user_config.CONFIG_PATH = os.path.join(tmp, "users.json")
        avisos_log.RUTA = os.path.join(tmp, "avisos.jsonl")
        return await _pasada()


async def _pasada() -> int:
    print("=" * 70)
    print("PRUEBA HEADLESS DEL TRACKER")
    print("=" * 70)

    bot = FakeBot()
    tracker = ActiveGameTracker(bot)

    cuentas = sum(len(p.accounts) for p in tracker._players)
    stale = sum(1 for p in tracker._players for a in p.accounts if a.stale)
    print(f"   jugadores trackeados : {len(tracker._players)}")
    print(f"   cuentas              : {cuentas} (de ellas {stale} marcadas stale)")

    print()
    print(f"   Ejecutando run() con timeout de {TIMEOUT}s...")
    print("   (con el codigo antiguo esto no habria terminado nunca)")
    print()

    started = time.perf_counter()
    try:
        stats = await asyncio.wait_for(tracker.run(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - started
        print(f"   [FALLO] run() no termino tras {elapsed:.0f}s -> sigue el bug del while True")
        await close_riot_client()
        return 1

    elapsed = time.perf_counter() - started
    print()
    print("=" * 70)
    print("RESULTADO DE LA PASADA")
    print("=" * 70)
    print(f"   termino en           : {stats.duracion:.2f}s  (timeout era {TIMEOUT}s)")
    print(f"   cuentas revisadas    : {stats.revisadas}")
    print(f"   stale omitidas       : {stats.omitidas_stale}")
    print(f"   partidas detectadas  : {stats.en_partida}")
    print(f"   notificadas          : {stats.notificadas}  (0 es normal: bot simulado sin canales)")
    print(f"   marcadas stale nuevas: {stats.marcadas_stale}")
    print(f"   errores              : {stats.errores}")

    if stats.detalle:
        print()
        print("   partidas en curso detectadas:")
        for line in stats.detalle:
            print(f"     {line}")

    print()
    print("=" * 70)
    print("SEGUNDA PASADA (comprueba que es repetible y usa caché)")
    print("=" * 70)
    t0 = time.perf_counter()
    try:
        stats2 = await asyncio.wait_for(tracker.run(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        print("   [FALLO] la segunda pasada no termino")
        await close_riot_client()
        return 1
    print(f"   termino en {time.perf_counter() - t0:.2f}s · {stats2.en_partida} partidas")

    await close_riot_client()

    print()
    if stats.errores > 0:
        print(f"   [AVISO] {stats.errores} cuentas dieron error (revisa el log en DEBUG)")
    if stats.marcadas_stale > 0:
        print(f"   [AVISO] {stats.marcadas_stale} PUUIDs invalidos marcados como stale")
    print("   [OK] run() devuelve el control: el tasks.loop puede gobernar la cadencia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

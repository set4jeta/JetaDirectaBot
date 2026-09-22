"""¿Por qué salen 429 si los límites de la key son 500:10 y 3000:10?

El limitador local se "sincroniza" con lo que Riot reporta en
`X-App-Rate-Limit-Count`. Pero ese header es una **foto del momento en que Riot
procesó esa petición**, y las respuestas llegan desordenadas. Si una respuesta
tardía trae un contador bajo, `_Window.sync_count` hace:

    missing = count - len(self.hits)      # negativo
    for _ in range(-missing):
        self.hits.popleft()               # BORRA nuestras propias marcas

...y el limitador se cree con cupo libre que no tiene. Aquí se mide cuánto
cupo se regala, sin tocar la red.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apis.riot_client import _RateLimiter, _Window


def escenario_1() -> None:
    """500 peticiones lanzadas; llega una respuesta con el contador en 20."""
    w = _Window(500, 10.0)
    ahora = time.monotonic()
    for _ in range(500):
        w.record(ahora)
    print("escenario 1: ráfaga de 500 en la ventana de 10 s")
    print(f"   hits antes de sincronizar : {len(w.hits)}")
    print(f"   espera antes             : {w.wait_time(ahora):.2f}s  (debería ser > 0)")

    # Respuesta que salió cuando Riot llevaba contadas 20.
    w.sync_count(20, ahora)
    print(f"   hits después             : {len(w.hits)}")
    print(f"   espera después           : {w.wait_time(ahora):.2f}s")
    print(f"   >>> cupo regalado        : {500 - len(w.hits)} peticiones\n")


def escenario_2() -> None:
    """Lo mismo por el camino real: cabeceras de Riot en desorden."""
    limitador = _RateLimiter(((500, 10.0), (30000, 600.0)))
    ahora = time.monotonic()
    for w in limitador.windows:
        for _ in range(480):
            w.record(ahora)

    print("escenario 2: 480 en vuelo y llegan respuestas desordenadas")
    print(f"   espera inicial           : {max(w.wait_time(ahora) for w in limitador.windows):.2f}s")

    # Tres respuestas con contadores dispares, como pasa de verdad.
    for count in (455, 12, 470):
        limitador.sync_counts([(count, 10.0), (count, 600.0)])
        v10 = limitador.windows[0]
        print(f"   tras 'Count: {count}:10'   -> hits={len(v10.hits):3d}  "
              f"espera={v10.wait_time(time.monotonic()):.2f}s")
    print()


def escenario_3() -> None:
    """Sin desorden: ¿la sincronización sirve para algo cuando va bien?"""
    w = _Window(500, 10.0)
    ahora = time.monotonic()
    for _ in range(10):
        w.record(ahora)
    print("escenario 3: la key la comparte otro proceso (contador alto)")
    print(f"   hits locales             : {len(w.hits)}")
    w.sync_count(490, ahora)
    print(f"   tras 'Count: 490:10'     : {len(w.hits)}  (subir SÍ es correcto)")
    print(f"   espera                   : {w.wait_time(ahora):.2f}s\n")


escenario_1()
escenario_2()
escenario_3()

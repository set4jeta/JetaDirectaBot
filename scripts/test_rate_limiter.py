"""Pruebas del limitador de `apis.riot_client`. No usa red.

Qué se comprueba y por qué
--------------------------
`_Window.sync_count` alinea nuestro conteo local con el que Riot reporta en
`X-App-Rate-Limit-Count`. La versión original también **restaba**: si una
respuesta traía un contador menor que nuestras marcas, hacía `popleft()`.

Eso regala cupo que no existe. `X-App-Rate-Limit-Count` es una foto del instante
en que Riot procesó *esa* petición, y con 12 corrutinas en vuelo las respuestas
llegan desordenadas: una que salió con el contador en 20 puede llegar después de
otra que iba por 480. Restar equivale a borrar peticiones que sí hicimos.

Medido antes del arreglo: 500 marcas en vuelo + una respuesta tardía con
`Count: 20:10` dejaba la ventana en 20 -> 480 peticiones de cupo fantasma.

Ejecutar:
    python scripts/test_rate_limiter.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RIOT_API_KEY", "test-no-se-usa-la-red")

from apis.riot_client import (  # noqa: E402
    _parse_rate_limit_header,
    _RateLimiter,
    _Window,
)

_fallos: list[str] = []
_ok = 0


def comprobar(condicion: bool, descripcion: str) -> None:
    global _ok
    if condicion:
        _ok += 1
        print(f"  ok   {descripcion}")
    else:
        _fallos.append(descripcion)
        print(f"  FALLA {descripcion}")


def test_ventana_basica() -> None:
    print("\nVentana deslizante")
    w = _Window(3, 10.0)
    comprobar(w.wait_time(100.0) == 0.0, "vacía: no hay que esperar")
    for t in (100.0, 100.5, 101.0):
        w.record(t)
    comprobar(w.wait_time(101.0) > 0, "llena: hay que esperar")
    comprobar(
        abs(w.wait_time(105.0) - 5.0) < 0.01,
        "la espera es lo que le falta a la marca más vieja (5.0s)",
    )
    comprobar(w.wait_time(111.0) == 0.0, "pasados los 10 s la ventana se vacía sola")


def test_sync_no_regala_cupo() -> None:
    """El bug medido: una respuesta tardía borraba marcas en vuelo."""
    print("\nsync_count con respuestas desordenadas")
    w = _Window(500, 10.0)
    ahora = 1_000.0
    for _ in range(500):
        w.record(ahora)
    comprobar(w.wait_time(ahora) > 0, "500 en vuelo: la ventana está llena")

    # Respuesta que Riot procesó cuando su contador iba por 20.
    w.sync_count(20, ahora)
    comprobar(
        len(w.hits) == 500,
        f"un 'Count: 20:10' tardío NO borra marcas (quedan {len(w.hits)}, deben ser 500)",
    )
    comprobar(w.wait_time(ahora) > 0, "y la ventana sigue llena: no se regala cupo")


def test_sync_si_sube() -> None:
    """Subir sí es correcto: la key puede estar compartida."""
    print("\nsync_count cuando Riot lleva más que nosotros")
    w = _Window(500, 10.0)
    ahora = 2_000.0
    for _ in range(10):
        w.record(ahora)
    w.sync_count(490, ahora)
    comprobar(len(w.hits) == 490, f"sube a 490 (tiene {len(w.hits)})")
    w.sync_count(495, ahora)
    comprobar(len(w.hits) == 495, "sigue subiendo con la foto más alta")
    w.sync_count(100, ahora)
    comprobar(len(w.hits) == 495, "una foto más baja no lo baja")


def test_sync_caduca() -> None:
    """El ajuste no se queda pegado: `prune` lo limpia con el tiempo."""
    print("\nel ajuste caduca solo")
    w = _Window(500, 10.0)
    w.sync_count(500, 3_000.0)
    comprobar(len(w.hits) == 500, "500 marcas sintéticas puestas")
    comprobar(w.wait_time(3_011.0) == 0.0, "11 s después la ventana está libre")


def test_limitador_multiventana() -> None:
    print("\nVarias ventanas a la vez")
    lim = _RateLimiter(((500, 10.0), (30000, 600.0)))
    comprobar(len(lim.windows) == 2, "dos ventanas activas")
    lim.sync_counts([(500, 10.0), (500, 600.0)])
    comprobar(
        [len(w.hits) for w in lim.windows] == [500, 500],
        "sync_counts reparte por segundos de ventana",
    )
    lim.sync_counts([(3, 10.0)])
    comprobar(
        len(lim.windows[0].hits) == 500,
        "una cabecera baja tampoco baja la ventana de 10 s",
    )


def test_update_limits_conserva_historico() -> None:
    print("\nupdate_limits")
    lim = _RateLimiter(((100, 10.0),))
    lim.windows[0].record(5_000.0)
    lim.update_limits(((500, 10.0), (30000, 600.0)))
    comprobar(lim.windows[0].limit == 500, "el límite nuevo se aplica")
    comprobar(
        len(lim.windows[0].hits) == 1,
        "y el histórico de la ventana del mismo tamaño se conserva",
    )


def test_parseo_cabeceras() -> None:
    print("\nParseo de cabeceras de Riot")
    comprobar(
        _parse_rate_limit_header("500:10,30000:600") == ((500, 10.0), (30000, 600.0)),
        "'500:10,30000:600' se parsea entero",
    )
    comprobar(_parse_rate_limit_header(None) == (), "None -> tupla vacía")
    comprobar(_parse_rate_limit_header("basura") == (), "basura -> tupla vacía")
    comprobar(
        _parse_rate_limit_header("20:1,x:y,100:120") == ((20, 1.0), (100, 120.0)),
        "un trozo corrupto no tira el resto",
    )


def main() -> int:
    for prueba in (
        test_ventana_basica,
        test_sync_no_regala_cupo,
        test_sync_si_sube,
        test_sync_caduca,
        test_limitador_multiventana,
        test_update_limits_conserva_historico,
        test_parseo_cabeceras,
    ):
        prueba()

    total = _ok + len(_fallos)
    print(f"\n{_ok}/{total} comprobaciones pasadas")
    if _fallos:
        print("Fallos:")
        for f in _fallos:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

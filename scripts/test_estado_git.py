"""El repo no puede volver a llevarse el estado del bot.

Por qué existe
--------------
El 18-10-2026 se perdió un buen rato persiguiendo un fantasma: el bot arrancaba
con «los rosters de siempre» (908 jugadores, sin Worlds) y parecía que la rama
`estado` estaba restaurando datos viejos. **No era ella.** `restaurar()` solo baja
lo que está en `ARCHIVOS`, y los rosters no están.

El culpable era `main`: `accounts_from_teams.json` (2,5 MB), `accounts.json`,
`ranked_data.json`, `puuid_cache.json` y varios caches **estaban commiteados**.
Render arranca con el disco vacío y hace checkout de `main`, así que se
encontraba con la foto del día en que alguien subió esos ficheros. La rama
`estado` solo tenía una copia vieja de lo mismo —un snapshot del repo de cuando
se creó—, que es lo que despistó.

Lo que se comprueba aquí
------------------------
1. Que el estado mutable **no está versionado**. Si alguien lo añade otra vez,
   esto falla.
2. Que el `.gitignore` lo tapa, para que no entre por accidente.
3. Que la división de papeles se respeta: la rama de estado guarda lo que **no**
   se puede reconstruir (`notified_games.json`, `tracked_matches.json`, los
   PUUIDs…) y **no** los ficheros grandes que se vuelven a bajar solos.
4. Que el bot arranca sin esos ficheros: los cargadores devuelven vacío en vez
   de romper. Es la condición para poder quitarlos del repo sin más.
5. Que la red de seguridad de las pruebas **restaura de verdad**. Antes usaba
   `git checkout --`, que no hace nada con ficheros sin seguimiento: avisaba de
   que restauraba y no restauraba nada.

Uso:
    python scripts/test_estado_git.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _estado_de_prueba import _ESTADO_MUTABLE, RAIZ, estado_limpio, estado_temporal  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def prueba_no_versionado() -> None:
    print("\n=== el estado mutable no está en el repo ===")
    for rel in _ESTADO_MUTABLE:
        ruta = RAIZ / rel
        versionado = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", rel],
            cwd=RAIZ, capture_output=True).returncode == 0
        ok(not versionado, f"{rel} no está versionado")
        if not versionado and ruta.exists():
            ok(True, f"{rel} sigue en disco (solo que ya no se sube)")


def prueba_ignorado() -> None:
    print("\n=== y el .gitignore lo tapa ===")
    for rel in _ESTADO_MUTABLE:
        ignorado = subprocess.run(
            ["git", "check-ignore", "-q", "--", rel],
            cwd=RAIZ, capture_output=True).returncode == 0
        ok(ignorado, f"{rel} está ignorado")


def prueba_reparto() -> None:
    """Qué va a la rama de estado y qué se reconstruye solo."""
    print("\n=== el reparto entre rama de estado y reconstrucción ===")
    from core.estado_remoto import ARCHIVOS

    # Lo que NO se puede reconstruir tiene que estar en la rama.
    para_no_perder = (
        "notified_games.json",
        "tracked_matches.json",
        "puuid_cache.json",
    )
    for rel in para_no_perder:
        ok(rel in ARCHIVOS, f"{rel} se guarda en la rama de estado")

    # Lo grande y reconstruible NO: serían commits de megas cada 5 minutos.
    para_no_subir = (
        "tracking/soloq/accounts_from_teams.json",
        "tracking/soloq/accounts.json",
        "ranked_data.json",
    )
    for rel in para_no_subir:
        ok(rel not in ARCHIVOS, f"{rel} no se sube (se reconstruye solo)")

    ok(estado_limpio(), "`estado_limpio()` está de acuerdo con todo lo anterior")


def prueba_arranca_sin_ellos() -> None:
    """El bot tiene que poder arrancar sin los ficheros de estado."""
    print("\n=== arranca sin los ficheros de estado ===")
    # Se apunta cada ruta a un fichero que **no existe** dentro de un temporal
    # vacío. Si algún cargador los leyera al importar, o revienta al no
    # encontrarlo, salta aquí. (Borrarlos en disco no serviría: el temporal
    # empieza con una copia de lo que hay.)
    from tracking.soloq import accounts_io
    from tracking.soloq import accounts_from_teams as aft
    from core import rank_store

    with estado_temporal(avisar=False) as tmp:
        vacio = str(Path(tmp) / "no-existe.json")
        for modulo, atributo in (
            (accounts_io, "JSON_TEAMS_PATH"),
            (aft, "JSON_PATH"),
            (rank_store, "RANKED_DATA_FILE"),
        ):
            setattr(modulo, atributo, vacio)

        try:
            ok(accounts_io.load_tracked_accounts() == [],
               "sin fichero de rosters, el cargador devuelve vacío (no revienta)")
            ok(aft.cargar_existentes_teams() == [],
               "y el de rosters de equipos también")
            ok(rank_store._cargar() == {},
               "y sin ranked_data.json, los rangos también")
            ok(rank_store.obtener_crudo("cualquiera") is None,
               "consultar un rango que no está devuelve None, no falla")
        finally:
            import importlib

            importlib.reload(accounts_io)
            importlib.reload(aft)
            importlib.reload(rank_store)


def prueba_restaura_de_verdad() -> None:
    """La red de seguridad tiene que restaurar aunque el fichero no esté en git.

    Este es el fallo que dejaba la restauración en papel: con los ficheros sin
    seguimiento, `git checkout --` no restauraba nada.
    """
    print("\n=== la red de seguridad restaura, no solo avisa ===")
    victima = RAIZ / "ranked_data.json"
    original = victima.read_bytes() if victima.exists() else None

    try:
        with estado_temporal(avisar=False):
            # Una prueba que escribe donde no debe.
            if original:
                datos = json.loads(original.decode("utf-8"))
            else:
                datos = {}
            datos["__basura_de_la_prueba__"] = "esto no debe sobrevivir"
            victima.write_text(json.dumps(datos, ensure_ascii=False),
                               encoding="utf-8")

        despues = victima.read_bytes() if victima.exists() else None
        ok(despues == original,
           "el estado real queda como estaba tras la prueba")
        contenido = json.loads(despues.decode("utf-8")) if despues else {}
        ok("__basura_de_la_prueba__" not in contenido,
           "y la basura que escribió la prueba no se queda")
    finally:
        if original is not None and not victima.exists():
            victima.write_bytes(original)


def main() -> int:
    print("=" * 74)
    print("EL ESTADO DEL BOT NO PUEDE ENTRAR EN EL REPO")
    print("=" * 74)

    prueba_no_versionado()
    prueba_ignorado()
    prueba_reparto()
    prueba_arranca_sin_ellos()
    prueba_restaura_de_verdad()

    print("\n" + "=" * 74)
    if fallos:
        print(f"fallos: {len(fallos)}")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("fallos: 0")
    print("El estado mutable vive en disco y en la rama de estado, no en `main`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

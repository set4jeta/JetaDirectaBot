"""Manda el estado del bot a una carpeta temporal, para que las pruebas no lo toquen.

Por qué existe
--------------
El bot guarda su estado en nueve ficheros JSON repartidos por `tracking/soloq/` y
`core/`: los canales suscritos, las ligas seguidas, los planes, los usuarios, las
cuentas seguidas… Cada prueba que toca uno de esos módulos **tiene que acordarse**
de redirigir su ruta a un temporal. El que se olvida no falla: escribe en el estado
de verdad y deja basura que nadie ve.

Pasó el 30-09-2026 al pasar la batería completa: `notify_config.json` acabó con un
servidor de prueba (`111222333444555666`) y `accounts_from_teams.json` con los
rosters reescritos — 8 458 líneas cambiadas. No dio ningún error; se descubrió
porque `git status` enseñó ficheros que nadie había tocado. Y el dueño tiene razón
en que eso es lo peor que puede hacer una prueba: **si el estado cambia solo, ya no
te fías de ninguna**.

Cómo se usa
-----------
```python
from _estado_de_prueba import estado_temporal

with estado_temporal():
    ...  # aquí dentro, todo lo que se escriba va a un temporal
```

Hace tres cosas, y las tres importan:

1. **Redirige** las rutas de estado a una carpeta temporal.
2. **Comprueba** al salir que ningún fichero real cambió, y lo dice bien fuerte si
   pasó. Es lo que caza el caso de «alguien añadió un módulo y no lo apuntó aquí».
3. **Restaura** lo que se haya tocado, para que el daño no llegue a durar.

Enumerar rutas a mano se queda viejo; comprobar que la lista está completa, no.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

#: Cada ruta de estado: (módulo, atributo, nombre del fichero).
#:
#: El nombre se usa para el temporal y para saber qué fichero real vigilar, así que
#: tiene que coincidir con el de verdad. Hay una comprobación al final que avisa si
#: alguno de estos ficheros cambia durante la prueba.
_RUTAS = (
    ("tracking.soloq.channel_config", "CONFIG_PATH", "notify_config.json"),
    ("tracking.soloq.channel_targets", "RUTA", "channel_targets.json"),
    ("tracking.soloq.leagues", "_CONFIG_PATH", "leagues_config.json"),
    ("tracking.soloq.plans", "_CONFIG_PATH", "plans_config.json"),
    ("tracking.soloq.plans", "_USUARIOS_PATH", "plans_users.json"),
    ("tracking.soloq.user_config", "CONFIG_PATH", "users_config.json"),
    ("tracking.soloq.accounts_io", "JSON_PATH", "accounts.json"),
    ("tracking.soloq.accounts_io", "JSON_TEAMS_PATH", "accounts_from_teams.json"),
    # El mismo fichero, pero `accounts_from_teams` se lo guarda en su **propia**
    # constante (`JSON_PATH`) en vez de leer la de `accounts_io`. Redirigir solo
    # la de `accounts_io` deja a `refrescar_ligas` escribiendo en el fichero de
    # verdad, y eso pasó al probar el refresco de Worlds: la prueba avisó y
    # restauró, pero el aviso era correcto y el agujero real.
    ("tracking.soloq.accounts_from_teams", "JSON_PATH", "accounts_from_teams.json"),
    ("tracking.soloq.accounts_io", "JSON_SUELTAS_PATH", "cuentas_sueltas.json"),
    # El contador de ancho de banda. Lo escribe cualquier cosa que salga a la red,
    # así que sin esto lo toca media batería.
    ("utils.egress", "RUTA", "egress.json"),
    # Los rangos. Vive en la raíz y lo escribe `rank_store` en cuanto una prueba
    # pide un rango: `test_plataformas` lo dejaba con 1356 líneas menos, o sea con
    # los rangos de media plantilla borrados. Se detectaba (está en `_EN_LA_RAIZ`)
    # pero no se evitaba, que es la mitad que faltaba.
    ("core.rank_store", "RANKED_DATA_FILE", "ranked_data.json"),
)

#: Ficheros de estado que viven en la raíz del proyecto y no en `tracking/soloq/`.
_EN_LA_RAIZ = ("ranked_data.json",)


def _origen(nombre: str) -> Path:
    """Dónde vive de verdad un fichero de estado.

    Casi todos están en `tracking/soloq/`, pero los rangos viven en la raíz. Se
    resuelve por nombre en un solo sitio en vez de mantener dos listas paralelas:
    la segunda lista es justo la que se olvida de actualizar.
    """
    if nombre in _EN_LA_RAIZ:
        return RAIZ / nombre
    return RAIZ / "tracking" / "soloq" / nombre


def _rutas_reales() -> list[Path]:
    """Dónde están de verdad los ficheros de estado, ahora mismo."""
    return [_origen(nombre) for _, _, nombre in _RUTAS]


def _huella(ruta: Path) -> tuple[int, int] | None:
    """Tamaño y fecha de modificación, o `None` si no existe."""
    try:
        datos = ruta.stat()
        return datos.st_size, datos.st_mtime_ns
    except OSError:
        return None


@contextlib.contextmanager
def estado_temporal(avisar: bool = True):
    """Redirige el estado a un temporal, y vigila que el de verdad no se toque.

    Devuelve la carpeta temporal, por si la prueba quiere mirar lo que se escribió.
    """
    from importlib import import_module

    antes = {ruta: _huella(ruta) for ruta in _rutas_reales()}
    # **Copia de bytes tomada al entrar**, no al salir. Se toma antes porque es
    # lo que permite restaurar de verdad: los ficheros de estado ya no están en
    # el repo (ver `.gitignore`), así que el `git checkout --` de antes no
    # restauraba nada y la red de seguridad mentía. Con la copia da igual que el
    # fichero esté versionado o no.
    copias: dict[Path, bytes] = {
        ruta: ruta.read_bytes() for ruta in _rutas_reales() if ruta.exists()
    }

    with tempfile.TemporaryDirectory(prefix="estado-prueba-") as tmp:
        # **El temporal empieza con una copia de lo que hay.** No basta con
        # apuntar a un fichero vacío: hay pruebas que además de escribir el estado
        # lo LEEN, y necesitan datos de verdad — la de los objetivos por canal
        # resuelve «T1» a la LCK leyendo los rosters. Con un temporal vacío esas
        # comprobaciones fallan por falta de datos, que es un fallo de mentira y
        # manda a buscar el problema donde no está.
        for _, _, nombre in _RUTAS:
            origen = _origen(nombre)
            if origen.exists():
                shutil.copy2(origen, Path(tmp) / nombre)

        for modulo, atributo, nombre in _RUTAS:
            try:
                import_module(modulo)
                anterior = getattr(sys.modules[modulo], atributo)
                # **Se respeta el tipo.** `channel_targets.RUTA` es un `Path` y el
                # resto son cadenas; ponerle una cadena a un `Path` no falla al
                # asignarlo, falla mucho después con «'str' object has no attribute
                # 'exists'» dentro del módulo. Pasó al estrenar esto.
                nuevo = os.path.join(tmp, nombre)
                setattr(sys.modules[modulo], atributo,
                        Path(nuevo) if isinstance(anterior, Path) else nuevo)
            except (ImportError, AttributeError):
                # Si el módulo o el atributo ya no existe, no se puede redirigir.
                # No se levanta: la comprobación de abajo lo cazará si eso hace que
                # una prueba escriba en el estado real.
                pass

        # Y la variable de entorno del contador de salida, además del atributo:
        # `test_salida_red` **recarga el módulo** a propósito (comprueba que el
        # acumulado sobrevive a un reinicio) y una recarga vuelve a evaluar las
        # constantes. Con solo el atributo, la ruta desviada se desharía y la
        # prueba escribiría en el contador de verdad.
        entorno_antes = os.environ.get("EGRESS_RUTA")
        os.environ["EGRESS_RUTA"] = str(Path(tmp) / "egress.json")

        try:
            yield Path(tmp)
        finally:
            if entorno_antes is None:
                os.environ.pop("EGRESS_RUTA", None)
            else:
                os.environ["EGRESS_RUTA"] = entorno_antes

            tocados = [ruta for ruta, huella in antes.items()
                       if _huella(ruta) != huella]
            if tocados and avisar:
                print("\n" + "!" * 74)
                print("  La prueba escribió en el ESTADO REAL del bot:")
                for ruta in tocados:
                    print(f"     {ruta.relative_to(RAIZ)}")
                print("  Se restaura lo que había. Apunta el módulo que falta en")
                print("  `scripts/_estado_de_prueba.py` para que no vuelva a pasar.")
                print("!" * 74)

            # Se restaura desde la copia de bytes tomada al entrar. **Sin git**:
            # los ficheros de estado no están versionados y `git checkout` no
            # haría nada, con lo que el aviso de arriba prometería una
            # restauración que no ocurría.
            for ruta in tocados:
                if ruta in copias:
                    ruta.write_bytes(copias[ruta])
                elif ruta.exists():
                    # No existía al entrar: se borra lo que la prueba creó.
                    ruta.unlink()


#: Estado que el bot **escribe en marcha**. No se versiona: un fichero
#: commiteado es una foto vieja y el host arranca haciendo checkout de `main`.
#: Se reconstruye solo al arrancar o vive en la rama `estado`
#: (`core/estado_remoto.ARCHIVOS`).
#:
#: Ojo con no confundirlo con los ficheros de **configuración**
#: (`notify_config.json`, `channel_targets.json`, `leagues_config.json`…): esos
#: sí se versionan a propósito, son los valores por defecto con los que arranca
#: un servidor nuevo, y además viven en la rama de estado.
_ESTADO_MUTABLE: tuple[str, ...] = (
    "tracking/soloq/accounts_from_teams.json",
    "tracking/soloq/accounts.json",
    "ranked_data.json",
    "puuid_cache.json",
    "notified_games.json",
    "tracked_matches.json",
    "tracking/ranking_cache.json",
    "tracking/soloq/last_index.json",
    "tracking/soloq/infoplayers_eu.json",
)


def estado_limpio() -> bool:
    """¿El repo se está guardando de tragarse el estado del bot?

    Ya no significa «el estado está como el último commit»: el estado mutable no
    está en el repo, así que esa pregunta no tiene sentido. Lo que sí se puede
    afirmar, y es lo que evita que vuelva el problema del 18-10-2026, es que
    **sigue fuera** del control de versiones y dentro del `.gitignore`.
    """
    import subprocess

    problemas = []
    for rel in _ESTADO_MUTABLE:
        ruta = RAIZ / rel
        versionado = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", rel],
            cwd=RAIZ, capture_output=True).returncode == 0
        if versionado:
            problemas.append(f"VERSIONADO (no debería): {rel}")
            continue
        ignorado = subprocess.run(
            ["git", "check-ignore", "-q", "--", rel],
            cwd=RAIZ, capture_output=True).returncode == 0
        if not ignorado:
            problemas.append(f"sin cubrir por .gitignore: {rel}")
        if ruta.exists() and not versionado:
            pass  # está en disco y sin seguimiento: es exactamente lo que se quiere

    if problemas:
        print("Estado del bot mal guardado en el repo:")
        for p in problemas:
            print(f"   {p}")
        return False
    return True

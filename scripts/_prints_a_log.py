"""Convierte los `print()` de esports_extension en llamadas al logger.

Se hace con un script porque son 99 repartidos en cuatro ficheros y el criterio
es mecánico: el prefijo del mensaje ya dice de qué nivel es.

    [DEBUG] [FRAME] [ESTADO] [DEDUCCIÓN] ...  -> log.debug
    [⚠️] [WARN] [PROTECCIÓN] [FORZADO] ...    -> log.warning / log.info
    [ERROR] [❌] [🔥]                          -> log.error

El resto —mensajes sin prefijo, del tipo "Guardando partidos trackeados en"—
son informativos de una vez por operación, así que van a debug: en un bot que
late cada 30 s, "una vez por operación" son 2880 líneas al día.

Uso:  python scripts/_prints_a_log.py [--aplicar]
Sin --aplicar solo enseña lo que haría.
"""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

FICHEROS = {
    "esports_extension/models/tracker.py": "esports.tracker_model",
    "esports_extension/services/tracker_service.py": "esports.tracker",
    "esports_extension/services/storage.py": "esports.storage",
    "esports_extension/services/api.py": "esports.api",
}

# Prefijo -> nivel. Se comprueba en orden, el primero que encaje gana.
NIVELES = (
    (("[ERROR]", "[❌]", "[🔥]", "Error", "error al", "No se pudo"), "error"),
    (("[⚠️]", "[WARN]", "[PROTECCIÓN]", "[FIX]", "[AUTO-SCORE]"), "warning"),
    (("[🏁]", "[🟢]", "[PAUSA]", "[REANUDADO]", "[🗑️]"), "info"),
)
POR_DEFECTO = "debug"


def nivel_de(mensaje: str) -> str:
    for marcas, nivel in NIVELES:
        if any(m.lower() in mensaje.lower() for m in marcas):
            return nivel
    return POR_DEFECTO


def procesar(ruta: Path, nombre_logger: str, aplicar: bool) -> int:
    texto = ruta.read_text(encoding="utf-8")
    lineas = texto.split("\n")
    cambios = 0
    salida = []

    for linea in lineas:
        desnuda = linea.lstrip()
        if not desnuda.startswith("print(") or desnuda.startswith("#"):
            salida.append(linea)
            continue

        nivel = nivel_de(linea)
        salida.append(linea.replace("print(", f"log.{nivel}(", 1))
        cambios += 1

    if not cambios:
        return 0

    nuevo = "\n".join(salida)

    # Asegurar el logger. Se mete tras el último import de la cabecera.
    if "get_logger" not in nuevo:
        cuerpo = nuevo.split("\n")
        ultimo_import = 0
        for i, l in enumerate(cuerpo[:60]):
            if l.startswith(("import ", "from ")):
                ultimo_import = i
        cuerpo.insert(ultimo_import + 1, "from utils.logger import get_logger")
        cuerpo.insert(ultimo_import + 2, "")
        cuerpo.insert(ultimo_import + 3, f'log = get_logger("{nombre_logger}")')
        nuevo = "\n".join(cuerpo)

    print(f"{ruta.relative_to(RAIZ)}: {cambios} print() -> log")
    if aplicar:
        ruta.write_text(nuevo, encoding="utf-8")
    return cambios


def main() -> int:
    aplicar = "--aplicar" in sys.argv
    total = sum(
        procesar(RAIZ / rel, logger, aplicar) for rel, logger in FICHEROS.items()
    )
    print(f"\ntotal: {total}" + ("" if aplicar else "  (simulación; usa --aplicar)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

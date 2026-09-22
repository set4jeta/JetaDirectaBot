"""Repara los PUUIDs corruptos de las cuentas del bot desde la consola.

La lógica vive en `tracking/soloq/puuid_repair.py`, compartida con la tarea
periódica del bot, así que no hay dos implementaciones que se puedan
desincronizar.

Uso:
    python scripts/repair_puuids.py --dry-run   # ver qué cambiaría, sin escribir
    python scripts/repair_puuids.py             # aplicar (hace respaldo antes)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from tracking.soloq import puuid_repair  # noqa: E402


def _print_file_report(name: str, stats: dict) -> None:
    print()
    print("=" * 70)
    print(name)
    print("=" * 70)
    if "total" not in stats:
        print(f"   {stats.get('antes', 0)} entradas antes -> {stats.get('despues', 0)} "
              f"después ({stats.get('cambiadas', 0)} cambiadas)")
        return

    print(f"   {stats['total']} cuentas resueltas en {stats['duracion']}s")
    print(f"   reparadas      : {stats['reparadas']}")
    print(f"   ya correctas   : {stats['ya_correctas']}")
    print(f"   no encontradas : {stats['no_encontradas']}  (renombrada o borrada en Riot)")

    missing = stats.get("no_encontradas_lista") or []
    if missing:
        print(f"   ejemplos: {', '.join(missing[:14])}")
        if len(missing) > 14:
            print(f"            ...y {len(missing) - 14} más")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Repara PUUIDs corruptos vía la API de Riot")
    parser.add_argument("--dry-run", action="store_true",
                        help="muestra qué cambiaría sin escribir nada")
    args = parser.parse_args()

    print("=" * 70)
    print("REPARACIÓN DE PUUIDs" + ("  [SIMULACIÓN]" if args.dry_run else ""))
    print("=" * 70)

    # close_client=True: aquí sí conviene cerrar, es un proceso suelto que
    # termina. Dentro del bot el cliente es compartido y no se debe cerrar.
    summary = await puuid_repair.repair_all(
        dry_run=args.dry_run, close_client=True
    )

    if not summary:
        print("[ERROR] No se encontraron ficheros de cuentas.")
        return 1

    total_repaired = 0
    total_missing = 0
    for name, stats in summary.items():
        _print_file_report(name, stats)
        total_repaired += stats.get("reparadas", 0)
        total_missing += stats.get("no_encontradas", 0)

    print()
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"   PUUIDs reparados    : {total_repaired}")
    print(f"   cuentas no halladas : {total_missing}")
    if args.dry_run:
        print()
        print("   Simulación: ejecuta sin --dry-run para aplicar.")
    else:
        print()
        print("   Respaldos en .backups/")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

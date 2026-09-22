"""Reparación de PUUIDs reutilizable (script + tarea periódica del bot).

Riot es la fuente autorizada de los PUUIDs. Los que el proyecto guardaba desde
dpm.lol no los puede descifrar Riot y respondían:

    HTTP 400 "Bad Request - Exception decrypting <puuid>"

lo que dejaba al bot ciego a esas cuentas. Aquí está la lógica para
re-resolverlos por `riot_id`; el script de consola y la tarea de fondo del bot
usan esta misma función, así que el comportamiento no se puede desincronizar.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from utils.logger import get_logger

log = get_logger("tracking.puuid_repair")

ROOT = Path(__file__).resolve().parents[2]

ACCOUNT_FILES = (
    ROOT / "tracking" / "soloq" / "accounts_from_teams.json",
    ROOT / "tracking" / "soloq" / "accounts.json",
)
PUUID_CACHE = ROOT / "puuid_cache.json"

# `account-v1/by-riot-id` es búsqueda global: comprobado en vivo, europe,
# americas y asia devuelven el mismo PUUID. Una sola llamada por cuenta basta.
# ("sea" fue fusionado con "asia" y devuelve 403.)
CLUSTER = "europe"

# Cuántas resoluciones a la vez. El límite medido de este método es 1000 por
# minuto, así que el arranque no puede resolverse de golpe: sin tope, se lanzan
# ~1245 peticiones en unos pocos segundos, Riot contesta 429 (medido en la
# consola: tipo=method, Retry-After=1, más de cien en un arranque) y el arranque
# pasa de 2 s a 50 s esperando reintentos.
MAX_CONCURRENCY = int(os.getenv("PUUID_REPAIR_CONCURRENCY", "10"))


def load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, data) -> None:
    """Escritura atómica: `tmp` + `os.replace`.

    Este módulo reescribe `accounts.json` (572 kB) y `puuid_cache.json` enteros.
    Con `path.open("w")` el destino se trunca antes de saber si el volcado cabe,
    así que un disco lleno o un SIGTERM a mitad —Render manda uno en cada
    despliegue— dejaba el fichero en 0 bytes con todos los PUUID perdidos. Pasó
    el 03-09-2026 con dos ficheros que se escribían igual.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("No se pudo guardar %s: %s. Se conserva el anterior.", path, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def backup(paths: list[Path], backup_dir: Path) -> list[Path]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    made = []
    for path in paths:
        if path.exists():
            dest = backup_dir / f"{path.name}.{stamp}.bak"
            shutil.copy2(path, dest)
            made.append(dest)
    return made


def iter_accounts(players: list[dict]):
    """Genera (account, game_name, tag_line) para cuentas con riot_id válido."""
    for player in players:
        for account in player.get("accounts", []):
            riot_id = account.get("riot_id") or {}
            game_name = riot_id.get("game_name")
            tag_line = riot_id.get("tag_line")
            if game_name and tag_line:
                yield account, game_name, tag_line


async def _resolve(client, game_name: str, tag_line: str) -> str | None:
    from apis.riot_client import RiotApiError

    try:
        return await client.get_puuid(game_name, tag_line, region=CLUSTER)
    except RiotApiError as exc:
        log.debug("No se pudo resolver %s#%s: %s", game_name, tag_line, exc.status)
        return None


async def _resolver_todos(
    client,
    objetivos: dict[str, tuple[str, str]],
    ya_resuelto: dict[str, str | None] | None = None,
) -> dict[str, str | None]:
    """Resuelve `{"Game#Tag": (game, tag)}` -> `{"Game#Tag": puuid|None}`.

    Con `ya_resuelto` se reutiliza lo que otra pasada ya averiguó, que es la
    gracia del arreglo: `repair_file` y `rebuild_puuid_cache` recorren **los
    mismos** riot_id, así que la mitad del trabajo era repetido.

    El semáforo es lo que evita los 429: sin él se disparan todas las
    peticiones de golpe y Riot contesta con `tipo=method` durante todo el
    arranque.
    """
    semaforo = asyncio.Semaphore(MAX_CONCURRENCY)
    resultados: dict[str, str | None] = dict(ya_resuelto or {})

    pendientes = {k: v for k, v in objetivos.items() if k not in resultados}
    if not pendientes:
        log.debug("Resolución de PUUIDs: %d ya resueltas, 0 peticiones.", len(resultados))
        return resultados

    async def uno(clave: str, game_name: str, tag_line: str):
        async with semaforo:
            return clave, await _resolve(client, game_name, tag_line)

    pares = await asyncio.gather(
        *(uno(k, gn, tl) for k, (gn, tl) in pendientes.items())
    )
    resultados.update(pares)
    log.debug(
        "Resolución de PUUIDs: %d nuevas, %d reutilizadas, concurrencia %d.",
        len(pendientes), len(resultados) - len(pendientes), MAX_CONCURRENCY,
    )
    return resultados


async def repair_file(
    client,
    path: Path,
    dry_run: bool = False,
    ya_resuelto: dict[str, str | None] | None = None,
) -> dict:
    """Re-resuelve los PUUIDs de un fichero de cuentas y lo guarda.

    `ya_resuelto` se rellena con lo que esta pasada averiguó, para que la
    siguiente (`rebuild_puuid_cache`) no vuelva a pedirlo.
    """
    players = load_json(path)
    targets = list(iter_accounts(players))
    started = time.perf_counter()

    objetivos = {f"{gn}#{tl}": (gn, tl) for _acc, gn, tl in targets}
    resueltos = await _resolver_todos(client, objetivos, ya_resuelto)
    if ya_resuelto is not None:
        ya_resuelto.update(resueltos)

    stats = {"reparadas": 0, "ya_correctas": 0, "no_encontradas": 0}
    not_found: list[str] = []

    for account, game_name, tag_line in targets:
        label = f"{game_name}#{tag_line}"
        puuid = resueltos.get(label)

        if not puuid:
            # Cuenta renombrada o borrada en Riot. No borramos sus datos por si
            # vuelve, pero la marcamos para no gastar peticiones en cada pasada.
            stats["no_encontradas"] += 1
            not_found.append(label)
            if not dry_run:
                account["stale"] = True
            continue

        if account.get("puuid") != puuid:
            stats["reparadas"] += 1
            if not dry_run:
                account["puuid"] = puuid
        else:
            stats["ya_correctas"] += 1

        if not dry_run:
            account.pop("stale", None)

    stats["duracion"] = round(time.perf_counter() - started, 2)
    stats["total"] = len(targets)
    stats["no_encontradas_lista"] = not_found

    if not dry_run:
        save_json(path, players)

    log.info(
        "%s: %d cuentas · %d reparadas · %d correctas · %d no halladas (%.1fs)",
        path.name, len(targets), stats["reparadas"],
        stats["ya_correctas"], stats["no_encontradas"], stats["duracion"],
    )
    return stats


async def rebuild_puuid_cache(
    client,
    players_by_file: list,
    dry_run: bool = False,
    ya_resuelto: dict[str, str | None] | None = None,
) -> dict:
    """Regenera puuid_cache.json desde Riot (guardaba PUUIDs de dpm.lol).

    Recibe las resoluciones que `repair_file` ya hizo: antes volvía a pedir a
    Riot exactamente los mismos riot_id, duplicando el trabajo de arranque.
    """
    targets: dict[str, tuple[str, str]] = {}
    for players in players_by_file:
        for _account, game_name, tag_line in iter_accounts(players):
            targets.setdefault(f"{game_name}#{tag_line}", (game_name, tag_line))

    resueltos = await _resolver_todos(client, targets, ya_resuelto)
    if ya_resuelto is not None:
        ya_resuelto.update(resueltos)

    new_cache = {k: v for k, v in resueltos.items() if v}

    old_cache = load_json(PUUID_CACHE) if PUUID_CACHE.exists() else {}
    changed = sum(1 for k, v in new_cache.items() if old_cache.get(k) != v)

    if not dry_run and new_cache:
        save_json(PUUID_CACHE, new_cache)

    log.info(
        "puuid_cache: %d -> %d entradas (%d cambiadas)",
        len(old_cache), len(new_cache), changed,
    )
    return {"antes": len(old_cache), "despues": len(new_cache), "cambiadas": changed}


async def repair_all(
    dry_run: bool = False,
    make_backup: bool = True,
    close_client: bool = False,
) -> dict:
    """Repara todos los ficheros de cuentas y la caché de PUUIDs.

    Con la key actual (500 req/10s) las ~690 cuentas se resuelven en unos
    segundos; con la key antigua esto habría tardado media hora, de ahí que
    antes se hiciera "de a poco" y nunca terminara.

    `close_client` solo debe valer `True` cuando esto se ejecuta como script
    suelto. Antes se cerraba siempre, y como el cliente es un singleton
    compartido, la tarea periódica del bot (cada 6 h) cerraba la sesión que
    estaba usando el tracker de partidas: las peticiones en vuelo morían con
    "Session is closed" y, peor, el cliente nuevo arrancaba con el limitador a
    cero y creía tener todo el cupo libre, provocando 429 evitables.
    """
    from apis.riot_client import close_riot_client, get_riot_client

    present = [p for p in ACCOUNT_FILES if p.exists()]
    if not present:
        log.error("No se encuentra ningún fichero de cuentas en tracking/soloq/")
        return {}

    if make_backup and not dry_run:
        backup(present + [PUUID_CACHE], ROOT / ".backups")

    client = await get_riot_client()
    summary: dict[str, dict] = {}
    loaded: list = []

    # Un solo diccionario compartido por las dos fases: lo que resuelve la
    # primera no se vuelve a pedir en la segunda.
    ya_resuelto: dict[str, str | None] = {}

    try:
        for path in present:
            players = load_json(path)
            loaded.append(players)
            summary[path.name] = await repair_file(client, path, dry_run, ya_resuelto)
        summary["puuid_cache"] = await rebuild_puuid_cache(
            client, loaded, dry_run, ya_resuelto
        )
    finally:
        if close_client:
            await close_riot_client()

    return summary

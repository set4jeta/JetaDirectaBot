"""Refresca los rosters desde dpm.lol **fuera de Render** y los publica.

Por qué existe
--------------
El bot saca los rosters de dpm.lol. Desde el 01-11-2026, Cloudflare contesta
**403 a la IP de Render** (está documentado en `apis/transporte_dpm.py`: no es un
fallo del cliente, es la reputación de la IP, y la IP de salida de Render no se
puede cambiar). Resultado: `accounts_from_teams.json` no se crea, el censo se
queda congelado y el bot solo puede arrancar con la copia del censo que guarda
`tracking/soloq/censo.py`.

Esto lo hace desde **un runner de GitHub**, que sale por otra IP, y deja el
resultado en la rama de estado. El bot se lo baja después con
`sincronizar_censo_remoto` (`core/background_tasks.py`).

Qué publica y qué no
--------------------
**Solo** `tracking/soloq/censo_compacto.json` (`estado_remoto.CENSO`). El censo
grande son 1,7 MB y la API de contenidos de GitHub no está cómoda ahí; la copia
compacta son ~290 KB y lleva lo que el barrido necesita, PUUIDs incluidos. Y no
se publica el resto de la rama a propósito: `egress.json` y
`notified_games.json` son contadores **vivos** del bot, y la copia de aquí —una
foto de hace horas— los haría retroceder.

Uso:
    python scripts/refrescar_rosters.py                    # todas las ligas
    python scripts/refrescar_rosters.py --ligas lec,lck     # solo esas
    python scripts/refrescar_rosters.py --sin-publicar      # no toca GitHub
    python scripts/refrescar_rosters.py --sin-puuid         # sin la API de Riot
    python scripts/refrescar_rosters.py --si-mas-de-horas 6 # no repetir si está fresco

Devuelve 0 si al menos una liga se refrescó (o si no hacía falta), 1 si no se
pudo ninguna: el workflow falla y se ve en la pestaña Actions en vez de quedarse
callado con un censo viejo.

Por qué `--si-mas-de-horas`
---------------------------
La reputación de la IP de un runner de GitHub **cambia de una ejecución a otra**.
Medido el 01-11-2026 con dos runs seguidos del mismo código: el primero pasó con
~16 % de peticiones rechazadas y reintentadas; el segundo recibió 403 en todo,
leaderboard incluido, desde la primera petición. Como la IP no cambia dentro de
una ejecución, la única forma de reintentar es **otra ejecución**, y eso es lo
que hace el workflow con tres intentos en serie. Este freno es lo que evita que
el segundo y el tercero repitan el scraping entero cuando el primero ya publicó:
si el censo de la rama es más joven que N horas, no se hace nada y se sale con 0.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import config  # noqa: E402  (después del sys.path, a propósito)
from core import estado_remoto  # noqa: E402
from tracking.soloq import censo, puuid_repair  # noqa: E402
from utils.logger import get_logger  # noqa: E402
from utils.safe_json import guardar_lista_json  # noqa: E402

log = get_logger("scripts.refrescar_rosters")

#: Pausa entre ligas, igual que en `sembrar_rosters_faltantes`. No es cortesía:
#: encadenar 20 scrapes sin respirar es la forma más rápida de que Cloudflare
#: decida que este runner también sobra.
PAUSA = 5.0


def _preparar_censo_previo() -> int:
    """Deja el censo restaurado donde lo espera `refrescar_ligas`.

    `refrescar_ligas` trabaja **sobre** `accounts_from_teams.json`: hereda los
    PUUID ya resueltos y conserva los jugadores de las ligas que no toca. En un
    runner el repo viene limpio y ese fichero no existe (está en `.gitignore`),
    así que sin esto cada ejecución sería un alta desde cero: se perderían los
    PUUID y habría que volver a pedirle ~2 000 a Riot **cada día**.

    Así que se expande la copia compacta a la forma larga y se escribe como
    fichero previo. Devuelve cuántos jugadores tenía.

    **Solo siembra si el fichero grande no tiene jugadores.** Si existe y está
    bien, no se toca: `refrescar_ligas` ya sabe trabajar sobre él, y sustituirlo
    por la copia compacta sería perder los campos que la copia no guarda
    (`rank`, `profile_icon`, `links`…). La copia es un respaldo, no la fuente.
    """
    from tracking.soloq.accounts_from_teams import JSON_PATH, cargar_existentes_teams

    if cargar_existentes_teams():
        log.info("El censo grande ya está en disco; no se siembra desde la copia.")
        return 0

    jugadores = censo.leer()
    if not jugadores:
        log.info("Sin copia del censo en la rama: esta pasada será un alta completa.")
        return 0

    guardar_lista_json(
        JSON_PATH,
        jugadores,
        etiqueta="censo previo (desde la rama de estado)",
        # Se está sembrando el punto de partida, no sustituyendo datos buenos:
        # el control de merma no pinta nada aquí y rechazaría la siembra.
        min_ratio=0.0,
        hacer_backup=False,
    )
    log.info("Censo previo sembrado desde la rama: %d jugadores.", len(jugadores))
    return len(jugadores)


def _codigos(pedidas: list[str] | None) -> list[str]:
    from tracking.soloq.leagues import LIGAS, resolver

    if not pedidas:
        return list(LIGAS)

    salida: list[str] = []
    for crudo in pedidas:
        liga = resolver(crudo)
        if liga is None:
            log.warning("Liga desconocida: %s (se ignora).", crudo)
            continue
        if liga.codigo not in salida:
            salida.append(liga.codigo)
    return salida


def _refrescar(codigos: list[str]) -> tuple[int, int]:
    """Refresca liga por liga. Devuelve `(hechas, fallidas)`.

    De una en una y no todo en una llamada, por dos razones: cada liga que
    termina se escribe (si el runner muere a mitad, lo hecho queda), y un fallo
    en una no arrastra a las demás.
    """
    from tracking.soloq.accounts_from_teams import refrescar_ligas

    hechas = fallidas = 0
    for i, codigo in enumerate(codigos, 1):
        try:
            ok = refrescar_ligas([codigo])
        except Exception:
            log.exception("Fallo refrescando %s.", codigo)
            ok = False
        if ok:
            hechas += 1
            log.info("Roster de %s refrescado (%d/%d).", codigo, i, len(codigos))
        else:
            fallidas += 1
            log.warning("Roster de %s sin cambios (%d/%d).", codigo, i, len(codigos))
        if i < len(codigos):
            time.sleep(PAUSA)
    return hechas, fallidas


async def _reparar_puuids() -> None:
    """Resuelve en Riot los PUUID de las cuentas nuevas y rehace la copia.

    El orden importa: `refrescar_ligas` escribió la copia compacta **antes** de
    que existieran estos PUUID. Si no se reescribe aquí, viajan 300 cuentas sin
    PUUID y el bot no puede sondearlas — es el mismo fallo que ya se comió una
    liga entera el 22-09-2026.
    """
    from tracking.soloq.accounts_from_teams import cargar_existentes_teams

    if not config.RIOT_API_KEY:
        log.warning(
            "Sin RIOT_API_KEY: las cuentas nuevas se publican sin PUUID y el bot "
            "no podrá sondearlas hasta que alguien las repare."
        )
        return

    try:
        await puuid_repair.repair_all(dry_run=False, make_backup=False, close_client=True)
    except Exception:
        log.exception("Fallo reparando PUUID; se publica lo que haya.")
        return

    jugadores = cargar_existentes_teams()
    if jugadores:
        censo.escribir(jugadores)


async def publicar() -> bool:
    """Sube el censo a la rama de estado. `False` si no se pudo."""
    if not estado_remoto.activo():
        log.warning("Sin GITHUB_TOKEN/GITHUB_REPO no se publica nada.")
        return False
    subidos = await estado_remoto.guardar(forzar=True, solo=estado_remoto.CENSO)
    if subidos:
        log.info("Censo publicado en %s@%s.", config.GITHUB_REPO, config.GITHUB_RAMA_ESTADO)
        return True
    log.error("No se pudo publicar el censo en la rama de estado.")
    return False


async def _run(args) -> int:
    codigos = _codigos(args.ligas)
    if not codigos:
        log.error("No hay ninguna liga que refrescar.")
        return 1
    log.info("Rosters: %d liga(s) a refrescar: %s", len(codigos), ", ".join(codigos))

    if not args.sin_restaurar:
        # Bajar el censo de la rama no es opcional: es lo que hace que esta
        # pasada sea incremental en vez de un alta desde cero (ver
        # `_preparar_censo_previo`).
        await estado_remoto.restaurar(solo=estado_remoto.CENSO)
        if args.si_mas_de_horas > 0 and not args.forzar:
            # Otra ejecución (de este mismo workflow, unos minutos antes) ya
            # publicó. Reintentar aquí solo gastaría 20 minutos de scraping.
            edad_h = censo.edad_dias()
            edad_h = None if edad_h is None else edad_h * 24
            if edad_h is not None and edad_h < args.si_mas_de_horas:
                log.info(
                    "El censo de la rama tiene %.2f h (menos de %.0f): no hace "
                    "falta otra pasada. Usa --forzar para hacerla igualmente.",
                    edad_h, args.si_mas_de_horas,
                )
                return 0
    _preparar_censo_previo()

    hechas, fallidas = _refrescar(codigos)
    log.info("Rosters: %d liga(s) refrescadas, %d sin cambios.", hechas, fallidas)

    if hechas:
        if not args.sin_puuid:
            await _reparar_puuids()
        else:
            log.info("Reparación de PUUID omitida (--sin-puuid).")

    edad = censo.edad_dias()
    log.info(
        "Censo compacto: %s.",
        "sin copia" if edad is None else f"{edad:.2f} días de antigüedad",
    )

    if args.sin_publicar:
        log.info("Publicación omitida (--sin-publicar).")
    elif hechas:
        if not await publicar():
            return 1
    else:
        log.warning("No se refrescó ninguna liga; no se publica nada.")

    return 0 if hechas else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ligas", default="",
        help="códigos separados por comas (por defecto, todas las del catálogo)",
    )
    parser.add_argument("--sin-publicar", action="store_true", help="no toca GitHub")
    parser.add_argument("--sin-puuid", action="store_true", help="no llama a Riot")
    parser.add_argument(
        "--sin-restaurar", action="store_true",
        help="no baja el censo de la rama (alta desde cero)",
    )
    parser.add_argument(
        "--si-mas-de-horas", type=float, default=0.0, metavar="H",
        help="no hace nada si el censo de la rama tiene menos de H horas (0 = siempre)",
    )
    parser.add_argument(
        "--forzar", action="store_true",
        help="refresca aunque el censo de la rama sea reciente",
    )
    args = parser.parse_args()
    args.ligas = [c.strip() for c in args.ligas.split(",") if c.strip()]
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

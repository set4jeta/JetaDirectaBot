"""Que el bot **arranque**, no solo que pasen las pruebas.

Por qué existe
--------------
Las otras pruebas comprueban piezas sueltas. Ninguna arranca el bot entero, así
que un fallo en el camino de arranque —un import circular, una clave de idioma
que no existe, un comando que no registra— no se ve hasta que se despliega. Y
desplegar para descubrirlo cuesta una caída: el 29-09-2026 el bot estuvo 3 días
fuera por algo parecido.

**No se conecta a Discord.** Recorre el mismo camino que `main.py` hasta justo
antes de `bot.start()`, que es donde vive el riesgo de arranque. Conectarse
pondría un segundo bot en línea con el token de producción y podría mandar avisos
duplicados a servidores reales, así que eso no se hace desde una prueba.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


# --------------------------------------------------------------------- #
# 1. La configuración, igual que la comprueba main.py
# --------------------------------------------------------------------- #

def prueba_config() -> None:
    print("\n=== configuración ===")
    import config

    falta = config.missing_required()
    ok(not falta, "están las variables obligatorias", ", ".join(falta) or "todas")
    print(f"  ... {config.resumen().splitlines()[0]}")


# --------------------------------------------------------------------- #
# 2. Los módulos que main.py precalienta en el arranque
# --------------------------------------------------------------------- #

def prueba_precalentamiento() -> None:
    """`main.py` importa esto antes de conectar, a propósito.

    Los de scraping pesan (cloudscraper, bs4, curl_cffi) y se importaban en frío
    dentro de un comando, comiéndose el plazo de 3 s que Discord da para la
    primera respuesta. Si alguno deja de importar, el bot arranca igual y el
    fallo aparece al usar el comando: por eso se comprueba aquí.
    """
    print("\n=== módulos que se precalientan al arrancar ===")

    for nombre in (
        "apis.transporte_dpm",
        "tracking.soloq.accounts_from_teams",
        "tracking.soloq.accounts_from_leaderboard",
        "core.estado_remoto",
        # Los que se tocaron el 29-09-2026 por el ancho de banda.
        "utils.egress",
        "ui.active_match_embed",
        "ui.player_image_utils",
        "ui.team_image_utils",
    ):
        try:
            __import__(nombre)
            ok(True, f"importa {nombre}")
        except Exception as exc:  # noqa: BLE001 — queremos ver el motivo
            ok(False, f"importa {nombre}", f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------- #
# 3. El registro de comandos, que es donde revienta un import roto
# --------------------------------------------------------------------- #

def prueba_registro_de_comandos() -> None:
    """Construye el bot y registra todo, sin conectar.

    Es la comprobación que de verdad cubre el arranque: `register_commands`
    importa **todos** los módulos de comandos, así que un import roto en
    cualquiera de ellos sale aquí y no en producción.
    """
    print("\n=== registro de comandos (sin conectar a Discord) ===")

    from core.commands import register_commands
    from core import bot_launcher

    bot = bot_launcher.bot

    try:
        asyncio.run(register_commands(bot))
    except Exception as exc:  # noqa: BLE001
        ok(False, "register_commands() termina", f"{type(exc).__name__}: {exc}")
        return

    ok(True, "register_commands() termina sin excepciones")

    # Los comandos se leen de `_application_commands_to_add` y no de
    # `get_application_commands()`, que devuelve 0 sin conectar: nextcord
    # **encola** los decorados y solo los vuelca al registro de verdad al
    # conectarse. Se probó con `add_all_application_commands()`, que es el paso
    # que da nextcord, y tampoco los mueve en frío. Es el único sitio donde se
    # pueden ver antes de conectar, y por eso la prueba usa un atributo privado
    # a conciencia: la alternativa es no comprobar nada.
    nombres = {c.name for c in bot._application_commands_to_add}

    for cmd in ("health", "premium", "info", "help", "live", "leagues"):
        ok(cmd in nombres, f"el comando /{cmd} está registrado")
    ok(len(nombres) >= 15, "se registran los comandos del catálogo",
       f"{len(nombres)} comandos: {', '.join(sorted(nombres))}")

    # Ninguno puede quedarse sin descripción: Discord rechaza el comando entero
    # y el error no aparece hasta sincronizar.
    sin_desc = [c.name for c in bot._application_commands_to_add
                if not (getattr(c, "description", "") or "").strip()]
    ok(not sin_desc, "todos los comandos llevan descripción",
       ", ".join(sin_desc) or "todos")


# --------------------------------------------------------------------- #
# 4. El tracker y el contador de salida, ya montados
# --------------------------------------------------------------------- #

def prueba_piezas_montadas() -> None:
    print("\n=== el tracker y el contador, montados ===")

    from utils import egress

    e = egress.estado()
    ok("mb" in e and "tope_mb" in e,
       "el contador de salida responde", f"{e['mb']:.2f} / {e['tope_mb']:.0f} MB")
    ok(egress.puede_adjuntar(1100), "y deja adjuntar el .bat")

    # El contador tiene que estar en la lista que se sube a GitHub, o se
    # reiniciaría en cada despliegue y no avisaría nunca de nada.
    from core.estado_remoto import ARCHIVOS
    ok("tracking/soloq/egress.json" in ARCHIVOS,
       "el contador se guarda fuera del disco efímero")

    # Y `/health` tiene que poder pintarlo: las claves del catálogo existen.
    from utils.i18n import t
    for clave in ("health.campo_salida", "health.salida", "health.salida_aviso"):
        for idioma in ("es", "en"):
            ok(t(clave, idioma) != clave,
               f"existe la clave {clave} en {idioma}")


def main() -> None:
    print("=" * 70)
    print("ARRANQUE DEL BOT (sin conectar a Discord)")
    print("=" * 70)

    prueba_config()
    prueba_precalentamiento()
    prueba_registro_de_comandos()
    prueba_piezas_montadas()

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()

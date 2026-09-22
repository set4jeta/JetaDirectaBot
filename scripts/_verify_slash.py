"""Comprueba, sin conectarse a Discord, que todos los comandos migrados quedan
registrados en las dos formas (`!x` y `/x`) y con la forma de opciones correcta.

Se ejecuta con:  python scripts/_verify_slash.py

Por qué offline: `bot.get_application_commands()` solo se rellena durante el
despliegue en `bot.start()`. Aquí se leen los pendientes
(`bot._application_commands_to_add`) y se fuerza `from_callback` para que las
opciones existan, que es lo que nextcord hace por dentro al arrancar.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nextcord
from nextcord.ext import commands


def construir_bot() -> commands.Bot:
    """Igual que el bot real de `core/bot_launcher.py`.

    `help_command=None` es imprescindible: nextcord trae su propio `!help`, y
    sin desactivarlo el `!help` del bot choca con
    `CommandRegistrationError: The command help is already an existing command`.
    """
    intents = nextcord.Intents.default()
    intents.message_content = True
    return commands.Bot(command_prefix="!", intents=intents, help_command=None)


async def main() -> int:
    bot = construir_bot()

    from core.commands import register_commands

    fallos: list[str] = []
    try:
        await register_commands(bot)
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"\nFALLO al registrar comandos: {exc!r}")
        return 1

    # --- prefijo -------------------------------------------------------
    prefijo = sorted(c.qualified_name for c in bot.commands)
    print("PREFIJO (%d):" % len(prefijo))
    for nombre in prefijo:
        cmd = bot.get_command(nombre)
        sub = ""
        if isinstance(cmd, commands.Group):
            sub = " -> " + ", ".join(sorted(s.name for s in cmd.commands))
        print(f"  !{nombre}{sub}")

    # --- slash ---------------------------------------------------------
    pendientes = list(getattr(bot, "_application_commands_to_add", []) or [])
    print("\nSLASH (%d):" % len(pendientes))
    vistos: list[str] = []
    for cmd in sorted(pendientes, key=lambda c: c.name or ""):
        try:
            cmd.from_callback(cmd.callback)
        except Exception as exc:  # noqa: BLE001
            fallos.append(f"/{cmd.name}: from_callback falló -> {exc!r}")
            continue

        vistos.append(cmd.name)
        # En nextcord 3.x `get_payload` pide el guild_id (los comandos pueden
        # declararse por servidor). `None` = global, que es lo que usa el bot.
        payload = cmd.get_payload(None)
        opciones = payload.get("options") or []
        perm = payload.get("default_member_permissions")

        # Un subgrupo llega como opción de tipo 1 (SUB_COMMAND).
        subs = [o for o in opciones if o.get("type") == 1]
        args = [o for o in opciones if o.get("type") != 1]

        detalle = []
        for o in args:
            marcas = []
            if o.get("required"):
                marcas.append("req")
            if o.get("choices"):
                marcas.append(f"{len(o['choices'])} choices")
            detalle.append(f"{o['name']}({', '.join(marcas) or 'opcional'})")

        extra = f"  [perm={perm}]" if perm else ""
        print(f"  /{cmd.name}{extra}")
        if detalle:
            print(f"      args: {', '.join(detalle)}")
        if subs:
            print(f"      subcomandos: {', '.join(s['name'] for s in subs)}")
        if not payload.get("description"):
            fallos.append(f"/{cmd.name}: sin descripción")

    # --- cotejo --------------------------------------------------------
    # Todo comando de prefijo de nivel raíz debería tener su slash.
    print("\nCOTEJO:")
    solo_prefijo = sorted(set(prefijo) - set(vistos))
    solo_prefijo = [n for n in solo_prefijo if " " not in n]
    solo_slash = sorted(set(vistos) - set(prefijo))
    if solo_prefijo:
        print(f"  sin slash todavía: {', '.join(solo_prefijo)}")
    if solo_slash:
        print(f"  solo slash: {', '.join(solo_slash)}")
    if not solo_prefijo and not solo_slash:
        print("  todos los comandos existen en las dos formas")

    if fallos:
        print("\nFALLOS:")
        for f in fallos:
            print("  " + f)
        return 1

    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

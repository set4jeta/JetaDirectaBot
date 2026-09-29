"""Comprueba que la lista de comandos de Discord es la que debe ser.

Por qué existe
--------------
Las descripciones de los slash commands no las manda el bot en un mensaje: se las
manda a Discord al registrar los comandos, y Discord las valida **todas de
golpe**. Eso hace que los fallos aquí sean mucho peores que en un mensaje: una
descripción de más de 100 caracteres o un nombre con mayúsculas hace que Discord
conteste 400 al despliegue **completo** y el bot se queda sin ningún slash
command. No es "ese comando sale raro": es que no responde ninguno.

Y desde el 22-09-2026 hay además tres reglas de diseño que el dueño fijó y que
este test defiende, porque son justo las que se deshacen sin querer al añadir un
comando:

1. **Solo slash.** Los `!` se retiraron: eran una segunda superficie que había que
   mantener en paralelo y decidir dos veces cada nombre. Aquí se comprueba que no
   queda **ninguno**.
2. **Solo en inglés.** Nada de `name_localizations` ni
   `description_localizations`: un nombre, el mismo para todos, que es lo
   universal. (El español del catálogo se queda como documentación y no viaja.)
3. **Una palabra por comando.** Ni guiones ni guiones bajos: `esports`, no
   `esports-live`. Lo que distinguía dos funciones parecidas va en una opción de
   lista cerrada (`/subscribe type: soloq|esports`).

Lo que se comprueba, en orden: el catálogo, el payload que se manda a Discord, la
lista exacta de comandos, y que no haya ni un `!`.

    python scripts/test_slash_locale.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nextcord  # noqa: E402
from nextcord.ext import commands  # noqa: E402

from utils.i18n import (  # noqa: E402
    _CATALOGO,
    IDIOMA_BASE_DISCORD,
    MAX_DESCRIPCION,
    MAX_NOMBRE,
    t,
)

fallos: list[str] = []

#: Lo que Discord acepta en el nombre de un comando o de una opción.
NOMBRE_VALIDO = re.compile(r"^[-_a-z0-9]{1,32}$")

#: Un comando, una palabra: sin guiones ni guiones bajos. Es la regla del dueño
#: («que se entienda su significado de una palabra»), y la que impediría que
#: volviera un `esports-live`.
UNA_PALABRA = re.compile(r"^[a-z][a-z0-9]{0,31}$")

#: La lista exacta. Está escrita a mano a propósito: si alguien añade, quita o
#: renombra un comando, tiene que venir aquí y decidirlo, en vez de colarse.
COMANDOS_ESPERADOS = (
    "channels", "esports", "following", "health", "help", "history", "info",
    "language", "leagues", "live", "match", "mute", "premium", "ranking",
    "schedule", "subscribe", "team", "track", "unsubscribe", "untrack",
)


def check(etiqueta: str, ok: bool, detalle: str = "") -> None:
    marca = "OK  " if ok else "FALLO"
    print(f"  [{marca}] {etiqueta}" + (f" — {detalle}" if detalle else ""))
    if not ok:
        fallos.append(etiqueta)


def claves_crudas(texto: str) -> list[str]:
    """Claves del catálogo que aparecen literalmente en un texto."""
    return [k for k in _CATALOGO if k in (texto or "")]


def revisar_texto(quien: str, texto: str, limite: int, es_nombre: bool) -> None:
    if not (texto or "").strip():
        fallos.append(f"{quien}: vacío")
        return
    if len(texto) > limite:
        fallos.append(f"{quien}: {len(texto)} caracteres (máx {limite}) -> {texto!r}")
    crudas = claves_crudas(texto)
    if crudas:
        fallos.append(f"{quien}: clave sin traducir {crudas}")
    if es_nombre and not NOMBRE_VALIDO.match(texto):
        fallos.append(f"{quien}: nombre inválido para Discord -> {texto!r}")


def locales_de(payload: dict, campo: str) -> dict:
    """Las localizaciones de un payload, con las claves como texto."""
    return {
        str(getattr(k, "value", k)): v
        for k, v in (payload.get(campo) or {}).items()
    }


async def main() -> int:
    intents = nextcord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    from core.commands import register_commands

    await register_commands(bot)

    print("\n1) El catálogo")
    claves_cmd = sorted(k for k in _CATALOGO if k.startswith("cmd."))
    check(f"hay {len(claves_cmd)} claves cmd.*", bool(claves_cmd))

    problemas_catalogo = []
    for clave in claves_cmd:
        en = t(clave, IDIOMA_BASE_DISCORD)
        limite = MAX_NOMBRE if clave.endswith((".name", ".arg")) else MAX_DESCRIPCION
        if len(en) > limite:
            problemas_catalogo.append(f"{clave}[en]: {len(en)} > {limite}")
        # El español se queda como documentación; si falta, es que alguien copió
        # la entrada a medias.
        if not (t(clave, "es") or "").strip():
            problemas_catalogo.append(f"{clave}: sin español")
    check("ninguna clave se pasa del límite y todas tienen español",
          not problemas_catalogo, "; ".join(problemas_catalogo[:4]))

    print("\n2) El payload que se le manda a Discord")
    pendientes = list(getattr(bot, "_application_commands_to_add", []) or [])
    check(f"hay {len(pendientes)} slash commands", len(pendientes) > 0)

    for cmd in sorted(pendientes, key=lambda c: c.name or ""):
        cmd.from_callback(cmd.callback)
        payload = cmd.get_payload(None)
        nombre = payload.get("name", "?")

        revisar_texto(f"/{nombre} nombre", nombre, MAX_NOMBRE, es_nombre=True)
        revisar_texto(f"/{nombre} desc", payload.get("description", ""),
                      MAX_DESCRIPCION, es_nombre=False)

        for opcion in payload.get("options") or []:
            etiqueta = f"/{nombre} {opcion.get('name', '?')}"
            revisar_texto(f"{etiqueta} nombre", opcion.get("name", ""),
                          MAX_NOMBRE, es_nombre=True)
            revisar_texto(f"{etiqueta} desc", opcion.get("description", ""),
                          MAX_DESCRIPCION, es_nombre=False)

    print("\n3) Solo en inglés: nada de localizaciones")
    con_locales = []
    for cmd in sorted(pendientes, key=lambda c: c.name or ""):
        payload = cmd.get_payload(None)
        if locales_de(payload, "name_localizations"):
            con_locales.append(f"/{payload.get('name')} (nombre)")
        if locales_de(payload, "description_localizations"):
            con_locales.append(f"/{payload.get('name')} (descripción)")
        for opcion in payload.get("options") or []:
            if locales_de(opcion, "name_localizations"):
                con_locales.append(f"/{payload.get('name')} {opcion.get('name')} (nombre)")
            if locales_de(opcion, "description_localizations"):
                con_locales.append(f"/{payload.get('name')} {opcion.get('name')} (descripción)")
    check("ningún comando ni opción manda traducciones", not con_locales,
          str(con_locales[:4]))

    print("\n4) Una palabra por comando")
    con_guion = [c.name for c in pendientes if not UNA_PALABRA.match(c.name or "")]
    check("ningún nombre lleva guion ni guion bajo", not con_guion, str(con_guion))

    nombres = sorted(c.name for c in pendientes)
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    check("no hay dos comandos con el mismo nombre", not repetidos, str(repetidos))

    print("\n5) La lista exacta de comandos")
    print("  " + ", ".join(f"/{n}" for n in nombres))
    check(f"son los {len(COMANDOS_ESPERADOS)} comandos acordados",
          tuple(nombres) == COMANDOS_ESPERADOS,
          f"sobra: {sorted(set(nombres) - set(COMANDOS_ESPERADOS))} · "
          f"falta: {sorted(set(COMANDOS_ESPERADOS) - set(nombres))}")

    # Cada comando registrado tiene su nombre en el catálogo, y al revés: así no
    # queda una entrada huérfana ni un comando sin descripción.
    claves_nombre = {t(k, IDIOMA_BASE_DISCORD) for k in _CATALOGO if k.endswith(".name")}
    check("cada comando registrado tiene su clave cmd.X.name",
          set(nombres) <= claves_nombre,
          str(sorted(set(nombres) - claves_nombre)))
    check("no hay claves cmd.X.name sin comando",
          claves_nombre <= set(nombres),
          str(sorted(claves_nombre - set(nombres))))

    print("\n6) Los `!` se retiraron")
    prefijos = sorted(bot.all_commands)
    check("no queda ningún comando de prefijo", not prefijos, str(prefijos))

    print("\n7) Lo que ve el usuario")
    for cmd in sorted(pendientes, key=lambda c: c.name or ""):
        payload = cmd.get_payload(None)
        opciones = ", ".join(o.get("name", "") for o in (payload.get("options") or []))
        sufijo = f" ({opciones})" if opciones else ""
        print(f"  /{payload.get('name')}{sufijo}")
        print(f"      {payload.get('description')}")

    return 1 if fallos else 0


codigo = asyncio.run(main())

print("\n" + "=" * 60)
if fallos:
    print(f"FALLOS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("Los comandos son slash, solo en inglés, de una palabra y válidos para Discord.")
sys.exit(codigo)

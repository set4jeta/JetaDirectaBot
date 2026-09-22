"""Comprueba que la lista de comandos de Discord está localizada y es válida.

Por qué existe
--------------
Las descripciones de los slash commands no las manda el bot en un mensaje: se
las manda a Discord al registrar los comandos, y Discord las valida **todas de
golpe**. Eso hace que los fallos aquí sean mucho peores que en un mensaje:

1. **Una descripción de más de 100 caracteres** hace que Discord conteste 400 al
   despliegue **completo**. No es "ese comando sale raro": es que el bot se queda
   sin ningún slash command y solo responden los `!`.
2. **Un nombre de opción con mayúsculas, espacios o tildes** produce el mismo
   400. `jugador` vale; `Nick del pro` no.
3. **Una clave del catálogo que no existe** se cuela tal cual, así que el
   usuario ve `cmd.ligas.desc` en el selector de comandos. No falla nada: queda
   ahí puesto.
4. **Una descripción sin traducir** no da error tampoco. Simplemente el bot
   parece a medio hacer en el idioma del usuario.
5. **El español olvidado en `es-419`.** Discord trata `es-ES` y `es-419`
   (Latinoamérica) como locales distintos. Con solo `es-ES`, un usuario de la LLA
   ve el comando en inglés aunque el catálogo tenga español.

Nada de esto se ve en local: `bot.start()` es el que despliega, y el 400 sale en
producción. Así que se comprueba offline, forzando `from_callback` como hace
nextcord por dentro.

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
    LOCALES_DISCORD,
    MAX_DESCRIPCION,
    MAX_NOMBRE,
    t,
)

fallos: list[str] = []

#: Lo que Discord acepta en el nombre de un comando o de una opción.
NOMBRE_VALIDO = re.compile(r"^[-_a-z0-9]{1,32}$")

#: Los locales a los que tiene que llegar cada idioma que no sea el base.
ESPERADOS = tuple(
    loc
    for idioma, locales in LOCALES_DISCORD.items()
    if idioma != IDIOMA_BASE_DISCORD
    for loc in locales
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


def revisar_localizaciones(quien: str, base: str, locales: dict | None) -> None:
    """Que estén los locales esperados y que digan algo distinto del base."""
    locales = {str(getattr(k, "value", k)): v for k, v in (locales or {}).items()}
    faltan = [loc for loc in ESPERADOS if loc not in locales]
    if faltan:
        fallos.append(f"{quien}: sin traducción para {faltan}")
    for loc, texto in locales.items():
        revisar_texto(f"{quien}[{loc}]", texto, MAX_DESCRIPCION, es_nombre=False)
    # Una "traducción" idéntica al inglés casi siempre significa que se copió el
    # literal en vez de traducirlo. Con emoji o nombres propios puede pasar de
    # verdad, así que es aviso, no fallo.
    iguales = [loc for loc, txt in locales.items() if txt.strip() == (base or "").strip()]
    if iguales:
        print(f"      aviso: {quien} igual al inglés en {iguales}")


def revisar_nombre_localizado(quien: str, locales: dict | None) -> None:
    for loc, texto in {str(getattr(k, "value", k)): v for k, v in (locales or {}).items()}.items():
        revisar_texto(f"{quien}[{loc}]", texto, MAX_NOMBRE, es_nombre=True)


async def main() -> int:
    intents = nextcord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    from core.commands import register_commands

    await register_commands(bot)

    print("\n1) El catálogo de descripciones de comandos")
    claves_cmd = sorted(k for k in _CATALOGO if k.startswith("cmd."))
    check(f"hay {len(claves_cmd)} claves cmd.*", bool(claves_cmd))
    for clave in claves_cmd:
        texto_en = t(clave, IDIOMA_BASE_DISCORD)
        limite = MAX_NOMBRE if clave.endswith(".arg") else MAX_DESCRIPCION
        if len(texto_en) > limite:
            fallos.append(f"{clave}[en]: {len(texto_en)} caracteres (máx {limite})")
    check("ninguna clave cmd.* se pasa del límite de Discord",
          not [f for f in fallos if f.startswith("cmd.")])

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
        revisar_nombre_localizado(f"/{nombre} nombre", payload.get("name_localizations"))

        # Ya no hay ningún grupo con subcomandos: todos los comandos se
        # registran por `dual` o a mano con sus localizaciones, así que se
        # exige la traducción a todos. Si algún día vuelve un grupo (opciones
        # de tipo 1), habrá que decidir si se le exige lo mismo al grupo.
        opciones = payload.get("options") or []
        revisar_localizaciones(f"/{nombre} desc", payload.get("description"),
                               payload.get("description_localizations"))

        for opcion in opciones:
            etiqueta = f"/{nombre} {opcion.get('name', '?')}"
            revisar_texto(f"{etiqueta} nombre", opcion.get("name", ""),
                          MAX_NOMBRE, es_nombre=True)
            revisar_texto(f"{etiqueta} desc", opcion.get("description", ""),
                          MAX_DESCRIPCION, es_nombre=False)
            revisar_nombre_localizado(f"{etiqueta} nombre",
                                      opcion.get("name_localizations"))
            if opcion.get("type") != 1:
                revisar_localizaciones(f"{etiqueta} desc", opcion.get("description"),
                                       opcion.get("description_localizations"))

    print("\n3) Lo que ve cada usuario en su selector de comandos")
    for cmd in sorted(pendientes, key=lambda c: c.name or ""):
        payload = cmd.get_payload(None)
        locales = {
            str(getattr(k, "value", k)): v
            for k, v in (payload.get("description_localizations") or {}).items()
        }
        es = locales.get("es-ES", "—")
        print(f"  /{payload.get('name')}")
        print(f"      en: {payload.get('description')}")
        print(f"      es: {es}")

    return 1 if fallos else 0


codigo = asyncio.run(main())

print("\n" + "=" * 60)
if fallos:
    print(f"FALLOS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("Todos los comandos son válidos para Discord y están localizados.")
sys.exit(codigo)

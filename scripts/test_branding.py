"""Comprueba que el descargo legal de Riot llega de verdad a las superficies.

Por qué este test
-----------------
`utils/branding.py` existía pero no lo llamaba nadie, así que la obligación
seguía incumplida con el módulo escrito. Un test que solo importe el módulo no
detecta eso: hay que mirar el embed **ya construido**.

Lo que se afirma
----------------
1. `/help` lleva el descargo completo, en los dos idiomas, y sigue cabiendo en
   los límites de Discord (campo 1024, embed entero 6000).
2. El respaldo en texto plano también lo lleva: si falta el permiso de embeds,
   ese texto es toda la ayuda que ve el usuario.
3. El embed de partida lleva la versión corta en el pie.
4. `sellar_embed` no pisa un pie que ya existía (caso `/health`).
5. `enlaces()` no inventa enlaces sin configurar.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nextcord

from utils.branding import (
    BOT_NOMBRE,
    descargo_corto,
    descargo_riot,
    enlaces,
    sellar_embed,
)

fallos: list[str] = []


def check(cond: bool, etiqueta: str) -> None:
    print(f"  {'OK  ' if cond else 'FALLO'}  {etiqueta}")
    if not cond:
        fallos.append(etiqueta)


# --------------------------------------------------------------------------
# 1 y 2. La ayuda
# --------------------------------------------------------------------------
print("\n=== /help ===")
from core.help_commands import construir_embed, construir_texto  # noqa: E402

#: Trozo textual de la plantilla de Riot. Si esto no aparece, el descargo no es
#: el que pide la política, sea lo que sea lo que haya en su lugar.
_FIRMA_EN = "isn't endorsed by Riot Games"
_FIRMA_ES = "no está avalado por Riot Games"

for idioma, firma in (("es", _FIRMA_ES), ("en", _FIRMA_EN)):
    embed = construir_embed(idioma)
    campos = [(f.name or "", f.value or "") for f in embed.fields]
    todo = "\n".join(v for _n, v in campos)

    check(firma in todo, f"[{idioma}] el embed de /help lleva el descargo")
    check(
        "trademarks or registered trademarks of Riot Games" in todo,
        f"[{idioma}] incluye la parte de marcas registradas",
    )
    check(BOT_NOMBRE in todo, f"[{idioma}] el descargo nombra al producto")

    largos = [(n, len(v)) for n, v in campos if len(v) > 1024]
    check(not largos, f"[{idioma}] ningún campo pasa de 1024 ({largos})")

    total = len(embed.title or "") + len(embed.description or "") + sum(
        len(n) + len(v) for n, v in campos
    )
    check(total <= 6000, f"[{idioma}] el embed entero cabe en 6000 ({total})")

    texto = construir_texto(idioma)
    check(firma in texto, f"[{idioma}] el respaldo en texto plano lleva el descargo")

# El descargo español adjunta el original inglés a propósito: es una traducción
# de cortesía y hay que poder ver qué dice el texto que Riot redacta.
check(
    _FIRMA_EN in descargo_riot("es"),
    "[es] el descargo adjunta el original en inglés",
)
check(
    descargo_riot(None) == descargo_riot("es"),
    "sin idioma cae en español (idioma por defecto del bot)",
)
check(
    descargo_riot("fr") == descargo_riot("es"),
    "un idioma no soportado cae en español, no revienta",
)

# --------------------------------------------------------------------------
# 3. El pie del embed de partida
# --------------------------------------------------------------------------
print("\n=== embed de partida ===")
for idioma in ("es", "en"):
    embed = nextcord.Embed(title="x")
    sellar_embed(embed, idioma)
    pie = embed.footer.text or ""
    check(pie == descargo_corto(idioma), f"[{idioma}] el pie es el descargo corto")
    check("Riot Games" in pie, f"[{idioma}] el pie menciona a Riot Games")
    check(len(pie) <= 2048, f"[{idioma}] el pie cabe en 2048 ({len(pie)})")

# --------------------------------------------------------------------------
# 4. No pisar un pie existente
# --------------------------------------------------------------------------
print("\n=== sellar_embed sobre un pie que ya existía ===")
embed = nextcord.Embed(title="x")
embed.set_footer(text="Actualizado hace 2 min")
sellar_embed(embed, "es")
pie = embed.footer.text or ""
check("Actualizado hace 2 min" in pie, "conserva el pie original")
check("Riot Games" in pie, "y añade el legal detrás")

# Llamarlo dos veces no debe duplicar el texto: el checker cachea el embed por
# idioma y podría sellarse más de una vez en un reintento.
sellar_embed(embed, "es")
check(
    (embed.footer.text or "").count("Riot Games") == 1,
    "sellar dos veces no duplica el descargo",
)

# --------------------------------------------------------------------------
# 5. Enlaces
# --------------------------------------------------------------------------
print("\n=== enlaces() ===")
check(
    all(l.count("http") >= 1 or ": " in l for l in enlaces("es")),
    "los enlaces que devuelve tienen contenido",
)
check(
    not any(l.rstrip().endswith(":") for l in enlaces("es")),
    "no devuelve etiquetas con la URL vacía",
)

print(f"\nfallos : {len(fallos)}")
for f in fallos:
    print(f"  - {f}")
sys.exit(1 if fallos else 0)

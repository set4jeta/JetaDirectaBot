"""Comprueba que el descargo de Riot **ya no** sale por ninguna superficie.

Por qué este test cambió de signo
---------------------------------
Antes afirmaba lo contrario: que el aviso «no está avalado por Riot Games»
llegaba de verdad a `/help`, al pie de cada embed y a la web, porque la política
del portal de Riot lo pide como texto obligatorio para productos de terceros.
`utils/branding.py` existía y no lo llamaba nadie, así que un test que solo
importara el módulo no lo habría detectado: había que mirar el embed construido.

El **22-09-2026 el dueño ordenó quitarlo**: leerlo le parecía que Riot rechazaba
el bot («¿cómo que no me avala, si me dieron una key donde postulé esperando
meses?»). Es su producto y su decisión. Este archivo vigila ahora lo contrario,
que es lo que sí puede romperse por descuido:

1. que `branding` no vuelva a exponer las funciones del aviso;
2. que `/help` (embed y texto plano) no lo publique en ninguno de los dos
   idiomas, y que el embed siga cabiendo en los límites de Discord;
3. que ningún módulo del bot lo llame por su cuenta;
4. que `enlaces()` siga sin inventar enlaces vacíos.
"""

from __future__ import annotations

import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from utils.branding import BOT_NOMBRE, enlaces  # noqa: E402

fallos: list[str] = []


def check(cond: bool, etiqueta: str) -> None:
    print(f"  {'OK  ' if cond else 'FALLO'}  {etiqueta}")
    if not cond:
        fallos.append(etiqueta)


#: Las dos formas del aviso, en los dos idiomas.
_AGUJAS = (
    "no está avalado por Riot Games",
    "isn't endorsed by Riot Games",
    "not endorsed by Riot Games",
    "trademarks or registered trademarks of Riot Games",
)


# --------------------------------------------------------------------------
# 1. `branding` ya no tiene las funciones del aviso
# --------------------------------------------------------------------------
print("\n=== utils/branding.py ===")
import utils.branding as branding  # noqa: E402

for nombre in ("descargo_riot", "descargo_corto", "sellar_embed"):
    check(
        not hasattr(branding, nombre),
        f"`{nombre}` ya no existe (se retiró el 22-09-2026)",
    )
check(
    bool(BOT_NOMBRE),
    "el nombre del producto sigue en pie, que lo usa media web",
)

# --------------------------------------------------------------------------
# 2. `/help`, en los dos idiomas
# --------------------------------------------------------------------------
print("\n=== /help ===")
from core.help_commands import construir_embed, construir_texto  # noqa: E402
from core.responder import partir  # noqa: E402

for idioma in ("es", "en"):
    embed = construir_embed(idioma)
    campos = [(f.name or "", f.value or "") for f in embed.fields]
    todo = "\n".join(v for _n, v in campos)

    sucio = [a for a in _AGUJAS if a in todo]
    check(not sucio, f"[{idioma}] el embed de /help no publica el aviso ({sucio})")

    largos = [(n, len(v)) for n, v in campos if len(v) > 1024]
    check(not largos, f"[{idioma}] ningún campo pasa de 1024 ({largos})")

    total = len(embed.title or "") + len(embed.description or "") + sum(
        len(n) + len(v) for n, v in campos
    )
    check(total <= 6000, f"[{idioma}] el embed entero cabe en 6000 ({total})")

    texto = construir_texto(idioma)
    sucio = [a for a in _AGUJAS if a in texto]
    check(not sucio, f"[{idioma}] el respaldo en texto plano tampoco ({sucio})")

    # El respaldo pasa de 2000 caracteres a propósito (lleva los 20 comandos), y
    # `enviar_partido` lo trocea. Lo que hay que vigilar es que el troceado deje
    # todos los trozos dentro del límite de Discord, no que quepa de una vez.
    trozos = partir(texto)
    check(
        all(len(t) <= 1900 for t in trozos),
        f"[{idioma}] el respaldo se trocea dentro del límite "
        f"({len(texto)} chars -> {len(trozos)} trozos, "
        f"máx {max((len(t) for t in trozos), default=0)})",
    )

# --------------------------------------------------------------------------
# 3. Nadie lo llama por su cuenta
# --------------------------------------------------------------------------
print("\n=== puntos de llamada ===")
llamadas = []
for carpeta in ("core", "ui", "tracking", "utils"):
    for f in (RAIZ / carpeta).rglob("*.py"):
        if f.name == "branding.py":
            continue
        src = f.read_text(encoding="utf-8", errors="replace")
        for nombre in ("descargo_riot", "descargo_corto", "sellar_embed"):
            if nombre in src:
                llamadas.append(f"{f.relative_to(RAIZ)} -> {nombre}")
check(not llamadas, "ningún módulo llama a las funciones retiradas")

# --------------------------------------------------------------------------
# 4. Enlaces
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

print("\n=== el aviso dice de qué bot viene ===")

# El aviso de partida es lo único que ve alguien que no conoce el proyecto:
# aparece en un canal, interesa a quien lo lee, y hasta el 29-09-2026 no decía
# de dónde salía ni cómo tenerlo. Cada aviso es publicidad y se estaba
# desperdiciando entera. Esto vigila que la marca no se caiga por descuido.
import asyncio  # noqa: E402

sys.path.insert(0, str(RAIZ / "scripts"))
from models.soloq_match import SoloQMatch  # noqa: E402
from scripts.test_i18n_embed import RANGOS, mapa, partida  # noqa: E402
from ui.active_match_embed import create_match_embed  # noqa: E402


async def _aviso():
    match = SoloQMatch.from_riot_game_data(partida())
    return await create_match_embed(match, mapa(1), RANGOS, idioma="es")


_embed, _ = asyncio.run(_aviso())
_autor = _embed.author

check(_autor is not None, "el aviso lleva autor")
check(_autor is not None and _autor.name == BOT_NOMBRE,
      f"y el autor es el nombre del bot ({_autor.name if _autor else 'sin autor'})")
# El enlace es lo que lo hace servir para algo: el `author` admite URL y el pie
# no, así que un pie con la dirección escrita sería texto para copiar a mano.
check(bool(_autor and _autor.url), "con enlace a Discord, pulsable")
check(not _embed.footer, "sin pie: el descargo de Riot sigue fuera")

print(f"\nfallos : {len(fallos)}")
for f in fallos:
    print(f"  - {f}")
sys.exit(1 if fallos else 0)

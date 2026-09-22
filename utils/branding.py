"""Textos legales y de marca del bot. Obligatorios, no decorativos.

Por qué existe este módulo
--------------------------
Las políticas generales del portal de desarrolladores de Riot (última revisión
del 29 de mayo de 2025, https://developer.riotgames.com/policies/general) dicen
literalmente:

    "You must post the following legal boilerplate to your product in a
     location that is readily visible to players:
     [Your product] isn't endorsed by Riot Games and doesn't reflect the views
     or opinions of Riot Games or anyone officially involved in producing or
     managing Riot Games properties. Riot Games, and all associated properties
     are trademarks or registered trademarks of Riot Games, Inc."

Esto **no estaba en ninguna parte del bot**. No es un detalle de estilo: el
mismo documento avisa de que incumplir las políticas puede acabar en
"suspension or cancellation of your API access or legal recourse", así que era
el riesgo más caro del proyecto y el más barato de arreglar.

Dónde se enseña
---------------
La política pide un sitio "readily visible", no todos los sitios:

* completo, en `/help` y en la web (`web/index.html`, `web/legal.html`);
* abreviado, en el pie del embed de partida, que es la superficie que más se ve
  porque se publica sola en el canal.

Sobre monetizar
---------------
La misma página permite cobrar con condiciones, y este módulo también recoge las
que afectan al texto que ve el usuario:

    "You may monetize your product as long as your product is registered on the
     Developer Portal and your product status is either Approved or Acknowledged"
    "You must have a free tier of access for players, which may include advertising"
    "Acceptable ways to charge players are: Subscriptions, donations, or
     crowdfunding; Entry fees for tournaments; Currencies that cannot be
     exchanged back into fiat"

De ahí sale la forma de `tracking/soloq/plans.py`: hay tier gratis siempre, y lo
que se cobra son cupos, nunca el aviso de partida en sí.

Marca
-----
El nombre del producto se puede cambiar con `BOT_NOMBRE` sin tocar el texto
legal, porque la plantilla de Riot lleva "[Your product]" al principio y hay que
sustituirlo por el nombre real.
"""

from __future__ import annotations

import os

#: Nombre del producto. Configurable porque el texto legal lo lleva incrustado.
BOT_NOMBRE = os.getenv("BOT_NOMBRE", "JetaDirectaBot")

#: URL pública del bot. Se usa en `/help`, en `/premium` y en el pie de la web.
WEB_URL = os.getenv("BOT_WEB_URL", "")

#: Enlace de invitación. Vacío por defecto: mejor no enseñar un enlace roto que
#: enseñar uno inventado.
INVITE_URL = os.getenv("BOT_INVITE_URL", "")

#: Donde se aceptan donaciones. Riot las nombra explícitamente como forma
#: aceptable de cobrar, así que es la vía con menos fricción legal.
DONATE_URL = os.getenv("BOT_DONATE_URL", "")

#: Servidor de soporte.
SOPORTE_URL = os.getenv("BOT_SOPORTE_URL", "")


def descargo_riot(idioma: str | None = None) -> str:
    """El descargo obligatorio, completo.

    La versión inglesa es **literal** la de la política de Riot: es un texto
    legal que ellos redactan, no una cadena del bot, así que no se reescribe ni
    se resume. La española es una traducción de cortesía y va acompañada del
    original para que no haya duda de qué se está aceptando.
    """
    ingles = (
        f"{BOT_NOMBRE} isn't endorsed by Riot Games and doesn't reflect the "
        "views or opinions of Riot Games or anyone officially involved in "
        "producing or managing Riot Games properties. Riot Games, and all "
        "associated properties are trademarks or registered trademarks of "
        "Riot Games, Inc."
    )
    if idioma == "en":
        return ingles
    return (
        f"{BOT_NOMBRE} no está avalado por Riot Games y no refleja las "
        "opiniones ni los puntos de vista de Riot Games ni de nadie "
        "involucrado oficialmente en la producción o gestión de las "
        "propiedades de Riot Games. Riot Games y todas sus propiedades "
        "asociadas son marcas comerciales o marcas registradas de "
        f"Riot Games, Inc.\n\n_{ingles}_"
    )


def descargo_corto(idioma: str | None = None) -> str:
    """Versión de una línea, para el pie de un embed.

    Discord corta el pie a 2048 caracteres, pero el problema real es visual: el
    descargo completo en el pie de cada notificación tapa el contenido. La
    política pide un sitio bien visible, no todos; el completo está en `/help` y
    en la web.
    """
    if idioma == "en":
        return f"{BOT_NOMBRE} · Not endorsed by Riot Games"
    return f"{BOT_NOMBRE} · No avalado por Riot Games"


def sellar_embed(embed, idioma: str | None = None) -> None:
    """Pone el descargo corto en el pie de un embed, sin pisar el que ya tenga.

    Modifica el embed en el sitio y no devuelve nada, para que se pueda llamar
    justo antes de enviarlo sin cambiar el flujo de quien lo construyó. Si el
    embed ya traía pie (como `/health`), se le añade detrás separado por `·`:
    perder el pie propio para meter el legal sería cambiar una cosa que
    funciona por otra.
    """
    corto = descargo_corto(idioma)
    actual = getattr(getattr(embed, "footer", None), "text", None)
    if actual and corto not in actual:
        embed.set_footer(text=f"{actual} · {corto}")
    elif not actual:
        embed.set_footer(text=corto)


def enlaces(idioma: str | None = None) -> list[str]:
    """Líneas de enlaces que existen de verdad, ya formateadas.

    Devuelve solo los que están configurados: un `/premium` que enseña
    "Donar: (vacío)" es peor que uno que no lo menciona.
    """
    es = idioma != "en"
    salida: list[str] = []
    if WEB_URL:
        salida.append(f"🌐 {'Web' if es else 'Website'}: {WEB_URL}")
    if INVITE_URL:
        salida.append(
            f"➕ {'Añadir a tu servidor' if es else 'Add to your server'}: {INVITE_URL}"
        )
    if DONATE_URL:
        salida.append(f"💛 {'Apoyar el proyecto' if es else 'Support the project'}: {DONATE_URL}")
    if SOPORTE_URL:
        salida.append(f"🛠 {'Soporte' if es else 'Support'}: {SOPORTE_URL}")
    return salida

"""Genera la web del bot desde el propio código del bot.

Por qué se genera en vez de escribirse a mano
---------------------------------------------
La web tiene que decir qué ligas se pueden seguir y qué lleva cada plan. Si eso
se escribe a mano en el HTML, se queda obsoleto exactamente igual que se quedó
el `TRACKED_TEAMS` que motivó `leagues.py`: el catálogo pasó de 12 a 20 ligas
esta semana y una landing con 12 sería publicidad falsa.

Aquí el HTML se rellena desde `tracking.soloq.leagues.LIGAS`,
`tracking.soloq.plans.PLANES` y `utils.branding`, así que la web **no puede**
contradecir al bot: si se añade una liga, se vuelve a ejecutar esto y ya está.

    python scripts/generar_web.py

Qué sale
--------
En `web/`, ficheros estáticos sin build ni servidor (GitHub Pages o Cloudflare
Pages, gratis):

    index.html                          la landing
    ligas.html                          el hub que enlaza las 20 ligas
    liga-<codigo>.html                  una por liga, con sus datos reales
    avisos.html                         qué es un aviso, con ejemplo
    alternativas-bots-lol-discord.html  la comparativa
    legal.html                          términos y privacidad
    404.html                            error real, noindex, fuera del sitemap
    sitemap.xml  robots.txt             generados desde las páginas escritas
    og.png  favicon.svg                 dibujados, sin dependencias
    img/teams/  img/players/            copiados de assets/ según se usen

Cómo se reparte el trabajo
--------------------------
* `web_seo.py`    — `<head>`, JSON-LD, sitemap y robots. *Cómo lo leen Google y
                    los LLM.*
* `web_layout.py` — cabecera, pie, botones, anuncios. *Lo que sale igual en
                    todas.*
* `web_datos.py`  — los ficheros de datos del bot, preparados para pintar.
* `web_paginas.py`— las páginas de contenido (ligas, avisos, comparativa, 404).
* `web_og.py`     — la imagen social y el favicon.
* este archivo    — la landing, el documento legal y el orden de todo.

Sobre los anuncios
------------------
El usuario quiere AdSense. El hueco existe (`.anuncio`) y el `<script>` de
AdSense se inyecta **solo** si se pasa `--adsense ca-pub-XXXX`, por dos razones
medidas, no por prudencia genérica:

1. AdSense exige que el sitio esté aprobado antes de servir anuncios, y para
   pedir la aprobación hace falta que el sitio ya exista con contenido y con
   política de privacidad. El orden correcto es publicar → pedir → añadir el ID.
2. Un `<script>` de terceros que recoge datos obliga a declararlo en la política
   de privacidad. Como el texto legal se genera aquí también, el aviso de
   cookies publicitarias solo aparece cuando el ID está puesto: así el
   documento nunca dice algo que no sea verdad.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracking.soloq.leagues import LIGAS, MAX_LIGAS_POR_SERVIDOR  # noqa: E402
from tracking.soloq.plans import ORDEN, PLANES  # noqa: E402
from utils import branding  # noqa: E402

from scripts import web_datos as datos  # noqa: E402
from scripts import web_layout as maq  # noqa: E402
from scripts import web_og as og  # noqa: E402
from scripts import web_paginas as pags  # noqa: E402
from scripts import web_seo as seo  # noqa: E402
from scripts.web_layout import e, normalizar_pub  # noqa: E402
from scripts.web_seo import Pagina  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "web")

#: Dominio del sitio. Sale de `BOT_WEB_URL` si está puesta y si no del respaldo
#: de `web_seo`, que apunta a GitHub Pages de este repositorio. **No puede quedar
#: vacío**: el canónico, `og:url` y el sitemap son URL absolutas por definición, y
#: una web sin canónico es la primera cosa de la lista de SEO que se incumple.
SITIO = seo.normalizar_sitio(branding.WEB_URL)

#: Fecha que se estampa en los documentos legales y en `dateModified`. Se pasa
#: como argumento en las pruebas para que el HTML generado sea comparable entre
#: ejecuciones.
HOY = date.today().isoformat()


def ligas_html() -> str:
    """Las ligas del catálogo como etiquetas, agrupadas por lo que sabe hacer.

    Se marca la que no permite detectar partida en vivo (LPL: China no está en
    la API de Riot). Prometer avisos en vivo de la LPL sería lo mismo que
    prometer LLA: una función que no existe.
    """
    filas = []
    for liga in LIGAS.values():
        marca = "" if liga.seguible else ' <span title="ranks only, no live game tracking">·&nbsp;Elo only</span>'
        filas.append(
            f'      <li><b>{e(liga.codigo)}</b> {e(liga.nombre)}'
            f" <span>{e(liga.region)}</span>{marca}</li>"
        )
    return "\n".join(filas)


def _plural(n: int, singular: str, plural: str) -> str:
    """`1 liga` / `3 ligas`, no `1 liga(s)`.

    En el embed de `/premium` el `(s)` se queda porque la cadena está en el
    catálogo de i18n y cambiarla obliga a tocar los dos idiomas; aquí es texto
    generado y no hay excusa. Una landing con "1 liga(s) a la vez" parece sin
    terminar, y esta página es lo primero que ve alguien que no conoce el bot.
    """
    return f"{n} {singular if n == 1 else plural}"


def _precio(plan) -> str:
    """`0 €` o `3,99 € / mes`, con coma decimal.

    La coma no es un detalle tipográfico: la página está en español y un precio
    escrito `3.99 €` se lee como formato anglosajón, que es exactamente la
    señal que hace dudar de si una web cobra en euros o en dólares.
    """
    if plan.gratis:
        return "0 €"
    return f"{plan.precio:.2f} € / month".replace(".", ",")


def planes_html() -> str:
    """Una tarjeta por plan, con los cupos que el bot aplica de verdad."""
    tarjetas = []
    for codigo in ORDEN:
        plan = PLANES[codigo]
        destacado = " destacado" if plan.gratis else ""
        etiqueta = (
            '        <span class="etiqueta">Always free</span>\n'
            if plan.gratis else ""
        )
        tarjetas.append(
            f'      <article class="plan{destacado}">\n'
            f"{etiqueta}"
            f"        <h3>{e(plan.nombre)}</h3>\n"
            f'        <p class="precio">{_precio(plan)}</p>\n'
            "        <ul>\n"
            f"          <li>{_plural(plan.ligas, 'league', 'leagues')} at a time</li>\n"
            f"          <li>{_plural(plan.canales, 'alert channel', 'alert channels')}</li>\n"
            f"          <li>{_plural(plan.jugadores_propios, 'custom player', 'custom players')}</li>\n"
            f"          <li>{_plural(plan.historial, 'match', 'matches')} of history</li>\n"
            "        </ul>\n"
            "      </article>"
        )
    return "\n".join(tarjetas)


# ---------------------------------------------------------------------- #
# Páginas
# ---------------------------------------------------------------------- #

#: Lo que hace el bot, en el orden en el que le importa a quien lo va a
#: instalar: primero lo que pasa sin escribir nada (el aviso automático), y
#: solo después los comandos. Es el mismo orden que `/help` y por el mismo
#: motivo: la función principal no se pide, ocurre.
FUNCIONES: tuple[tuple[str, str], ...] = (
    (
        "🔔 Alerts you when a pro queues up for SoloQ",
        "Without typing a thing. The bot watches the accounts of the players in "
        "the leagues you pick and posts the alert to your channel with champion, "
        "role, rank and the team they play for, as soon as the game starts.",
    ),
    (
        "🎮 <code>/live</code> · <code>/match</code> · <code>/info</code>",
        "Who is playing right now, a specific player's game with all ten "
        "participants and their ranks, or a player's profile with every account "
        "they use.",
    ),
    (
        "📊 <code>/ranking</code> · <code>/historial</code> · <code>/team</code>",
        "The SoloQ ladder of an entire league, the latest tracked games, and a "
        "team's roster with the rank of every player on it.",
    ),
    (
        "🏆 <code>/partida</code> · <code>/next</code>",
        "Live official matches and the schedule of the next ones, across every "
        "league, not only the ones you follow in SoloQ.",
    ),
    (
        "🌍 English and Spanish",
        "<code>/lang en</code> switches the whole bot to that language on that "
        "server: commands, alerts, errors and help.",
    ),
    (
        "🩺 <code>/health</code>",
        "If anything looks stale, this command says which data source is failing "
        "and when it last updated. No need to open a ticket.",
    ),
)


def funciones_html() -> str:
    """Las tarjetas de funciones.

    Aquí **no** se escapa: `FUNCIONES` es una constante de este archivo y lleva
    `<code>` a propósito. Lo que viene de datos (ligas, planes) sí pasa por
    `e()`; mezclar los dos criterios en la misma función sería la forma de
    acabar escapando lo que no toca o no escapando lo que sí.
    """
    tarjetas = []
    for titulo, texto in FUNCIONES:
        tarjetas.append(
            '      <article class="tarjeta">\n'
            f"        <h3>{titulo}</h3>\n"
            f"        <p>{texto}</p>\n"
            "      </article>"
        )
    return "\n".join(tarjetas)


def _plan_gratis():
    """El plan gratuito, buscado por su propiedad y no por su código.

    `PLANES` está indexado por código (`"gratis"`, `"pro"`, `"elite"`) y
    escribirlo a mano aquí es un `KeyError` esperando a que alguien renombre el
    plan. `Plan.gratis` es `precio <= 0`, que es la definición de verdad.
    """
    return next(p for p in PLANES.values() if p.gratis)


#: Las preguntas de la portada. Son las que se hacen antes de instalar nada, y
#: están aquí y no en `web_paginas` porque describen el producto entero y no una
#: liga: la respuesta a "¿es gratis?" sale de `PLANES`, no de un dato de liga.
#:
#: Se pintan en HTML y alimentan el `FAQPage` desde la misma lista, igual que en
#: las páginas de liga. La regla del usuario era explícita: nunca schema que no
#: coincida con el contenido visible.
def _preguntas_inicio() -> list[tuple[str, str]]:
    """Las FAQ de la portada, con los números sacados del código."""
    gratis = _plan_gratis()
    seguibles = sum(1 for liga in LIGAS.values() if liga.seguible)
    return [
        (
            f"What does {branding.BOT_NOMBRE} do?",
            f"It posts an alert to your Discord channel when a professional "
            "League of Legends player queues up for solo queue. The alert carries "
            "the champion, the role, the rank, the team and all ten participants "
            "of the game, and it arrives without anyone typing a single command.",
        ),
        (
            "Is it free?",
            f"Yes. The full game alert is in the free plan: "
            f"{gratis.ligas} league, {gratis.canales} alert channel and "
            f"{gratis.jugadores_propios} custom players. Paid plans only raise "
            "those limits, they never unlock the main feature, because Riot "
            "Games' policy requires a free tier to exist.",
        ),
        (
            "Which leagues does it cover?",
            f"{len(LIGAS)} professional leagues, from the LEC and the LCK to the "
            f"LFL or the NLC. Of those, {seguibles} allow live game detection; "
            "the LPL only provides ranks, because the Chinese servers are not in "
            "Riot's API.",
        ),
        (
            "Does it need permission to read my messages?",
            "Not to work with slash commands. The bot does not store messages: it "
            "holds the message content permission because prefix commands still "
            "exist and Discord requires it to read them, but they are processed "
            "in memory and discarded.",
        ),
        (
            "Does it work without my own server?",
            "Yes. It can be added to your account instead of to a server and the "
            "alerts arrive in your private chat, with /seguir to choose a "
            "specific player or an entire league.",
        ),
    ]


def _destacados_html() -> str:
    """Los tres enlaces internos grandes de la portada.

    No es un menú repetido: es la portada empujando enlace hacia las tres
    páginas que tienen que posicionar (el hub de ligas, la de avisos y la
    comparativa). La portada es la que recibe los enlaces de fuera, así que es
    la que puede repartirlos, y un enlace en el cuerpo con texto descriptivo
    vale más que el mismo destino en el pie.
    """
    tarjetas = (
        (
            "ligas.html",
            f"All {len(LIGAS)} leagues, one by one",
            "How many players and teams each league has, and what is published "
            "about each one.",
        ),
        (
            "avisos.html",
            "What the alert looks like",
            "The exact message that shows up in Discord, how long it takes and "
            "why the in-game clock runs behind.",
        ),
        (
            "alternativas-bots-lol-discord.html",
            "Compared with the other bots",
            "What each League of Legends Discord bot alerts on, with the data "
            "read from their official websites.",
        ),
    )
    return "\n".join(
        '      <article class="tarjeta">\n'
        f'        <h3><a href="{ruta}">{e(titulo)}</a></h3>\n'
        f"        <p>{e(texto)}</p>\n"
        "      </article>"
        for ruta, titulo, texto in tarjetas
    )


def pagina_inicio(pub: str, sitio: str, fecha: str) -> Pagina:
    """La landing.

    Estructura pensada para lo único que tiene que conseguir la página, que es
    que alguien pulse "Añadir a Discord": primero qué es y el botón, después las
    pruebas (funciones, ligas), y los planes al final. Los precios arriba
    espantan a quien todavía no sabe qué hace el bot.

    Es la única página que lleva `Organization`, `WebSite` y
    `SoftwareApplication`: los tres describen el sitio y el producto, no un
    contenido, y repetirlos en 25 páginas no añade nada —lo que hace es dar 25
    entidades con el mismo `@id` para que el rastreador decida cuál vale.
    """
    invite, invite_attr = maq.url(branding.INVITE_URL)
    soporte, sop_attr = maq.url(branding.SOPORTE_URL)
    donar, donar_attr = maq.url(branding.DONATE_URL)
    nombre = e(branding.BOT_NOMBRE)
    descripcion = (
        f"{branding.BOT_NOMBRE} alerts your Discord server when a professional "
        "League of Legends player queues up for SoloQ. "
        f"{len(LIGAS)} leagues, English and Spanish, free."
    )
    seguibles = sum(1 for liga in LIGAS.values() if liga.seguible)
    total_pros = sum(datos.censo_de(c).personas for c in LIGAS)
    preguntas = _preguntas_inicio()

    resumen = [
        f"Alerts your Discord server <b>when a pro queues up for SoloQ</b>, with "
        "champion, role, rank and team. No commands to type.",
        f"<b>{len(LIGAS)} leagues</b> and about <b>{total_pros} professional "
        f"players</b> tracked; {seguibles} leagues allow live game detection.",
        "The full alert is <b>free</b> and always will be: the plans only raise "
        "the limits.",
    ]

    cuerpo = (
        '  <header class="principal">\n'
        '    <div class="envoltura">\n'
        f"      <h1>{nombre}</h1>\n"
        '      <p class="lema">When a professional player queues up for SoloQ, '
        "your server finds out. Champion, role, rank and team, the moment the "
        "game starts.</p>\n"
        '      <div class="botones">\n'
        f'        <a class="boton primario" href="{invite}"{invite_attr}>Add to Discord</a>\n'
        f'        <a class="boton" href="{soporte}"{sop_attr}>Support server</a>\n'
        f'        <a class="boton" href="{donar}"{donar_attr}>Support the project</a>\n'
        "      </div>\n"
        f"{pags.tldr(resumen)}"
        "    </div>\n"
        "  </header>\n"
        "\n"
        '  <section id="funciones">\n'
        '    <div class="envoltura">\n'
        "      <h2>What it does</h2>\n"
        '      <p class="intro">Everything on this list works on the free '
        "plan.</p>\n"
        '      <div class="rejilla">\n'
        f"{funciones_html()}\n"
        "      </div>\n"
        "    </div>\n"
        "  </section>\n"
        "\n"
        '  <section id="ligas">\n'
        '    <div class="envoltura">\n'
        f"      <h2>{len(LIGAS)} leagues</h2>\n"
        '      <p class="intro">Each server picks the ones it wants to follow with '
        f"<code>/ligas</code>, up to {MAX_LIGAS_POR_SERVIDOR} at a time. Every "
        'league has <a href="ligas.html">its own page</a> with its players, their '
        "ranks and its teams.</p>\n"
        '      <ul class="ligas">\n'
        f"{ligas_html()}\n"
        "      </ul>\n"
        f'      <p class="nota">Of the {len(LIGAS)}, {seguibles} allow live game '
        "detection. The LPL only provides ranks and standings: China plays on "
        "servers that Riot's API does not expose, and promising live alerts for "
        "games that cannot be seen would be a lie.</p>\n"
        "    </div>\n"
        "  </section>\n"
        "\n"
        '  <section id="mas">\n'
        '    <div class="envoltura">\n'
        "      <h2>Before you install it</h2>\n"
        '      <div class="rejilla">\n'
        f"{_destacados_html()}\n"
        "      </div>\n"
        "    </div>\n"
        "  </section>\n"
        "\n"
        '  <section id="planes">\n'
        '    <div class="envoltura">\n'
        "      <h2>Plans</h2>\n"
        '      <p class="intro">The game alert is free and always will be. What '
        "you pay for is volume: more leagues at once, more channels and more "
        "history.</p>\n"
        '      <div class="planes">\n'
        f"{planes_html()}\n"
        "      </div>\n"
        '      <p class="nota">There is no automatic payment yet. If you want to '
        "support the project, plans are activated by hand from the donation link; "
        "until a payment processor exists, nobody can pay and get nothing in "
        "return.</p>\n"
        "    </div>\n"
        "  </section>\n"
        "\n"
        '  <section id="faq">\n'
        '    <div class="envoltura">\n'
        "      <h2>Frequently asked questions</h2>\n"
        f"{pags.faq_html(preguntas)}\n"
        f"{maq.bloque_anuncio(pub)}\n"
        "    </div>\n"
        "  </section>\n"
    )

    pagina = Pagina(
        ruta="index.html",
        titulo=f"{branding.BOT_NOMBRE} · SoloQ alerts for pro players on Discord",
        descripcion=descripcion,
        cuerpo=cuerpo,
        prioridad="1.0",
    )
    pagina.schemas = [
        seo.jsonld(seo.organizacion(
            sitio, branding.BOT_NOMBRE, soporte=branding.SOPORTE_URL,
        )),
        seo.jsonld(seo.sitio_web(sitio, branding.BOT_NOMBRE, descripcion)),
        seo.jsonld(seo.aplicacion(
            sitio, branding.BOT_NOMBRE, descripcion, invite=branding.INVITE_URL,
        )),
        seo.jsonld(seo.faq(preguntas)),
    ]
    return pagina


#: Qué guarda el bot, fila por fila. Sale de mirar los ficheros de verdad
#: (`notify_config.json`, `idiomas_config.json`, `leagues_config.json`,
#: `plans_config.json` y `announced_games.json`), no de una plantilla de
#: política de privacidad. Una tabla copiada de internet que diga "no guardamos
#: nada" siendo falso es peor que no tener política.
DATOS: tuple[tuple[str, str, str], ...] = (
    (
        "Server and channel ID",
        "To know where to post alerts and in which language.",
        "Until <code>/unsubscribe</code> runs or the bot is kicked.",
    ),
    (
        "Server language, leagues and plan",
        "To keep the configuration across restarts.",
        "Same as above.",
    ),
    (
        "IDs of games already announced",
        "To avoid sending the same alert twice to the same channel.",
        "2 hours.",
    ),
    (
        "Public League of Legends player data",
        "Riot ID, PUUID, rank and current game of the professional players being "
        "followed, obtained from the Riot Games API. This is not data about the "
        "people using the bot.",
        "Refreshed continuously; the match history is trimmed.",
    ),
)


def datos_html() -> str:
    """La tabla de datos de la política de privacidad."""
    filas = []
    for dato, para_que, cuanto in DATOS:
        filas.append(
            "        <tr>\n"
            f"          <td>{dato}</td>\n"
            f"          <td>{para_que}</td>\n"
            f"          <td>{cuanto}</td>\n"
            "        </tr>"
        )
    return "\n".join(filas)


def _seccion_cookies(pub: str) -> str:
    """El apartado de cookies. Cambia según si AdSense está activo.

    Esto es la razón de que el texto legal se genere y no se escriba a mano: sin
    ID no hay ni una cookie de terceros, y declarar cookies publicitarias que no
    existen es tan incorrecto como omitirlas cuando sí existen. Las dos versiones
    del párrafo salen del mismo sitio que el `<script>`, así que no se pueden
    desincronizar.
    """
    if not pub:
        return (
            "  <h3>7. Cookies</h3>\n"
            "  <p>This site is static and uses no cookies of its own or from third "
            "parties. There is no analytics, no advertising and no cross-site "
            "tracking. If that changes, this section is updated before the change "
            "goes live.</p>\n"
        )
    return (
        "  <h3>7. Cookies and advertising</h3>\n"
        "  <p>This site shows Google AdSense ads. Google and its partners use "
        "cookies or similar identifiers to serve ads and measure their "
        "performance, and may process data such as your IP address and your "
        "browsing activity. That processing is carried out by Google, not by "
        f"{e(branding.BOT_NOMBRE)}, and is governed by Google's own terms.</p>\n"
        "  <p>You can configure or withdraw your consent and manage personalised "
        'advertising in <a href="https://myadcenter.google.com/" '
        'rel="noopener" target="_blank">My Ad Center</a>, and read how Google uses '
        'the data in <a href="https://policies.google.com/technologies/'
        'partner-sites" rel="noopener" target="_blank">this notice</a>. The '
        "Discord bot shows no ads: ads appear only on this site.</p>\n"
    )


def pagina_legal(pub: str, hoy: str = HOY) -> Pagina:
    """Términos del servicio y política de privacidad, en una sola página.

    Van juntas y no en dos ficheros por una razón práctica: Discord pide **dos
    URL** al monetizar (Terms of Service y Privacy Policy) y acepta anclas, así
    que `legal.html#terminos` y `legal.html#privacidad` valen, y una sola página
    es una sola cosa que mantener.

    El texto describe lo que el bot hace de verdad, comprobado contra los
    ficheros que escribe (`notify_config.json`, `idiomas_config.json`,
    `leagues_config.json`, `plans_config.json`, `announced_games.json`). No es
    una plantilla rellenada.

    Se indexa, con `prioridad` baja. No se pone `noindex` aunque no sea contenido
    que nadie busque: es la página que Discord y AdSense comprueban que existe y
    es pública, y una política de privacidad marcada como no indexable es una
    señal rara justo en la página donde no conviene tenerla.
    """
    nombre = e(branding.BOT_NOMBRE)
    contacto = (
        f'<a href="{e(branding.SOPORTE_URL)}" rel="noopener">the support server</a>'
        if branding.SOPORTE_URL
        else "the support server listed on this site"
    )
    partes = [
        maq.migas_html([("Home", "index.html"),
                        ("Terms and Privacy", "legal.html")]),
        '  <main class="documento">\n',
        "  <h1>Terms and Privacy</h1>\n",
        f'  <p class="fecha">Last updated: {e(hoy)}</p>\n',
        f"  <p>This document covers {nombre} (the “bot”), a Discord bot "
        "that posts alerts when professional <em>League of Legends</em> players "
        "queue up for solo queue, and this website.</p>\n",
        '  <p><a href="#terminos">Terms of Service</a> · '
        '<a href="#privacidad">Privacy Policy</a></p>\n',
    ]
    partes.extend(_terminos(nombre, contacto))
    partes.extend(_privacidad(nombre, contacto, pub))
    partes.append("  </main>\n")
    return Pagina(
        ruta="legal.html",
        titulo=f"Terms and Privacy · {branding.BOT_NOMBRE}",
        descripcion=(
            f"Terms of service and privacy policy of {branding.BOT_NOMBRE}: what "
            "data the bot stores, what for, and for how long."
        ),
        cuerpo="".join(partes),
        prioridad="0.3",
    )


def _terminos(nombre: str, contacto: str) -> list[str]:
    """Los términos del servicio.

    El punto 4 (sin garantías) y el 5 (interrupciones) no son relleno legal: el
    bot depende de la API de Riot con una clave de cupo limitado y de Discord, y
    una caída de cualquiera de las dos deja de mandar avisos. Prometer
    disponibilidad que no se controla es lo que convierte un fallo en una
    reclamación.
    """
    return [
        '  <h2 id="terminos">Terms of Service</h2>\n',
        "  <h3>1. Acceptance</h3>\n",
        f"  <p>By adding {nombre} to a Discord server or using its commands you "
        "accept these terms. If you do not agree, kick the bot from the server: "
        "there is nothing else to do to stop using it.</p>\n",
        "  <h3>2. What is offered and at what price</h3>\n",
        "  <p>The main feature —the game alert and the information it carries— is "
        "<strong>free and always will be</strong>. Paid plans only raise the "
        "limits (simultaneous leagues, alert channels and history size). No plan "
        "grants an in-game advantage or information that is not already "
        "public.</p>\n",
        "  <p>Payments, when they exist, will be made by subscription or donation. "
        "There is no gambling, no loot boxes and no currency that can be exchanged "
        "back into real money. The prices shown on this site are indicative and do "
        "not constitute an offer until an active payment method exists.</p>\n",
        "  <h3>3. Acceptable use</h3>\n",
        "  <p>You may not use the bot to harass players, automate large volumes of "
        "requests, resell access or get around the service limits. Access can be "
        "withdrawn from a server that does any of those things, without prior "
        "notice if the abuse affects everyone else.</p>\n",
        "  <h3>4. No warranties</h3>\n",
        f"  <p>{nombre} is provided “as is”. Data comes from the Riot Games "
        "API and from public esports sources; it can arrive late, incomplete or "
        "not at all. No guarantee is given that an alert will be posted, that a "
        "piece of data is accurate, or that a player identified as a professional "
        "still is one. No liability is accepted for decisions made on the basis of "
        "this information.</p>\n",
        "  <h3>5. Interruptions and changes</h3>\n",
        "  <p>The service depends on the Riot Games API and on Discord, and can be "
        "interrupted when either of them fails, when the request quota runs out, "
        "or during maintenance. Features and limits may change; if a change "
        "reduces what a paying server already had, notice will be given in the "
        "support server before it is applied.</p>\n",
        "  <h3>6. Refunds</h3>\n",
        "  <p>As long as there is no automatic payment, there is nothing to refund. "
        "When the charge is made through Discord, Discord's refund policy applies; "
        "when it is made by donation, the amount contributed in the current month "
        f"will be returned to anyone who asks for it in {contacto}.</p>\n",
        "  <h3>7. Contact and cancellation</h3>\n",
        f"  <p>For anything related to these terms, write in {contacto}. To stop "
        "using the service, kicking the bot is enough; you can also stop only the "
        "alerts with <code>/unsubscribe</code>.</p>\n",
    ]


def _privacidad(nombre: str, contacto: str, pub: str) -> list[str]:
    """La política de privacidad.

    El apartado 2 es el importante y el que casi todas las políticas de bots
    tienen mal: este bot **no lee mensajes** para funcionar. Tiene el intent de
    contenido activado porque los comandos con prefijo `!` siguen existiendo y
    Discord lo exige para leerlos, y eso hay que declararlo tal cual en vez de
    afirmar que no se accede al contenido.
    """
    partes = [
        '  <h2 id="privacidad">Privacy Policy</h2>\n',
        "  <h3>1. Who is responsible</h3>\n",
        f"  <p>The data controller is whoever operates {nombre}, reachable in "
        f"{contacto}. There is no company behind it: this is a personal "
        "project.</p>\n",
        "  <h3>2. Discord messages</h3>\n",
        "  <p>The bot <strong>does not store messages</strong>. It holds the "
        "message content permission because prefix commands (<code>!live</code>) "
        "still work and Discord requires it in order to read them; messages are "
        "processed in memory to check whether they are a command and then "
        "discarded. They are not archived, analysed or sent to anyone. Using the "
        "<code>/</code> commands is recommended, since they require reading "
        "nothing.</p>\n",
        "  <h3>3. What is stored</h3>\n",
        "  <table>\n"
        "      <thead>\n"
        "        <tr><th>Data</th><th>What for</th><th>How long</th></tr>\n"
        "      </thead>\n"
        "      <tbody>\n"
        f"{datos_html()}\n"
        "      </tbody>\n"
        "    </table>\n",
        "  <p>No email address, password, IP address or payment method is asked for "
        "or stored. The bot has no user account: the unit of configuration is the "
        "Discord server, not the person.</p>\n",
        "  <h3>4. Professional player data</h3>\n",
        "  <p>The summoner names, PUUIDs, ranks and games the bot shows are public "
        "data obtained from the Riot Games API and from public esports sources, "
        "about the accounts of professional players. No data is collected from the "
        "League of Legends accounts of the people using the bot.</p>\n",
        "  <h3>5. Who it is shared with</h3>\n",
        "  <p>With nobody for commercial purposes. Data is sent only to the "
        "services the bot needs in order to work: Discord (to post the messages) "
        "and the Riot Games API (to look up games and ranks). It is not sold or "
        "transferred to third parties.</p>\n",
        "  <h3>6. Your rights</h3>\n",
        "  <p>You can delete all configuration for a server by kicking the bot or "
        "running <code>/unsubscribe</code>. To access, rectify or delete any other "
        "data, or to object to the processing, write in "
        f"{contacto}: you will get a reply within 30 days at the most.</p>\n",
    ]
    partes.append(_seccion_cookies(pub))
    partes.extend([
        "  <h3>8. Minors</h3>\n",
        "  <p>The bot is intended for people who meet Discord's minimum age in "
        "their country (13, or higher where the law requires it). Data is not "
        "knowingly collected from anyone below that age; if it happens, it is "
        "deleted as soon as it is detected or reported.</p>\n",
        "  <h3>9. Changes</h3>\n",
        "  <p>If this policy changes, the date in the header changes and the change "
        f"is announced in {contacto}. The version in force is always the one on "
        "this page.</p>\n",
    ])
    return partes


# ---------------------------------------------------------------------- #
# Escritura
# ---------------------------------------------------------------------- #

def construir(sitio: str, fecha: str, pub: str) -> list[Pagina]:
    """Todas las páginas del sitio, en una sola lista.

    Esta lista es la fuente única: de ella salen los ficheros HTML **y** el
    `sitemap.xml` **y** las imágenes que hay que copiar. Que sea una sola es lo
    que hace imposible el fallo clásico de añadir una página y olvidarse del
    sitemap, que era el primer punto de la lista técnica del usuario ("sitemap
    generado desde las rutas reales, nunca mantenido a mano").

    El orden es el de importancia y se refleja en `prioridad`: portada, hub,
    las dos páginas que tienen que posicionar, las 20 de liga, el legal y el 404.
    """
    return [
        pagina_inicio(pub, sitio, fecha),
        pags.pagina_ligas(sitio, fecha, pub),
        # El calendario va segundo y no al final por una razón medible: es la
        # única página cuyo contenido cambia sin que nadie toque el repositorio.
        # Un rastreador que vuelve y encuentra algo nuevo es un rastreador que
        # vuelve más a menudo, y eso se contagia al resto del sitio.
        pags.pagina_partidos(sitio, fecha, pub),
        pags.pagina_avisos(sitio, fecha, pub),
        pags.pagina_comparativa(sitio, fecha, pub),
        *[pags.pagina_liga(codigo, sitio, fecha, pub) for codigo in LIGAS],
        pagina_legal(pub, fecha),
        pags.pagina_404(sitio, pub),
    ]


def _catalogo_imagenes() -> dict[str, str]:
    """Índice `ruta en la web -> fichero original` de todas las imágenes posibles.

    No son las usadas, son las candidatas: las fotos de los jugadores que alguna
    página puede pintar y los logos de los equipos de las 20 ligas. Sirve para
    resolver lo que las páginas hayan referenciado de verdad.

    Hay que recorrer **las dos** fuentes de jugadores. Con solo `jugadores()` —los
    50 barridos de la LEC— la comprobación daba 15 huérfanas en cuanto las páginas
    de las otras 19 ligas empezaron a pintar sus rankings: las fotos de Chovy,
    Canyon o Bwipo sí están en `assets/`, pero no eran candidatas porque su
    jugador no está en el barrido. Y una huérfana es motivo para no publicar, así
    que la comprobación habría bloqueado la publicación por un fallo suyo.
    """
    catalogo: dict[str, str] = {}
    nombres = {j.nombre for j in datos.jugadores()}
    for codigo in LIGAS:
        nombres.update(c.nombre for c in datos.clasificacion_de(codigo))
    for nombre in nombres:
        imagen = datos.imagen_de_jugador(nombre)
        if imagen:
            catalogo[imagen.src] = imagen.origen
    for codigo in LIGAS:
        for tricode in datos.equipos_de(codigo):
            imagen = datos.imagen_de_equipo(tricode)
            if imagen:
                catalogo[imagen.src] = imagen.origen
    return catalogo


#: Las referencias a imágenes locales del HTML ya montado. Solo `img/`: `og.png`
#: y `favicon.svg` se generan y no se copian.
_REF_IMG = re.compile(r'src="(img/[^"]+)"')


def copiar_imagenes(paginas: list[Pagina], destino: str) -> tuple[int, list[str]]:
    """Copia a `destino` **solo** las imágenes que el HTML referencia.

    Se extraen del HTML ya montado, no de una lista aparte, por el mismo motivo
    que el sitemap sale de las páginas escritas: si una plantilla deja de pintar
    fotos, dejan de copiarse solas; y si empieza a pintar una que no existe, sale
    aquí como referencia sin origen en vez de como un 404 en producción.

    Devuelve `(copiadas, huérfanas)`. Una huérfana es un `<img>` apuntando a algo
    que no está en `assets/`, y es motivo para no publicar.
    """
    catalogo = _catalogo_imagenes()
    referencias = sorted({ref for p in paginas for ref in _REF_IMG.findall(p.cuerpo)})
    copiadas = 0
    huerfanas: list[str] = []
    for ref in referencias:
        origen = catalogo.get(ref)
        if not origen or not os.path.exists(origen):
            huerfanas.append(ref)
            continue
        final = os.path.join(destino, *ref.split("/"))
        os.makedirs(os.path.dirname(final), exist_ok=True)
        # `copy2` conserva la fecha de modificación: así el repositorio no
        # registra 48 imágenes "nuevas" e idénticas en cada regeneración.
        shutil.copy2(origen, final)
        copiadas += 1
    return copiadas, huerfanas


def _escribir(ruta: str, contenido: str) -> int:
    """Escribe texto y devuelve los bytes en disco.

    `newline="\\n"` a propósito: en Windows el modo texto convierte cada `\\n` en
    `\\r\\n`, y la web se publica desde un repositorio Git donde eso marcaría el
    fichero entero como cambiado al regenerarlo desde otro sistema operativo.
    """
    with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(contenido)
    return len(contenido.encode("utf-8"))


def _duplicados(paginas: list[Pagina]) -> list[str]:
    """Títulos o descripciones repetidos entre páginas.

    Se comprueba aquí y no solo en las pruebas porque es el fallo que más fácil
    se cuela al añadir una plantilla: 20 páginas de liga con el mismo `<title>`
    son 20 páginas que compiten entre ellas y de las que Google indexa una.
    """
    problemas = []
    for campo, etiqueta in (("titulo", "título"), ("descripcion", "descripción")):
        vistos: dict[str, str] = {}
        for pagina in paginas:
            valor = getattr(pagina, campo)
            if valor in vistos:
                problemas.append(
                    f"{etiqueta} repetida en {vistos[valor]} y {pagina.ruta}: {valor!r}"
                )
            vistos[valor] = pagina.ruta
    return problemas


#: Ventana en la que una meta descripción se ve entera en el resultado de
#: búsqueda. El límite real de Google es en píxeles y no en caracteres, así que
#: no hay un número exacto; 190 es el punto donde una línea larga empieza a
#: salir cortada con "..." y 70 es el punto por debajo del cual Google prefiere
#: escribir su propio resumen tomando texto de la página.
DESC_MIN, DESC_MAX = 70, 190


def _snippets(paginas: list[Pagina]) -> list[str]:
    """Títulos y descripciones que no caben en el resultado de búsqueda.

    Se comprueba en la generación y no solo en las pruebas porque es un fallo
    invisible: la página se ve perfecta y lo que sale roto es el snippet, que
    solo se ve buscándola en Google una semana después. Una descripción que se
    corta a mitad de frase deja de ser la promesa que hace que alguien entre.
    """
    problemas = []
    for pagina in paginas:
        if len(pagina.titulo) > 70:
            problemas.append(
                f"título de {len(pagina.titulo)} caracteres en {pagina.ruta} "
                "(Google corta sobre 70)"
            )
        largo = len(pagina.descripcion)
        if not DESC_MIN <= largo <= DESC_MAX:
            problemas.append(
                f"descripción de {largo} caracteres en {pagina.ruta} "
                f"(cabe entre {DESC_MIN} y {DESC_MAX})"
            )
    return problemas


def main(argv: list[str] | None = None) -> int:
    """Genera el sitio completo en `web/`.

    Devuelve un código de salida en vez de llamar a `sys.exit` para que se pueda
    invocar desde una prueba sin que la prueba muera con el script. Devuelve 1 —y
    no 0 con un aviso— cuando hay títulos duplicados, snippets que no caben o
    imágenes huérfanas: son las tres cosas que no se ven mirando la web y sí
    rompen el SEO.
    """
    parser = argparse.ArgumentParser(
        description="Genera la web de " + branding.BOT_NOMBRE,
        epilog=(
            "El ID de AdSense es opcional y va al final del proceso: primero se "
            "publica la web, después se pide la aprobación de AdSense (que exige "
            "un sitio en vivo con política de privacidad) y solo entonces se "
            "vuelve a ejecutar esto con --adsense."
        ),
    )
    parser.add_argument(
        "--adsense", default="", metavar="ca-pub-XXXX",
        help="ID de publicador de AdSense. Sin él no se carga ningún script de terceros.",
    )
    parser.add_argument(
        "--destino", default=DESTINO, metavar="DIR",
        help=f"Carpeta de salida (por defecto {DESTINO}).",
    )
    parser.add_argument(
        "--fecha", default=HOY, metavar="AAAA-MM-DD",
        help="Fecha de los documentos legales y de `dateModified`. Por defecto, hoy.",
    )
    parser.add_argument(
        "--sitio", default="", metavar="URL",
        help=(
            "Dominio del sitio para los canónicos y el sitemap. Por defecto "
            f"BOT_WEB_URL, y si no está, {seo.SITIO_POR_DEFECTO}"
        ),
    )
    args = parser.parse_args(argv)

    pub = normalizar_pub(args.adsense)
    sitio = seo.normalizar_sitio(args.sitio or branding.WEB_URL)
    os.makedirs(args.destino, exist_ok=True)

    paginas = construir(sitio, args.fecha, pub)
    total = 0
    for pagina in paginas:
        tamano = _escribir(
            os.path.join(args.destino, pagina.ruta),
            maq.montar(pagina, pub, sitio),
        )
        total += tamano
        marca = "" if pagina.indexable else "  (noindex, fuera del sitemap)"
        print(f"  {pagina.ruta:38} {tamano:7d} B{marca}")

    total += _escribir(
        os.path.join(args.destino, "sitemap.xml"),
        seo.sitemap(sitio, paginas, args.fecha),
    )
    total += _escribir(os.path.join(args.destino, "robots.txt"), seo.robots(sitio))
    total += _escribir(
        os.path.join(args.destino, "favicon.svg"), og.favicon(branding.BOT_NOMBRE)
    )

    tarjeta = og.tarjeta(branding.BOT_NOMBRE, len(LIGAS), "PRO SOLOQ ALERTS")
    with open(os.path.join(args.destino, "og.png"), "wb") as fh:
        fh.write(tarjeta)
    total += len(tarjeta)

    # La hoja de estilos se mantiene a mano y vive en `web/`. Si se genera en
    # otra carpeta hay que llevársela, o el HTML sale sin maquetar y Google lo
    # juzga como no apto para móvil.
    css_origen = os.path.join(RAIZ, "web", "styles.css")
    css_destino = os.path.join(args.destino, "styles.css")
    if os.path.exists(css_origen) and os.path.abspath(css_origen) != os.path.abspath(css_destino):
        shutil.copy2(css_origen, css_destino)

    copiadas, huerfanas = copiar_imagenes(paginas, args.destino)
    problemas = _duplicados(paginas) + _snippets(paginas)

    indexables = sum(1 for p in paginas if p.indexable)
    faltan = [
        var for var, valor in (
            ("BOT_INVITE_URL", branding.INVITE_URL),
            ("BOT_SOPORTE_URL", branding.SOPORTE_URL),
            ("BOT_DONATE_URL", branding.DONATE_URL),
            ("BOT_WEB_URL", branding.WEB_URL),
        ) if not valor
    ]

    print(
        f"\n{len(paginas)} páginas ({indexables} en el sitemap) · {copiadas} "
        f"imágenes · {total // 1024} kB · {args.destino}"
    )
    print(f"{len(LIGAS)} ligas · {len(PLANES)} planes · canónicos en {sitio}")
    # El estado del histórico se informa siempre, porque es la diferencia entre
    # publicar una página con avisos reales y publicar solo el formato, y no se
    # nota mirando la lista de ficheros: `avisos.html` pesa parecido en los dos
    # casos. Si sale en cero desde una máquina de desarrollo es lo normal: el
    # fichero lo escribe el bot en marcha, no el generador.
    registrados = datos.avisos(pags.TOPE_AVISOS)
    if registrados:
        print(
            f"Histórico de avisos: {len(registrados)} publicados en avisos.html "
            f"(el último, {registrados[0].fecha} {registrados[0].hora} UTC)"
        )
    else:
        print(
            "Histórico de avisos: vacío (avisos.html enseña solo el formato). "
            "Lo escribe el bot en tracking/soloq/avisos.jsonl al enviar un aviso."
        )
    if pub:
        print(f"AdSense activo: {pub}")
    else:
        print("AdSense: sin activar (hueco reservado, ningún script de terceros).")
    if faltan:
        print(
            "Enlaces sin configurar (los botones saldrán apagados): "
            + ", ".join(faltan)
        )
    for problema in problemas:
        print(f"ERROR: {problema}")
    if huerfanas:
        print("ERROR: imágenes referenciadas que no existen en assets/: "
              + ", ".join(huerfanas))
    return 1 if problemas or huerfanas else 0


if __name__ == "__main__":
    raise SystemExit(main())








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
    leagues.html                          el hub que enlaza las 20 ligas
    liga-<codigo>.html                  una por liga, con sus datos reales
    alerts.html                         qué es un aviso, con ejemplo
    lol-discord-bots.html  la comparativa
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

from tracking.soloq.leagues import LIGAS, MAX_LIGAS_POR_SERVIDOR, REGION_EN  # noqa: E402
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
            f" <span>{e(liga.region_en)}</span>{marca}</li>"
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


#: Cómo se llama cada plan **en la web**.
#:
#: `Plan.nombre` es la etiqueta que usa el bot en sus respuestas, y ahí «Gratis»
#: es lo correcto: la mitad de los servidores están en español y el plan se llama
#: así en el embed de `/premium`. La web, en cambio, se publica solo en inglés, y
#: usar `plan.nombre` tal cual dejaba un «Gratis» en medio de una página inglesa,
#: justo en la sección donde alguien decide si paga.
#:
#: Va por **código** (`gratis`, `pro`) y no por nombre: el código es la clave de
#: `PLANES` y no cambia si alguien reescribe la etiqueta. Si aparece un plan nuevo
#: y no está aquí, se cae a `plan.nombre` —que es la etiqueta del bot— en vez de
#: dejar la tarjeta sin título.
NOMBRE_PLAN_WEB: dict[str, str] = {
    "gratis": "Free",
    "pro": "Pro",
}


def _precio(plan) -> str:
    """`0 €` o `5,00 € / month`, con coma decimal.

    La coma es la convención del euro y de la audiencia —ligas europeas, precios
    en €—, y además es lo que ya usaba la web en español: cambiarla a punto haría
    que el mismo precio se leyera distinto según la página, que es la señal de
    que el sitio lo han tocado dos manos sin hablarlo. Lo que sí cambió al pasar
    la web a inglés es la unidad, que ahora dice `month` y no `mes`.
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
            f"        <h3>{e(NOMBRE_PLAN_WEB.get(codigo, plan.nombre))}</h3>\n"
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
        "📊 <code>/ranking</code> · <code>/history</code> · <code>/team</code>",
        "The SoloQ ladder of an entire league, the latest tracked games, and a "
        "team's roster with the rank of every player on it.",
    ),
    (
        "🏆 <code>/esports</code> · <code>/schedule</code>",
        "Live official matches and the schedule of the next ones, across every "
        "league, not only the ones you follow in SoloQ.",
    ),
    (
        "🌍 English and Spanish",
        "<code>/language en</code> switches the whole bot to that language on that "
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

    `PLANES` está indexado por código (`"gratis"`, `"pro"`) y
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
            "leagues.html",
            f"All {len(LIGAS)} leagues, one by one",
            "How many players and teams each league has, and what is published "
            "about each one.",
        ),
        (
            "alerts.html",
            "What the alert looks like",
            "The exact message that shows up in Discord, how long it takes and "
            "why the in-game clock runs behind.",
        ),
        (
            "lol-discord-bots.html",
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


def _aviso_ejemplo_html() -> str:
    """El aviso de ejemplo que abre la portada.

    Es lo más característico de este producto —lo que ve alguien cuando un pro
    entra en cola— y por eso ocupa el hero en vez de un bloque de cifras, que lo
    pone cualquier página. Va **marcado como ejemplo**: el nombre y el equipo son
    de un pro real, la partida no, y hacer pasar una partida inventada por una
    real es exactamente lo que no se puede hacer en una web que presume de datos.
    """
    return (
        '      <div class="hero-aviso">\n'
        '        <article class="aviso">\n'
        '          <div class="aviso-cab">\n'
        '            <span class="aviso-badge">FNC</span>\n'
        "            <div>\n"
        '              <p class="aviso-titulo">Vladi is in a SoloQ game</p>\n'
        '              <p class="aviso-sub">Mid · Fnatic · EUW</p>\n'
        "            </div>\n"
        "          </div>\n"
        '          <dl class="aviso-datos">\n'
        "            <dt>Queue</dt><dd>Ranked Solo/Duo</dd>\n"
        "            <dt>Champion</dt><dd>Ahri</dd>\n"
        "            <dt>Rank</dt><dd>Challenger I · 1204 LP</dd>\n"
        "            <dt>Spectate</dt><dd>in 2 min</dd>\n"
        "          </dl>\n"
        '          <p class="aviso-pie">All ten participants with their ranks, a '
        "<code>.bat</code> to spectate from the client, and a note on when "
        "spectator mode opens.</p>\n"
        "        </article>\n"
        '        <p class="aviso-nota">Example alert — the player is real, the '
        "game is not.</p>\n"
        "      </div>\n"
    )


def _apoyo_html() -> str:
    """La sección que explica de dónde salen los límites y pide ayuda.

    Por qué está en la portada y no en una página aparte
    ---------------------------------------------------
    Es la única página que ve quien llega de fuera, y el límite es lo primero que
    va a notar: elige una liga, quiere dos, y no puede. Sin explicación, eso se
    lee como un muro de pago y se va. Con explicación, se lee como lo que es —una
    cuota que pone Riot— y además se convierte en una petición de ayuda que el
    visitante puede atender sin pagar nada.

    Cómo está construida, porque no es copy suelto
    ----------------------------------------------
    1. **La restricción es externa, concreta y con número.** «Riot gives us 500
       requests every 10 seconds» es verificable y por eso se cree; «technical
       limitations» no. El número sale de `branding`, no de aquí, para que no se
       quede viejo.
    2. **Se dice dos veces que lo importante es gratis.** Si alguien cree que hay
       que pagar para recibir avisos, no instala el bot, y entonces no hay nada
       que crecer ni que vender.
    3. **El mecanismo es real y se explica**: más servidores es exactamente lo que
       Riot mira para conceder más cuota. Eso permite poner «compartir» **el
       primero** de la lista sin que sea un premio de consolación para quien no
       paga: es la acción que de verdad sube los límites. Si esto fuera mentira,
       toda la sección sería un truco y el visitante lo notaría.
    4. **Escalera de menos a más esfuerzo** (compartir / añadir / contárselo /
       Ko-fi) para que haya algo que hacer a cualquier nivel de compromiso.
    5. **Sin culpabilidad.** Nada de «ayúdanos o desaparecemos». Una petición que
       hace sentir mal convierte peor y quema al que ya estaba dentro.

    Y no se inventa ninguna cifra de alcance: cuántos servidores usan el bot hoy
    no se publica (ver `AGENTS.md`), así que la meta se cuenta en futuro —«cada
    servidor que se añade es un número más en esa petición»— y no como un
    contador que no existe.
    """
    donar, donar_attr = maq.url(branding.DONATE_URL)
    invite, invite_attr = maq.url(branding.INVITE_URL)
    req = branding.RIOT_CUOTA_PETICIONES
    seg = branding.RIOT_CUOTA_SEGUNDOS

    acciones = (
        (
            "🔗",
            "Share it",
            "It costs nothing and it is what actually raises the limits. Every "
            "server that adds the bot is one more number in the request we take "
            "to Riot.",
        ),
        (
            "➕",
            "Add it to your server",
            "Even if you only look at the alerts now and then. A server with the "
            "bot in it counts, whether or not anyone types a command.",
        ),
        (
            "💬",
            "Tell someone who plays",
            "Esports followers are the audience: the people who want to know when "
            "their favourite mid laner is on.",
        ),
        (
            "💛",
            "Support on Ko-fi",
            "If you would rather put money in. It pays for the server the bot "
            "runs on and speeds the whole thing up.",
        ),
    )
    tarjetas = "\n".join(
        '      <article class="tarjeta">\n'
        f'        <div class="ico">{ico}</div>\n'
        f"        <h3>{e(titulo)}</h3>\n"
        f"        <p>{e(texto)}</p>\n"
        "      </article>"
        for ico, titulo, texto in acciones
    )

    return (
        '  <section id="apoyo" class="apoyo">\n'
        '    <div class="envoltura">\n'
        "      <h2>Why the free plan <span class=\"res\">has limits</span></h2>\n"
        '      <p class="sub">It is not our call.</p>\n'
        '      <div class="apoyo-texto">\n'
        f"        <p>Riot Games gives every third-party app "
        f"<b>{req} requests every {seg} seconds</b>. That is the whole budget, "
        f"and out of it the bot can follow <b>{MAX_LIGAS_POR_SERVIDOR} leagues at "
        "a time per server</b>. It is a physical ceiling, not a paywall: the game "
        "alert —the part that matters— is free and always will be.</p>\n"
        "        <p>The other half is the interesting one. "
        "<b>The more servers use the bot, the bigger the community we can show "
        "Riot</b> when we ask for a larger quota, and a larger quota means higher "
        "limits for everyone — the free plan included. So this is not really about "
        "paying. It is about growing.</p>\n"
        "      </div>\n"
        '      <div class="grid">\n'
        f"{tarjetas}\n"
        "      </div>\n"
        '      <div class="apoyo-cierre">\n'
        '        <p class="apoyo-gracias">Thank you, genuinely: this is run by '
        "one person.</p>\n"
        '        <div class="botones">\n'
        f'          <a class="btn" href="{invite}"{invite_attr}>⚡ Add to Discord</a>\n'
        f'          <a class="btn bronce" href="{donar}"{donar_attr}>💛 Support on Ko-fi</a>\n'
        "        </div>\n"
        "      </div>\n"
        "    </div>\n"
        "  </section>\n"
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
        # ---- Hero ------------------------------------------------------- #
        #
        # Dos columnas: a la izquierda qué es y el botón; a la derecha **el
        # aviso**, que es lo más característico de este producto y por eso es lo
        # que abre la página. Un bloque de cifras con una etiqueta debajo lo pone
        # cualquiera; el embed que aparece solo en tu canal, no.
        '  <header class="hero">\n'
        '    <div class="envoltura hero-fila">\n'
        '      <div class="hero-texto">\n'
        f'        <span class="onair"><span class="punto"></span>Live · '
        f"{len(LIGAS)} leagues</span>\n"
        "        <h1>When a <span class=\"grad\">pro</span> queues up,\n"
        "        your server knows</h1>\n"
        '        <p class="lema">Champion, role, rank and team the moment the '
        f"game starts. The Discord bot watching <b>{total_pros} professional "
        "League of Legends players</b> — and you don't type a single command.</p>\n"
        '        <div class="botones">\n'
        f'          <a class="btn" href="{invite}"{invite_attr}>⚡ Add to Discord</a>\n'
        '          <a class="btn sec" href="commands.html">See the commands</a>\n'
        f'          <a class="btn sec" href="{donar}"{donar_attr}>Support the project</a>\n'
        "        </div>\n"
        "      </div>\n"
        f"{_aviso_ejemplo_html()}\n"
        "    </div>\n"
        '    <div class="envoltura">\n'
        '      <div class="stats">\n'
        f'        <div class="stat"><div class="n" data-count="{len(LIGAS)}">'
        f'{len(LIGAS)}</div><div class="l">Leagues</div></div>\n'
        f'        <div class="stat"><div class="n" data-count="{total_pros}">'
        f'{total_pros}</div><div class="l">Pros tracked</div></div>\n'
        '        <div class="stat"><div class="n" data-count="30">30'
        '<span class="u">s</span></div><div class="l">Max delay</div></div>\n'
        '        <div class="stat"><div class="n">0<span class="u">€</span></div>'
        '<div class="l">Free, always</div></div>\n'
        "      </div>\n"
        "    </div>\n"
        "  </header>\n"
        "\n"
        # ---- Qué hace --------------------------------------------------- #
        '  <section id="funciones">\n'
        '    <div class="envoltura">\n'
        "      <h2>What <span class=\"res\">it does</span></h2>\n"
        '      <p class="sub">Everything here works on the free plan. The alert '
        "is the point; the commands are for looking things up in between.</p>\n"
        f"{pags.tldr(resumen)}\n"
        '      <div class="grid">\n'
        f"{funciones_html()}\n"
        "      </div>\n"
        '      <div class="teams" id="teams-strip">'
        "<!-- logos inyectados por live.js --></div>\n"
        "    </div>\n"
        "  </section>\n"
        "\n"
        # ---- Avisos recientes ------------------------------------------- #
        '  <section id="live">\n'
        '    <div class="envoltura">\n'
        "      <h2>Recent <span class=\"res\">alerts</span></h2>\n"
        '      <p class="sub">What the bot has actually detected, straight from '
        "its own alert log.</p>\n"
        '      <div class="feed" id="feed">\n'
        '        <div class="vacio">Loading recent alerts…</div>\n'
        "      </div>\n"
        "    </div>\n"
        "  </section>\n"
        "\n"
        # ---- Ligas ------------------------------------------------------ #
        '  <section id="ligas">\n'
        '    <div class="envoltura">\n'
        f"      <h2>{len(LIGAS)} <span class=\"res\">leagues</span></h2>\n"
        '      <p class="sub">Each server picks the ones it follows with '
        f"<code>/leagues</code>, up to {MAX_LIGAS_POR_SERVIDOR} at a time — "
        '<a href="#apoyo">why that number and not more</a>. Every '
        'league has <a href="leagues.html">its own page</a> with its players, their '
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
        # ---- Por qué hay límites, y cómo se suben ----------------------- #
        #
        # Va justo después de las ligas a propósito: es donde el visitante acaba
        # de leer el tope y se pregunta por qué. La explicación pegada a la
        # limitación se lee; la misma explicación tres pantallas más abajo, no.
        f"{_apoyo_html()}"
        "\n"
        # ---- Antes de instalarlo ---------------------------------------- #
        '  <section id="mas">\n'
        '    <div class="envoltura">\n'
        "      <h2>Before you <span class=\"res\">install it</span></h2>\n"
        '      <div class="grid">\n'
        f"{_destacados_html()}\n"
        "      </div>\n"
        "    </div>\n"
        "  </section>\n"
        "\n"
        # ---- Planes ----------------------------------------------------- #
        '  <section id="planes">\n'
        '    <div class="envoltura">\n'
        "      <h2>Two <span class=\"res\">plans</span></h2>\n"
        '      <p class="sub">The alert is free and always will be. What you pay '
        "for is volume: more leagues at once, more channels and more history.</p>\n"
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
        # ---- Marcas ----------------------------------------------------- #
        '  <section class="sponsor-cta" id="marcas">\n'
        '    <div class="envoltura">\n'
        "      <h2>Brands and <span class=\"res\">sponsors</span></h2>\n"
        '      <p class="sub">The moment a pro queues up is the moment people '
        "look. That is a qualified audience at a known time, and it is what this "
        "site can put a brand in front of.</p>\n"
        '      <div class="botones">\n'
        '        <a class="btn bronce" href="partners.html">Partnership proposal</a>\n'
        '        <a class="btn sec" href="alerts.html">How an alert looks</a>\n'
        "      </div>\n"
        "    </div>\n"
        "  </section>\n"
        "\n"
        # ---- FAQ -------------------------------------------------------- #
        '  <section id="faq">\n'
        '    <div class="envoltura">\n'
        "      <h2>Frequently asked <span class=\"res\">questions</span></h2>\n"
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
        arena=True,
        # La portada es la única con `#teams-strip` y `#feed`, así que es la única
        # que carga `live.js`.
        en_vivo=True,
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
        "Until <code>/mute</code> runs or the bot is kicked.",
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


def pagina_legal(pub: str, hoy: str = HOY, sitio: str = "") -> Pagina:
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
    # `sitio` entra por parámetro desde el 29-09-2026, cuando la página pasó a
    # llevar schema: `seo.absoluta()` necesita la URL base para el `url` del
    # `WebPage`. Se deja con valor por defecto —el sitio del proyecto— para que
    # `test_web`, que la llama con dos argumentos, siga funcionando sin tocarla.
    sitio = sitio or SITIO
    return Pagina(
        ruta="legal.html",
        titulo=f"Terms of Service and Privacy Policy · {branding.BOT_NOMBRE}",
        descripcion=(
            f"Terms of service and privacy policy of {branding.BOT_NOMBRE}: what "
            "data the bot stores, what for, and for how long."
        ),
        cuerpo="".join(partes),
        # Es la única página sin schema junto con `commands.html`. Lleva `WebPage`
        # y no `Article` a propósito: un documento legal no es un artículo con
        # autor ni fecha de publicación, es la ficha de una URL concreta —la que
        # Discord y AdSense comprueban que existe— y `WebPage` es lo que la
        # describe sin inventarle metadatos que no tiene.
        schemas=[
            seo.jsonld(seo.migas(sitio, [
                ("Home", "index.html"), ("Terms & privacy", "legal.html"),
            ])),
            seo.jsonld({
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": f"Terms of Service and Privacy Policy · {branding.BOT_NOMBRE}",
                "description": (
                    f"Terms of service and privacy policy of {branding.BOT_NOMBRE}: "
                    "what data the bot stores, what for, and for how long."
                ),
                "url": seo.absoluta(sitio, "legal.html"),
                "inLanguage": seo.IDIOMA,
            }),
        ],
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
        "alerts with <code>/mute</code>.</p>\n",
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
        "running <code>/mute</code>. To access, rectify or delete any other "
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
        pags.pagina_comandos(sitio, fecha, pub),
        pags.pagina_comparativa(sitio, fecha, pub),
        *[pags.pagina_liga(codigo, sitio, fecha, pub) for codigo in LIGAS],
        pagina_legal(pub, fecha),
        pags.pagina_404(sitio, pub),
    ]


#: Páginas que se mantienen **a mano** en `web/`, se despliegan con el resto y
#: también tienen que estar en el sitemap.
#:
#: No salen de `construir()` —no las escribe el generador, así que no se pueden
#: perder al regenerar— pero sí son parte del sitio, y una página indexable fuera
#: del sitemap se descubre más tarde y peor. `(ruta, prioridad)`.
#:
#: Hoy es solo la landing de patrocinios: es la página que se manda a una marca
#: por correo, y que Google no la tenga declarada sería absurdo.
PAGINAS_A_MANO: tuple[tuple[str, str], ...] = (
    ("partners.html", "0.6"),
)


#: Rutas antiguas que hay que redirigir, `{vieja: nueva}`.
#:
#: El 29-09-2026 las URLs pasaron de español a inglés (`ligas.html` →
#: `leagues.html`, `liga-lec.html` → `league-lec.html`). El contenido ya estaba
#: en inglés desde hacía una semana, así que tener la URL en español era una
#: señal contradictoria: la URL es parte de lo que Google lee.
#:
#: Se hizo **ahora y no más tarde** a propósito: el sitio casi no está indexado,
#: así que el coste de moverlo es casi cero. Dentro de un año, con tráfico,
#: habría que montar redirecciones para no perder lo ganado — y en un sitio
#: estático no hay redirecciones de servidor, solo este apaño.
#:
#: GitHub Pages no sabe devolver un 301 (no hay servidor), así que la redirección
#: se hace con un fichero en la ruta vieja que lleva un `meta refresh` **y un
#: canónico a la nueva**. El canónico es lo que hace el trabajo de verdad: le dice
#: a Google cuál es la URL buena. El `refresh` es para la persona que tenía el
#: enlace guardado.
#:
#: Estas páginas **no van al sitemap** y se pueden borrar el día que no quede
#: nada apuntando a las rutas viejas.
REDIRECCIONES: dict[str, str] = {
    "ligas.html": "leagues.html",
    "avisos.html": "alerts.html",
    "alternativas-bots-lol-discord.html": "lol-discord-bots.html",
    "socios.html": "partners.html",
    **{f"liga-{codigo}.html": f"league-{codigo}.html" for codigo in LIGAS},
}


def _redireccion_html(vieja: str, nueva: str, sitio: str) -> str:
    """El HTML de una redirección estática.

    Sin `noindex` a propósito. Es tentador ponerlo para que la página vieja no
    aparezca en Google, pero Google avisa de que `noindex` y `canonical` juntos se
    contradicen: si la página no debe indexarse, el canónico se ignora y la
    autoridad no se transfiere, que es justo lo contrario de lo que se busca.
    Lo que se quiere es que la vieja desaparezca **a favor de la nueva**, y eso lo
    hace el canónico solo.
    """
    destino = seo.absoluta(sitio, nueva)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f'  <link rel="canonical" href="{seo.e(destino)}">\n'
        f'  <meta http-equiv="refresh" content="0; url={seo.e(nueva)}">\n'
        f"  <title>Moved to {seo.e(nueva)}</title>\n"
        "</head>\n"
        "<body>\n"
        f'  <p>This page moved to <a href="{seo.e(nueva)}">{seo.e(nueva)}</a>.</p>\n'
        "</body>\n"
        "</html>\n"
    )


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


def _regiones_sin_ingles() -> list[str]:
    """Regiones del catálogo que no tienen rótulo en inglés.

    `Liga.region_en` cae al español si la región no está en `REGION_EN`, y eso es
    lo correcto como red de seguridad: prefiero una web con una palabra en
    español a una web que no se genera. Pero el resultado sería una página en
    inglés con «LCK Corea» dentro, y eso no se nota revisando la portada —la
    región sale en las fichas de liga y en los `ItemList`—, así que se avisa aquí,
    que es donde se arregla: añadir la línea a `REGION_EN`.

    Pasó al añadir la vigésima liga: el catálogo creció y la tabla de traducción
    no, y el síntoma era una palabra suelta en español en una página en inglés.
    """
    faltan = sorted({liga.region for liga in LIGAS.values() if liga.region not in REGION_EN})
    return [
        f"la región {region!r} no tiene traducción en REGION_EN (leagues.py)"
        for region in faltan
    ]


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
        seo.sitemap(sitio, paginas, args.fecha, extras=PAGINAS_A_MANO),
    )
    total += _escribir(os.path.join(args.destino, "robots.txt"), seo.robots(sitio))

    # Redirecciones de las rutas viejas (ver `REDIRECCIONES`). Se escriben al
    # final y no cuentan para el total de páginas: no son páginas del sitio, son
    # carteles que mandan a la nueva.
    for vieja, nueva in REDIRECCIONES.items():
        _escribir(
            os.path.join(args.destino, vieja),
            _redireccion_html(vieja, nueva, sitio),
        )
    total += _escribir(
        os.path.join(args.destino, "favicon.svg"), og.favicon(branding.BOT_NOMBRE)
    )

    tarjeta = og.tarjeta(branding.BOT_NOMBRE, len(LIGAS), "PRO SOLOQ ALERTS")
    with open(os.path.join(args.destino, "og.png"), "wb") as fh:
        fh.write(tarjeta)
    total += len(tarjeta)

    # Los ficheros que se mantienen **a mano** y viven en `web/`: las dos hojas de
    # estilo, el `live.js` de la portada y la landing de patrocinios. Si se genera
    # en otra carpeta hay que llevárselos, o el HTML sale sin maquetar (y Google lo
    # juzga como no apto para móvil), la portada se queda con «Cargando avisos
    # recientes…» o el enlace a `partners.html` da 404.
    #
    # `styles-esports.css` y `live.js` se añadieron a esta lista el 22-09-2026,
    # **después** de perderlos: la portada del tema Arena estaba escrita a mano en
    # `web/index.html` y regenerar la pisó. Copiarlos aquí es lo que hace que una
    # regeneración ya no pueda volver a perderlos.
    #
    # `partners.html` se añadió también el 22-09-2026, al meterla en el sitemap: una
    # URL declarada a Google que no se copia es un 404 anunciado.
    for nombre in ("styles.css", "styles-esports.css", "live.js", "partners.html"):
        origen = os.path.join(RAIZ, "web", nombre)
        destino = os.path.join(args.destino, nombre)
        if os.path.exists(origen) and os.path.abspath(origen) != os.path.abspath(destino):
            shutil.copy2(origen, destino)

    copiadas, huerfanas = copiar_imagenes(paginas, args.destino)
    problemas = _duplicados(paginas) + _snippets(paginas) + _regiones_sin_ingles()

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
    # nota mirando la lista de ficheros: `alerts.html` pesa parecido en los dos
    # casos. Si sale en cero desde una máquina de desarrollo es lo normal: el
    # fichero lo escribe el bot en marcha, no el generador.
    registrados = datos.avisos(pags.TOPE_AVISOS)
    if registrados:
        print(
            f"Histórico de avisos: {len(registrados)} publicados en alerts.html "
            f"(el último, {registrados[0].fecha} {registrados[0].hora} UTC)"
        )
    else:
        print(
            "Histórico de avisos: vacío (alerts.html enseña solo el formato). "
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








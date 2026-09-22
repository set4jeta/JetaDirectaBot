"""Maqueta común de todas las páginas: `<head>`, pie, botones y hueco de anuncio.

Por qué es un módulo aparte
---------------------------
Estaba dentro de `generar_web.py`, y funcionaba mientras la web eran dos páginas.
Con las páginas de liga aparece un segundo módulo que también necesita el mismo
`<head>` y el mismo pie (`web_paginas.py`), y si ese importara de
`generar_web.py` —que a su vez tiene que importarlo a él para llamar a sus
páginas— sería un ciclo de importación.

Así que lo compartido vive aquí y los dos lo importan. La regla que decide qué
va en este archivo es simple: **lo que sale igual en todas las páginas**. Lo que
decide *qué dice* cada página está en su módulo, y lo que decide *cómo la leen
Google y los LLM* está en `web_seo.py`.
"""

from __future__ import annotations

import html

from tracking.soloq.leagues import LIGAS
from utils import branding

from scripts import web_seo as seo
from scripts.web_seo import Pagina


def e(texto) -> str:
    """Escapa para HTML. Los nombres de liga, equipo y jugador vienen de datos."""
    return html.escape(str(texto), quote=True)


def url(valor: str, respaldo: str = "#") -> tuple[str, str]:
    """`(href, atributo_extra)`.

    Un enlace sin configurar se deja visible pero apagado con `data-sin-url`, en
    vez de omitirlo: si desaparece el botón de invitar, la página pierde su
    única llamada a la acción y nadie se entera de que falta una variable.
    """
    if valor:
        return e(valor), ""
    return respaldo, " data-sin-url"


# ---------------------------------------------------------------------- #
# AdSense
# ---------------------------------------------------------------------- #

def normalizar_pub(valor: str) -> str:
    """Valida el ID de AdSense y le pone el prefijo si falta.

    En el panel de AdSense el identificador se enseña como `pub-1234…`, pero la
    URL del script lo quiere como `ca-pub-1234…`. Copiarlo tal cual del panel
    genera un `<script>` que **carga y no sirve anuncios**, sin ningún error
    visible: la web parece bien y no hay ingresos. Por eso se corrige aquí y se
    rechaza lo que no tenga forma de ID, en vez de dejarlo pasar.
    """
    limpio = (valor or "").strip()
    if not limpio:
        return ""
    if limpio.startswith("pub-"):
        limpio = f"ca-{limpio}"
    resto = limpio[len("ca-pub-"):]
    if not limpio.startswith("ca-pub-") or not resto.isdigit():
        raise SystemExit(
            f"ID de AdSense no válido: {valor!r}. Se espera 'ca-pub-' seguido de "
            "dígitos (en el panel de AdSense sale como 'pub-...')."
        )
    return limpio


def adsense_head(pub: str) -> str:
    """El `<script>` de AdSense para el `<head>`, o cadena vacía.

    Va en el `<head>` porque es lo que exigen los anuncios automáticos: con el
    script cargado, AdSense decide dónde colocarlos sin tocar el HTML. Si no hay
    ID no se carga **nada** de terceros, y por eso la política de privacidad
    generada tampoco menciona cookies publicitarias.
    """
    if not pub:
        return ""
    return (
        '  <script async src="https://pagead2.googlesyndication.com/pagead/js/'
        f'adsbygoogle.js?client={e(pub)}" crossorigin="anonymous"></script>\n'
    )


def bloque_anuncio(pub: str) -> str:
    """El hueco del anuncio dentro de la página.

    El hueco existe **siempre**, con o sin ID, porque su altura está reservada en
    el CSS: si el div apareciera solo al activar AdSense, el día que se active la
    página entera bajaría de golpe y eso es exactamente lo que Google penaliza
    como CLS. Sin ID dice para qué es, y no carga nada.
    """
    if not pub:
        return (
            '    <div class="anuncio">Espacio reservado para publicidad '
            "(sin activar)</div>"
        )
    return (
        '    <div class="anuncio">\n'
        '      <ins class="adsbygoogle" style="display:block"\n'
        f'           data-ad-client="{e(pub)}" data-ad-format="auto"\n'
        '           data-full-width-responsive="true"></ins>\n'
        "      <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>\n"
        "    </div>"
    )


# ---------------------------------------------------------------------- #
# Cabecera y pie
# ---------------------------------------------------------------------- #

def cabeza(pagina: Pagina, pub: str, sitio: str) -> str:
    """El `<head>` común a todas las páginas.

    El `lang` sale de `seo.IDIOMA` y no está escrito aquí a propósito: es uno de
    los seis sitios que tienen que cambiar juntos cuando exista la versión
    inglesa (`lang`, `og:locale`, `inLanguage`, `hreflang`, `x-default` y el
    idioma de las FAQ), y marcar `en` una página en español rompe los lectores de
    pantalla y el traductor del navegador sin dar ningún error.

    Todo lo de SEO (título, descripción, canónico, Open Graph, Twitter Card,
    `hreflang` y los bloques JSON-LD) sale de `web_seo`, no de aquí: este módulo
    decide cómo se ve la web y aquél cómo la leen los rastreadores.
    """
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{seo.IDIOMA}">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{seo.meta_seo(pagina, sitio)}"
        '  <link rel="stylesheet" href="styles.css">\n'
        '  <link rel="icon" href="favicon.svg" type="image/svg+xml">\n'
        + "".join(pagina.schemas)
        + f"{adsense_head(pub)}"
        "</head>\n"
    )


def descargo_html() -> str:
    """El descargo de Riot en HTML, sacado de `branding`, no copiado.

    `descargo_riot()` devuelve el texto con el original inglés en cursiva de
    Markdown (`_..._`), que es lo que entiende Discord. Pegado tal cual en la web
    saldrían los guiones bajos a la vista. Se traduce el formato aquí en vez de
    duplicar el texto legal en este archivo: el día que Riot cambie la
    plantilla se toca `branding.py` y las dos superficies quedan iguales.
    """
    partes = [p.strip() for p in branding.descargo_riot().split("\n\n") if p.strip()]
    html_partes = []
    for parte in partes:
        if parte.startswith("_") and parte.endswith("_"):
            html_partes.append(f"<em>{e(parte.strip('_'))}</em>")
        else:
            html_partes.append(e(parte))
    return "<br><br>".join(html_partes)


#: La navegación, igual en todas las páginas. No es decoración: son los enlaces
#: que hacen que un rastreador que entre por una página de liga encuentre las
#: demás **sin depender del sitemap**, y es la parte de "buenos enlaces
#: apuntando a esas páginas" que sí se controla desde dentro del sitio.
#:
#: Las 20 páginas de liga no van aquí sino en `ligas.html`, que es el hub: un
#: menú de 25 entradas repetido en 25 páginas diluye el enlace y no ayuda a
#: nadie a navegar. Con el hub, cualquier página de liga está a dos saltos de
#: cualquier otra.
#: El calendario entra aquí y no solo en la portada porque es la página que
#: cambia sola cada día: es la única a la que un rastreador tiene motivos para
#: volver, y estar en el pie de las 26 la pone a un clic de cualquier parte.
NAV: tuple[tuple[str, str], ...] = (
    ("index.html", "Home"),
    ("ligas.html", "Leagues"),
    ("upcoming-lol-matches.html", "Upcoming matches"),
    ("avisos.html", "How alerts look"),
    ("alternativas-bots-lol-discord.html", "Comparison"),
    ("legal.html", "Terms & privacy"),
)


def pie(pub: str) -> str:
    """Pie común: navegación, descargo obligatorio y aviso de anuncios.

    El descargo va en el pie de **todas** las páginas porque la política de Riot
    pide un sitio "readily visible", y el pie es lo único que aparece en todas.
    """
    web, web_attr = url(branding.WEB_URL)
    soporte, sop_attr = url(branding.SOPORTE_URL)
    nav = [f'      <a href="{ruta}">{e(texto)}</a>' for ruta, texto in NAV]
    if branding.SOPORTE_URL:
        nav.append(f'      <a href="{soporte}"{sop_attr}>Soporte</a>')
    if branding.WEB_URL:
        nav.append(f'      <a href="{web}"{web_attr}>{e(branding.WEB_URL)}</a>')
    aviso_ads = (
        "<br><br>Esta web muestra anuncios de Google AdSense." if pub else ""
    )
    return (
        "  <footer>\n"
        '    <div class="envoltura">\n'
        "      <nav>\n" + "\n".join(nav) + "\n      </nav>\n"
        f'      <p class="legal">{descargo_html()}{aviso_ads}</p>\n'
        "    </div>\n"
        "  </footer>\n"
        "</body>\n"
        "</html>\n"
    )


def migas_html(camino: list[tuple[str, str]]) -> str:
    """Las migas visibles, que acompañan al `BreadcrumbList` del JSON-LD.

    Se pintan de verdad y no solo en el schema: el marcado tiene que coincidir
    con lo que se ve, y además es la forma de que quien llega desde Google a la
    página de una liga sepa que existe un sitio alrededor.

    El último elemento no lleva enlace porque es la página actual; enlazarse a
    sí misma es un enlace que no lleva a ninguna parte.
    """
    partes = []
    for i, (nombre, ruta) in enumerate(camino):
        if i == len(camino) - 1:
            partes.append(f'<span aria-current="page">{e(nombre)}</span>')
        else:
            partes.append(f'<a href="{e(ruta)}">{e(nombre)}</a>')
    return (
        '  <nav class="migas" aria-label="Ruta">\n'
        '    <div class="envoltura">' + " › ".join(partes) + "</div>\n"
        "  </nav>\n"
    )


def cta(texto: str = "Añadir a Discord", *, nota: str = "") -> str:
    """La llamada a la acción, repetida al final de cada página de contenido.

    Es el único motivo por el que existe la web: alguien busca "elo de los mid de
    la LEC", encuentra la tabla, y abajo hay un botón que le dice que esto le
    puede llegar solo a su Discord. Una página de datos sin ese cierre es una
    página que informa y no convierte.
    """
    invite, invite_attr = url(branding.INVITE_URL)
    linea = f'      <p class="nota">{nota}</p>\n' if nota else ""
    return (
        '  <section class="cierre">\n'
        '    <div class="envoltura">\n'
        "      <h2>¿Y si esto te llegara solo?</h2>\n"
        f'      <p class="intro">{e(branding.BOT_NOMBRE)} publica este aviso en tu '
        "canal de Discord —o en tu chat privado— en cuanto el jugador entra en "
        f"partida, con las {len(LIGAS)} ligas del catálogo. Gratis.</p>\n"
        '      <div class="botones">\n'
        f'        <a class="boton primario" href="{invite}"{invite_attr}>{e(texto)}</a>\n'
        '        <a class="boton" href="avisos.html">Ver cómo es el aviso</a>\n'
        "      </div>\n"
        f"{linea}"
        "    </div>\n"
        "  </section>\n"
    )


def montar(pagina: Pagina, pub: str, sitio: str) -> str:
    """`Pagina` -> el HTML completo del fichero.

    Todas las páginas se montan por aquí, y eso es lo que convierte dos reglas
    obligatorias en propiedades estructurales en vez de disciplina:

    * **El descargo de Riot sale en todas.** Está en `pie()`, y no hay forma de
      escribir una página que no pase por aquí, así que no se puede olvidar en la
      página nueva de la semana que viene. La política de Riot pide que sea
      "readily visible" y el incumplimiento se paga con el acceso a la API.
    * **El `<head>` de SEO sale en todas.** Título, descripción y canónico van en
      `cabeza()`; una página sin canónico es el primer punto de la lista técnica
      que se incumpliría.
    """
    return cabeza(pagina, pub, sitio) + "<body>\n" + pagina.cuerpo + pie(pub)

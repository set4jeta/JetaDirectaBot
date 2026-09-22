"""Comprueba que la web generada dice lo que el bot hace y cumple la lista de SEO.

Por qué existe
--------------
La web se genera desde `LIGAS`, `PLANES`, `branding` y los ficheros de datos
justamente para que no pueda quedarse obsoleta, pero eso solo se cumple si
alguien lo comprueba: un `ligas_html()` que se olvide de una liga tiene
exactamente el mismo efecto que la landing escrita a mano que se quería evitar.
Aquí el HTML se compara **contra los datos del bot**, no contra una copia
esperada.

Y hay una segunda familia de comprobaciones que no se pueden hacer mirando una
página: **los títulos duplicados, el sitemap desincronizado y el `<h1>` de más
solo se ven comparando las 26 páginas entre sí.** Eso es lo que se prueba aquí y
lo que hace que la lista técnica de SEO sea una propiedad verificada en vez de
una intención.

Lo que se prueba y por qué es lo que importa
--------------------------------------------
* Que **todas** las ligas del catálogo salen en la web, con su código y con su
  página propia. Si el catálogo vuelve a crecer (pasó de 12 a 20), la web crece
  con él o esto falla.
* Que los cupos son los del plan, incluido el `historial` que se bajó de 500 a
  50: la web era el último sitio donde podía sobrevivir la cifra vieja.
* Que sin `--adsense` **no hay ningún script de terceros** y la política de
  privacidad no menciona cookies publicitarias; y que con ID aparecen las dos
  cosas a la vez.
* Que el descargo de Riot está en **las 26 páginas**, no solo en dos.
* Que cada página tiene título y descripción **únicos**, un solo `<h1>` y
  canónico absoluto autorreferente en el HTML crudo.
* Que el `sitemap.xml` contiene exactamente las páginas indexables escritas, y
  que el 404 no está.
* Que cada `<img>` lleva `width`, `height` y `loading`, que es lo que evita el
  CLS.
* Que el JSON-LD es JSON válido, no puede cerrar su `<script>`, y que cada
  pregunta del `FAQPage` está **visible** en la página.
* Que todos los enlaces internos apuntan a una página que existe.

No se escribe nada en `web/`: se genera todo en memoria.
"""

from __future__ import annotations

import contextlib
import html as _html
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import generar_web as gw  # noqa: E402
from scripts import web_datos as datos  # noqa: E402
from scripts import web_layout as maq  # noqa: E402
from scripts import web_paginas as pags  # noqa: E402
from scripts import web_seo as seo  # noqa: E402
from tracking.soloq.leagues import LIGAS, MAX_LIGAS_POR_SERVIDOR  # noqa: E402
from tracking.soloq.plans import ORDEN, PLANES  # noqa: E402
from utils import branding  # noqa: E402

#: Dominio y fecha fijos. Los canónicos y `dateModified` tienen que ser
#: comparables entre ejecuciones para que un fallo sea un fallo y no la fecha de
#: hoy.
SITIO = "https://ejemplo.test/"
FECHA = "2026-01-15"
PUB = "ca-pub-1234567890123456"

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    if condicion:
        print(f"  OK    {etiqueta}{f' ({extra})' if extra else ''}")
    else:
        print(f"  FALLA {etiqueta}{f' ({extra})' if extra else ''}")
        fallos.append(etiqueta)


def paginas(pub: str = "") -> list:
    """Las páginas como objetos `Pagina`."""
    return gw.construir(SITIO, FECHA, pub)


def sitio(pub: str = "") -> dict[str, str]:
    """`{ruta: html completo}` de todo el sitio, como se escribiría en disco."""
    return {p.ruta: maq.montar(p, pub, SITIO) for p in paginas(pub)}


def inicio(pub: str = "") -> str:
    return maq.montar(gw.pagina_inicio(pub, SITIO, FECHA), pub, SITIO)


def legal(pub: str = "", fecha: str = FECHA) -> str:
    return maq.montar(gw.pagina_legal(pub, fecha), pub, SITIO)


# ---------------------------------------------------------------------- #
# Histórico de avisos: las dos ramas
# ---------------------------------------------------------------------- #
#
# `avisos.html` tiene dos formas según el bot haya publicado avisos o no, y las
# dos hay que probarlas **siempre**. Depender del `avisos.jsonl` real haría lo
# contrario: hoy no existe (bot sin desplegar desde que se añadió el registro) y
# la rama con datos no se probaría nunca; el día que exista, la rama vacía dejaría
# de probarse y además el HTML cambiaría entre ejecuciones, que es justo lo que
# `FECHA` y `SITIO` fijos evitan.
#
# Así que el histórico se inyecta. Los jugadores son reales para que la foto
# exista y la comprobación de medidas del `<img>` sirva de algo.

#: Marca de tiempo del aviso más nuevo de las pruebas: 2025-12-31 16:51 UTC.
#: Anterior a `FECHA` (2026-01-15) a propósito, para que se note si la página
#: estampa la fecha de generación donde tendría que ir la del último aviso.
_MOMENTO = 1767200000


def _avisos_falsos(cuantos: int = 3) -> list:
    """Un histórico con forma real: jugadores de la LEC y horas descendentes."""
    reales = datos.jugadores_de("lec")[:cuantos]
    salida = []
    for i, j in enumerate(reales):
        salida.append(datos.Aviso(
            momento=_MOMENTO - i * 3600,
            jugador=j.nombre,
            equipo=j.equipo,
            liga="lec",
            campeon=j.campeones[0].nombre if j.campeones else "",
            rango=j.rango_texto,
            cuenta=j.riot_id,
            partida=str(7000000000 + i),
        ))
    return salida


@contextlib.contextmanager
def con_avisos(lista: list):
    """Genera el sitio como si `avisos.jsonl` tuviera esas entradas."""
    original = datos.avisos
    datos.avisos = lambda tope=20: list(lista)[:tope]
    try:
        yield
    finally:
        datos.avisos = original


# ---------------------------------------------------------------------- #
# HTML bien formado
# ---------------------------------------------------------------------- #

class _Cierres(HTMLParser):
    """Comprueba que cada etiqueta se cierra, y en orden.

    Se usa el parser de la librería estándar en vez de una expresión regular
    porque lo que hace falta detectar es un `</div>` de más o de menos, y eso una
    regex no lo ve. Los elementos vacíos de HTML5 no llevan cierre.
    """

    VACIOS = {"meta", "link", "br", "img", "hr", "input"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pila: list[str] = []
        self.errores: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VACIOS:
            self.pila.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VACIOS:
            return
        if not self.pila:
            self.errores.append(f"</{tag}> sin abrir")
        elif self.pila[-1] != tag:
            self.errores.append(f"</{tag}> cierra <{self.pila[-1]}>")
            if tag in self.pila:
                while self.pila and self.pila.pop() != tag:
                    pass
        else:
            self.pila.pop()

    def resto(self) -> list[str]:
        return self.errores + [f"<{t}> sin cerrar" for t in self.pila]


class _Inventario(HTMLParser):
    """Recoge lo que hace falta para las comprobaciones de SEO.

    Se recorre el HTML una vez y se queda con encabezados, imágenes, enlaces y
    el texto visible. Con regex sobre el HTML se puede contar `<h1`, pero no
    saber si un `<img>` lleva `width` **ni** si una pregunta del `FAQPage` está
    de verdad en el texto que el usuario lee, que es lo que la regla del schema
    exige.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.h1: list[str] = []
        self.encabezados: list[tuple[int, str]] = []
        self.imgs: list[dict[str, str]] = []
        self.enlaces: list[str] = []
        self.texto: list[str] = []
        self.scripts_ld: list[str] = []
        self._nivel: int | None = None
        self._en_ld = False

    def handle_starttag(self, tag, attrs):
        d = {k: (v or "") for k, v in attrs}
        if tag in ("h1", "h2", "h3", "h4"):
            self._nivel = int(tag[1])
        elif tag == "img":
            self.imgs.append(d)
        elif tag == "a" and d.get("href"):
            self.enlaces.append(d["href"])
        elif tag == "script" and d.get("type") == "application/ld+json":
            self._en_ld = True
            self.scripts_ld.append("")

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4"):
            self._nivel = None
        elif tag == "script":
            self._en_ld = False

    def handle_data(self, data):
        if self._en_ld:
            self.scripts_ld[-1] += data
            return
        self.texto.append(data)
        limpio = " ".join(data.split())
        if self._nivel and limpio:
            self.encabezados.append((self._nivel, limpio))
            if self._nivel == 1:
                self.h1.append(limpio)

    @property
    def visible(self) -> str:
        return " ".join(" ".join(self.texto).split())


def inventario(html: str) -> _Inventario:
    inv = _Inventario()
    inv.feed(html)
    return inv


def prueba_html_bien_formado() -> None:
    print("\n=== HTML bien formado ===")
    todo = sitio()
    malas = []
    for ruta, html in todo.items():
        parser = _Cierres()
        parser.feed(html)
        problemas = parser.resto()
        if problemas:
            malas.append(f"{ruta}: {problemas[0]}")
    ok(not malas, f"las {len(todo)} páginas cierran todas sus etiquetas",
       "; ".join(malas[:3]) if malas else f"{len(todo)} páginas")

    con_ads = sitio(PUB)
    malas = []
    for ruta, html in con_ads.items():
        parser = _Cierres()
        parser.feed(html)
        if parser.resto():
            malas.append(ruta)
    ok(not malas, "y también con AdSense activado", ", ".join(malas[:3]))

    sin_doctype = [r for r, h in todo.items() if not h.startswith("<!DOCTYPE html>")]
    ok(not sin_doctype, "todas empiezan por el doctype", str(sin_doctype[:3]))

    sin_lang = [r for r, h in todo.items() if 'lang="es"' not in h]
    ok(not sin_lang, "todas declaran el idioma", str(sin_lang[:3]))

    sin_viewport = [r for r, h in todo.items() if 'name="viewport"' not in h]
    ok(not sin_viewport, "todas llevan viewport: la mitad del tráfico es móvil",
       str(sin_viewport[:3]))

    huecos = [r for r, h in todo.items() if re.search(r"\{[a-z_]+\}", h)]
    ok(not huecos, "no queda ningún hueco de plantilla sin rellenar", str(huecos[:3]))


# ---------------------------------------------------------------------- #
# La lista técnica de SEO
# ---------------------------------------------------------------------- #

def prueba_titulos_unicos() -> None:
    """Títulos y descripciones únicos: el punto que solo se ve comparando todas.

    Es el fallo natural de la generación programática: una plantilla con 20
    variables y un título que no use la variable produce 20 páginas idénticas
    para Google, que indexa una y descarta las otras 19.
    """
    print("\n=== títulos y descripciones únicos ===")
    todas = paginas()
    ok(not gw._duplicados(todas),
       f"las {len(todas)} páginas tienen título y descripción únicos",
       "; ".join(gw._duplicados(todas)[:2]))

    cortos = [p.ruta for p in todas if len(p.titulo) < 15]
    ok(not cortos, "ningún título es un placeholder corto", str(cortos[:3]))

    # El largo del título y de la descripción se comprueba con la función que usa
    # el generador, no con números repetidos aquí: si la ventana cambia, cambia
    # en un sitio. Una prueba con su propia copia del límite es una prueba que
    # puede pasar mientras la generación falla.
    fuera = gw._snippets(todas)
    ok(not fuera,
       f"todos los títulos y descripciones caben en el snippet "
       f"({gw.DESC_MIN}-{gw.DESC_MAX})",
       "; ".join(fuera[:3]))

    # El título tiene que llevar el término por el que se busca. En una página
    # de liga eso es el nombre de la liga: sin él, la página programática no
    # responde a la búsqueda que justifica su existencia.
    sin_nombre = [
        p.ruta for p in todas
        if p.ruta.startswith("liga-")
        and LIGAS[p.ruta[5:-5]].nombre not in p.titulo
    ]
    ok(not sin_nombre, "cada página de liga lleva el nombre de su liga en el título",
       str(sin_nombre[:3]))


def prueba_canonicos() -> None:
    print("\n=== canónico absoluto y autorreferente ===")
    todo = sitio()
    malos = []
    for ruta, html in todo.items():
        encaje = re.search(r'<link rel="canonical" href="([^"]+)">', html)
        if not encaje:
            malos.append(f"{ruta}: sin canónico")
            continue
        esperado = seo.absoluta(SITIO, ruta)
        if encaje.group(1) != esperado:
            malos.append(f"{ruta}: {encaje.group(1)} != {esperado}")
    ok(not malos, "todas las páginas tienen canónico absoluto y a sí mismas",
       "; ".join(malos[:3]))

    ok(f'href="{SITIO}"' in todo["index.html"],
       "la portada canoniza a la carpeta, no a index.html")

    # Canónico y og:url tienen que coincidir; si no, se le está diciendo a
    # Google una cosa y a Discord otra.
    discrepan = []
    for ruta, html in todo.items():
        can = re.search(r'<link rel="canonical" href="([^"]+)">', html)
        og = re.search(r'<meta property="og:url" content="([^"]+)">', html)
        if not can or not og or can.group(1) != og.group(1):
            discrepan.append(ruta)
    ok(not discrepan, "canónico y og:url dicen la misma URL", str(discrepan[:3]))


def prueba_un_solo_h1() -> None:
    print("\n=== un <h1> y jerarquía coherente ===")
    todo = sitio()
    malas = []
    saltos = []
    for ruta, html in todo.items():
        inv = inventario(html)
        if len(inv.h1) != 1:
            malas.append(f"{ruta}: {len(inv.h1)} h1")
        anterior = 1
        for nivel, texto in inv.encabezados:
            if nivel > anterior + 1:
                saltos.append(f"{ruta}: h{anterior} -> h{nivel} ({texto[:30]})")
            anterior = nivel
    ok(not malas, f"las {len(todo)} páginas tienen exactamente un <h1>",
       "; ".join(malas[:3]))
    ok(not saltos, "no se salta ningún nivel de encabezado", "; ".join(saltos[:3]))


def prueba_open_graph() -> None:
    print("\n=== Open Graph y Twitter Card ===")
    todo = sitio()
    obligatorias = (
        'property="og:title"', 'property="og:description"', 'property="og:type"',
        'property="og:url"', 'property="og:image"', 'property="og:image:width"',
        'property="og:image:height"', 'property="og:locale"',
        'name="twitter:card" content="summary_large_image"',
        'name="twitter:title"', 'name="twitter:image"',
    )
    for etiqueta in obligatorias:
        faltan = [r for r, h in todo.items() if etiqueta not in h]
        ok(not faltan, f"{etiqueta.split('=')[1][:28]} en todas", str(faltan[:2]))

    absolutas = [
        r for r, h in todo.items()
        if f'content="{SITIO}og.png"' not in h
    ]
    ok(not absolutas, "og:image es una URL absoluta (si no, X no la carga)",
       str(absolutas[:3]))


def prueba_sitemap_y_robots() -> None:
    print("\n=== sitemap.xml y robots.txt ===")
    todas = paginas()
    xml = seo.sitemap(SITIO, todas, FECHA)

    raiz = ET.fromstring(xml)
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [n.text for n in raiz.iter(f"{ns}loc")]
    ok(bool(locs), "el sitemap es XML válido y tiene URL", f"{len(locs)} URL")

    esperadas = {seo.absoluta(SITIO, p.ruta) for p in todas if p.indexable}
    ok(set(locs) == esperadas,
       "el sitemap contiene exactamente las páginas indexables escritas",
       f"sitemap {len(locs)} / escritas {len(esperadas)}")

    ok(len(locs) == len(set(locs)), "sin URL repetidas en el sitemap")

    ok(seo.absoluta(SITIO, "404.html") not in locs,
       "el 404 no está en el sitemap")
    ok(all(loc.startswith("https://") for loc in locs),
       "todas las URL del sitemap son absolutas y https")

    txt = seo.robots(SITIO)
    ok(f"Sitemap: {SITIO}sitemap.xml" in txt,
       "robots.txt apunta al sitemap con URL absoluta")
    ok(".css" not in txt and ".js" not in txt,
       "robots.txt no bloquea CSS ni JS (Google renderiza la página para juzgarla)")
    ok("Disallow: /" not in txt, "robots.txt no bloquea el sitio")


def prueba_404() -> None:
    print("\n=== 404 real ===")
    todas = paginas()
    p404 = next(p for p in todas if p.ruta == "404.html")
    html = maq.montar(p404, "", SITIO)

    ok(not p404.indexable, "el 404 está marcado como no indexable")
    ok('<meta name="robots" content="noindex, follow">' in html,
       "y eso pone noindex en el HTML, con follow para que encuentre la salida")

    indexables = [p for p in todas if p.indexable]
    ok(all('name="robots"' not in maq.montar(p, "", SITIO) for p in indexables),
       "y ninguna otra página lleva meta robots")

    inv = inventario(html)
    internos = {e for e in inv.enlaces if not e.startswith(("http", "#", "mailto"))}
    ok(len(internos) >= 5, "el 404 tiene salida a las páginas que sí existen",
       f"{len(internos)} enlaces")


def prueba_imagenes() -> None:
    """`width`, `height`, `loading` y `alt` en cada imagen.

    Los tres primeros son CLS y carga; el `alt` es accesibilidad y además es lo
    único que un rastreador lee de una imagen.
    """
    print("\n=== imágenes: CLS y accesibilidad ===")
    todo = sitio()
    total = 0
    sin_medida, sin_lazy, sin_alt = [], [], []
    for ruta, html in todo.items():
        for img in inventario(html).imgs:
            total += 1
            if not img.get("width") or not img.get("height"):
                sin_medida.append(f"{ruta}:{img.get('src', '?')}")
            if img.get("loading") != "lazy":
                sin_lazy.append(f"{ruta}:{img.get('src', '?')}")
            if not img.get("alt"):
                sin_alt.append(f"{ruta}:{img.get('src', '?')}")
    ok(total > 0, "hay imágenes que comprobar", f"{total} <img>")
    ok(not sin_medida, "todas llevan width y height explícitos (CLS)",
       "; ".join(sin_medida[:3]))
    ok(not sin_lazy, 'todas llevan loading="lazy"', "; ".join(sin_lazy[:3]))
    ok(not sin_alt, "todas llevan alt", "; ".join(sin_alt[:3]))

    # Las medidas tienen que ser las del fichero, no un número inventado: si se
    # declara 48x48 sobre una imagen de 500x200, se reserva mal el hueco y el
    # CLS vuelve.
    inv = inventario(todo["liga-lec.html"])
    origen = datos.imagen_de_equipo("FNC")
    if origen and inv.imgs:
        proporciones_mal = []
        for img in inv.imgs:
            ancho, alto = int(img["width"]), int(img["height"])
            if ancho <= 0 or alto <= 0:
                proporciones_mal.append(img.get("src", "?"))
        ok(not proporciones_mal, "ninguna medida es cero o negativa",
           str(proporciones_mal[:3]))
        medida = datos.medir_imagen(origen.origen)
        ok(medida == (origen.ancho, origen.alto),
           "las medidas salen de leer la cabecera del fichero",
           f"FNC {origen.ancho}x{origen.alto}")


def prueba_jsonld() -> None:
    """El JSON-LD: válido, no puede cerrar su `<script>`, y coincide con lo visible."""
    print("\n=== datos estructurados ===")
    todo = sitio()
    bloques = 0
    malos, escapes = [], []
    for ruta, html in todo.items():
        for crudo in inventario(html).scripts_ld:
            bloques += 1
            try:
                json.loads(crudo)
            except json.JSONDecodeError as exc:
                malos.append(f"{ruta}: {exc}")
            if "</script" in crudo or "<" in crudo:
                escapes.append(ruta)
    ok(bloques > 0, "hay bloques JSON-LD", f"{bloques} bloques")
    ok(not malos, "todos son JSON válido", "; ".join(malos[:2]))
    ok(not escapes,
       "ninguno lleva '<' literal: no puede cerrar su etiqueta desde un dato remoto",
       str(escapes[:3]))

    # Cada pregunta del FAQPage tiene que estar visible en la página. Es la
    # regla que el usuario puso explícita: nunca schema que no coincida con el
    # contenido visible.
    desajustes = []
    con_faq = 0
    for ruta, html in todo.items():
        inv = inventario(html)
        visible = inv.visible
        for crudo in inv.scripts_ld:
            try:
                d = json.loads(crudo)
            except json.JSONDecodeError:
                continue
            if d.get("@type") != "FAQPage":
                continue
            con_faq += 1
            for entrada in d.get("mainEntity", []):
                pregunta = " ".join(str(entrada.get("name", "")).split())
                if pregunta and pregunta not in visible:
                    desajustes.append(f"{ruta}: {pregunta[:40]}")
    ok(con_faq >= 24, "casi todas las páginas llevan FAQPage", f"{con_faq} páginas")
    ok(not desajustes,
       "cada pregunta del FAQPage está visible en el HTML de su página",
       "; ".join(desajustes[:3]))

    # Y ninguna respuesta puede estar vacía: una pregunta sin respuesta es
    # exactamente el marcado que Google trata como manipulación.
    vacias = []
    for ruta, html in todo.items():
        for crudo in inventario(html).scripts_ld:
            try:
                d = json.loads(crudo)
            except json.JSONDecodeError:
                continue
            for entrada in d.get("mainEntity", []) if d.get("@type") == "FAQPage" else []:
                texto = (entrada.get("acceptedAnswer") or {}).get("text", "")
                if len(str(texto).strip()) < 20:
                    vacias.append(f"{ruta}: {entrada.get('name', '')[:30]}")
    ok(not vacias, "ninguna respuesta del FAQPage está vacía", "; ".join(vacias[:3]))

    # Sin invenciones: ni reseñas ni valoraciones, que es el marcado penalizado
    # cuando es falso, y no hay ninguna reseña que contar.
    inventado = [
        r for r, h in todo.items()
        if "aggregateRating" in h or '"review"' in h
    ]
    ok(not inventado, "no hay aggregateRating ni review inventados", str(inventado[:3]))

    # El Offer de la portada declara 0 € y solo eso: no hay pasarela, así que
    # marcar 3,99 € sería un precio que nadie puede pagar.
    home = todo["index.html"]
    ok('"SoftwareApplication"' in home, "la portada declara SoftwareApplication")
    ok('"price": "0"' in home and "3.99" not in home.split("</head>")[0],
       "y su Offer es 0 €, porque todavía no hay pasarela de pago")
    ok('"Organization"' in home and '"WebSite"' in home,
       "la portada lleva Organization y WebSite")
    otras = [r for r, h in todo.items() if r != "index.html" and '"WebSite"' in h]
    ok(not otras, "y no se repiten en las demás páginas", str(otras[:3]))

    lec = todo["liga-lec.html"]
    ok('"ItemList"' in lec, "la página con ranking visible declara ItemList")
    # El `ItemList` describe la tabla pintada, y hay dos que valen: la del
    # barrido (con Riot ID) y la del leaderboard (con Elo y victorias). Lo que no
    # puede haber es un `ItemList` en una página sin ninguna de las dos tablas,
    # porque entonces declararía una lista que no está en el HTML.
    sin_ranking = [
        r for r, h in todo.items()
        if r.startswith("liga-") and '"ItemList"' in h
        and not datos.jugadores_de(r[5:-5])
        and not datos.clasificacion_de(r[5:-5])
    ]
    ok(not sin_ranking, "y solo las que tienen ranking de verdad", str(sin_ranking[:3]))

    # Y al revés: donde hay tabla, tiene que haber `ItemList`. Sin esta segunda
    # mitad, la prueba pasaría igual si el schema dejara de emitirse.
    falta = [
        r for r, h in todo.items()
        if r.startswith("liga-") and '"ItemList"' not in h
        and (datos.jugadores_de(r[5:-5]) or datos.clasificacion_de(r[5:-5]))
    ]
    ok(not falta, "y todas las que tienen tabla lo declaran", str(falta[:3]))

    ok('"dateModified": "' + FECHA + '"' in lec,
       "el Article lleva dateModified con la fecha de generación (recencia)")


def prueba_enlaces_internos() -> None:
    """Ningún enlace interno puede apuntar a una página que no se escribe."""
    print("\n=== enlaces internos ===")
    todo = sitio()
    rutas = set(todo) | {"styles.css", "og.png", "favicon.svg"}
    rotos = []
    for ruta, html in todo.items():
        for href in inventario(html).enlaces:
            if href.startswith(("http://", "https://", "#", "mailto:")):
                continue
            destino = href.split("#")[0]
            if destino and destino not in rutas:
                rotos.append(f"{ruta} -> {href}")
    ok(not rotos, "ningún enlace interno apunta a una página que no existe",
       "; ".join(rotos[:3]))

    # Toda página **indexable** tiene que ser alcanzable siguiendo enlaces desde
    # la portada. Un sitemap es una lista de direcciones, no un enlace: si una
    # liga solo está en el sitemap, no recibe nada.
    #
    # El 404 queda fuera de la regla a propósito y no por descuido: nadie debe
    # enlazarlo, lo sirve el hosting cuando la ruta no existe. Enlazarlo desde el
    # menú para que "pase la prueba" sería invitar a Google a rastrear un error.
    # Por eso la exención se comprueba: solo puede librarse una página no
    # indexable.
    alcanzables = {"index.html"}
    frontera = ["index.html"]
    while frontera:
        actual = frontera.pop()
        for href in inventario(todo[actual]).enlaces:
            destino = href.split("#")[0]
            if destino in todo and destino not in alcanzables:
                alcanzables.add(destino)
                frontera.append(destino)
    sin_enlazar = {p.ruta for p in paginas() if not p.indexable}
    inalcanzables = sorted(set(todo) - alcanzables - sin_enlazar)
    ok(not inalcanzables,
       f"las {len(alcanzables)} páginas indexables se alcanzan navegando desde "
       "la portada",
       str(inalcanzables[:3]))
    ok(sin_enlazar == {"404.html"},
       "y la única página que nadie enlaza es el 404, que sirve el hosting",
       str(sorted(sin_enlazar)))

    # Y el camino tiene que ser corto. Con el hub, dos saltos.
    profundidad = {"index.html": 0}
    cola = ["index.html"]
    while cola:
        actual = cola.pop(0)
        for href in inventario(todo[actual]).enlaces:
            destino = href.split("#")[0]
            if destino in todo and destino not in profundidad:
                profundidad[destino] = profundidad[actual] + 1
                cola.append(destino)
    hondas = [f"{r}={d}" for r, d in profundidad.items() if d > 2]
    ok(not hondas, "ninguna página está a más de dos clics de la portada",
       ", ".join(hondas[:3]))

    ok(all(
        'rel="nofollow noopener"' in h or "dorans" not in h
        for h in todo.values()
    ), "los enlaces a la competencia van con nofollow")


# ---------------------------------------------------------------------- #
# El contenido contra los datos del bot
# ---------------------------------------------------------------------- #

def prueba_ligas() -> None:
    print("\n=== ligas en la web ===")
    pagina = inicio()

    faltan = [c for c in LIGAS if f"<b>{c}</b>" not in pagina]
    ok(not faltan, f"las {len(LIGAS)} ligas del catálogo salen en la portada",
       f"faltan {faltan}" if faltan else f"{len(LIGAS)} códigos")

    nombres = [l.nombre for l in LIGAS.values() if l.nombre not in pagina]
    ok(not nombres, "y con su nombre visible", f"faltan {nombres}" if nombres else "")

    ok(f"<h2>{len(LIGAS)} ligas</h2>" in pagina,
       "el titular cuenta las ligas que hay, no un número escrito a mano")

    ok(f"hasta {MAX_LIGAS_POR_SERVIDOR} a la vez" in pagina,
       "el tope por servidor sale de leagues.py", str(MAX_LIGAS_POR_SERVIDOR))

    # La LPL no permite partida en vivo: si algún día se marcara como seguible,
    # la web dejaría de decirlo y volveríamos a prometer algo que no existe.
    no_seguibles = [l for l in LIGAS.values() if not l.seguible]
    ok(bool(no_seguibles) == ("solo Elo" in pagina),
       "las ligas sin partida en vivo van marcadas",
       f"{[l.codigo for l in no_seguibles]}")

    # Una página por liga, ni una más ni una menos.
    todo = sitio()
    esperadas = {pags.ruta_de_liga(c) for c in LIGAS}
    ok(esperadas <= set(todo), f"se escribe una página por cada una de las {len(LIGAS)}",
       str(sorted(esperadas - set(todo))[:3]))

    hub = todo["ligas.html"]
    sin_enlace = [c for c in LIGAS if pags.ruta_de_liga(c) not in hub]
    ok(not sin_enlace, "y el hub enlaza a todas", str(sin_enlace[:3]))


def prueba_datos_de_liga() -> None:
    """Que las páginas de liga digan los números que hay, y solo los que hay."""
    print("\n=== datos reales en las páginas de liga ===")
    todo = sitio()

    lec = todo["liga-lec.html"]
    jugadores = datos.jugadores_de("lec")
    ok(bool(jugadores), "hay jugadores de la LEC descargados", f"{len(jugadores)}")

    primero = jugadores[0]
    ok(primero.nombre in lec, "el primero por Elo sale en la página", primero.nombre)
    ok(primero.riot_id in lec,
       "y con su Riot ID, que es el dato que no está en ningún otro sitio",
       primero.riot_id)
    ok(primero.rango_texto in lec, "y su rango en texto", primero.rango_texto)

    censo = datos.censo_de("lec")
    ok(str(censo.personas) in lec, "el censo medido sale en la página",
       f"{censo.personas} personas")

    # Y lo que no hay, no se pinta. La columna con el Riot ID solo puede salir
    # donde la liga está barrida jugador por jugador: el leaderboard identifica
    # por PUUID y `displayName`, así que en las otras 19 esa columna sería un
    # hueco con encabezado.
    vacias_con_tabla = []
    for codigo in LIGAS:
        html = todo[pags.ruta_de_liga(codigo)]
        tiene_datos = bool(datos.jugadores_de(codigo))
        tiene_tabla = "<th>Cuenta de SoloQ</th>" in html
        if tiene_tabla != tiene_datos:
            vacias_con_tabla.append(codigo)
    ok(not vacias_con_tabla,
       "solo hay tabla de jugadores donde hay jugadores descargados",
       str(vacias_con_tabla[:5]))

    # La otra mitad: donde hay ranking del leaderboard sale la tabla de Elo con
    # victorias y KDA, y **no** la del Riot ID. Las dos tablas no pueden
    # coexistir: serían el mismo ranking dos veces con números distintos, porque
    # el barrido mira todas las cuentas conocidas y el leaderboard solo las de la
    # lista de esa liga.
    mal_ranking = []
    for codigo in LIGAS:
        html = todo[pags.ruta_de_liga(codigo)]
        tiene_ranking = "<th>KDA</th>" in html
        toca = bool(datos.clasificacion_de(codigo)) and not datos.jugadores_de(codigo)
        if tiene_ranking != toca:
            mal_ranking.append(codigo)
    ok(not mal_ranking,
       "y tabla de ranking solo donde hay leaderboard y no hay barrido",
       str(mal_ranking[:5]))

    ambas = [c for c in LIGAS
             if "<th>KDA</th>" in todo[pags.ruta_de_liga(c)]
             and "<th>Cuenta de SoloQ</th>" in todo[pags.ruta_de_liga(c)]]
    ok(not ambas, "ninguna página pinta las dos tablas de Elo a la vez", str(ambas[:3]))

    # Una liga sin barrido tiene que llevar su ranking de verdad: nombre, equipo y
    # rango del primero. Se comprueba sobre la EBL, que es la más pequeña, así que
    # si el recorte por `TOPE_TABLA` se rompiera se vería aquí.
    ebl = todo["liga-ebl.html"]
    clasificados = datos.clasificacion_de("ebl")
    ok(bool(clasificados), "hay ranking de la EBL medido", f"{len(clasificados)}")
    lider = clasificados[0]
    ok(lider.nombre in ebl and lider.equipo in ebl,
       "el primero del ranking sale con su equipo", f"{lider.nombre} ({lider.equipo})")
    ok(lider.rango_texto in ebl, "y con su Elo en texto", lider.rango_texto)
    ok("#" not in lider.nombre and "Cuenta de SoloQ" not in ebl,
       "y sin prometer Riot ID, que esta vía no da")

    # Los ids de campeón se resuelven a nombre. Si el catálogo se quedara viejo,
    # esto es lo que lo detecta antes de publicar: un "ID 904" en una página
    # pública es basura, no un aviso útil como en un embed de Discord.
    ok(not re.search(r"\bID \d{2,3}\b", "".join(todo.values())),
       "ningún id de campeón se publica sin resolver a nombre")

    # Ninguna página puede publicar un contador a cero. Es la regla escrita en
    # `web_paginas`: si el dato no está, la sección no se pinta, porque una
    # página que dice "0 jugadores" es peor que no publicarla.
    #
    # El patrón lleva `\b` delante del cero, y eso es el arreglo de una prueba
    # que estaba mal: `"0 jugadores" in html` también encuentra la subcadena
    # dentro de "50 jugadores", así que la LEC —la única liga con datos
    # completos— era la que fallaba.
    cero = re.compile(r"\b0\s+(jugadores|equipos|cuentas|partidas|ligas)\b")
    ceros = sorted({
        f"{ruta}: {m.group(0)}"
        for ruta, html in todo.items()
        for m in cero.finditer(html)
    })
    ok(not ceros, "ninguna página publica un contador a cero", str(ceros[:3]))

    # La LPL no puede prometer avisos en vivo en su propia página.
    lpl = todo["liga-lpl.html"]
    ok("no expose" in lpl or "no expone" in lpl,
       "la página de la LPL explica por qué no hay partida en vivo")

    # Y el agregado de campeones, que es el dato propio, tiene que estar donde
    # se puede calcular.
    campeones = datos.campeones_de("lec", tope=pags.TOPE_CAMPEONES)
    ok(bool(campeones) and campeones[0].nombre in lec,
       "el agregado de campeones sale en la LEC",
       f"{campeones[0].nombre} {campeones[0].partidas}g" if campeones else "")
    con_campeones = [
        c for c in LIGAS
        if "<th>DPM medio</th>" in todo[pags.ruta_de_liga(c)]
        and not datos.campeones_de(c, tope=1)
    ]
    ok(not con_campeones, "y solo donde hay historial", str(con_campeones[:3]))

    # La tabla de presencia es la versión honesta para las ligas sin historial:
    # cuenta en cuántos rankings aparece un campeón, y no inventa partidas ni
    # winrate. Tiene que salir donde hay ranking y no hay historial, y en ningún
    # otro sitio.
    mal_presencia = []
    for codigo in LIGAS:
        html = todo[pags.ruta_de_liga(codigo)]
        tiene = "<th>Jugadores que lo llevan</th>" in html
        toca = bool(datos.campeones_del_ranking(codigo, tope=1)) and not datos.campeones_de(codigo, tope=1)
        if tiene != toca:
            mal_presencia.append(codigo)
    ok(not mal_presencia,
       "la tabla de presencia sale solo donde no hay historial de partidas",
       str(mal_presencia[:3]))

    # Y esa tabla no puede llevar un winrate ni un DPM: son los dos números que
    # `mostChamps` no da y que sí tiene el agregado de la LEC.
    presencia_con_dpm = [
        c for c in LIGAS
        if "<th>Jugadores que lo llevan</th>" in todo[pags.ruta_de_liga(c)]
        and "<th>DPM medio</th>" in todo[pags.ruta_de_liga(c)]
    ]
    ok(not presencia_con_dpm,
       "y no mezcla el DPM, que esa fuente no tiene", str(presencia_con_dpm[:3]))


def prueba_planes() -> None:
    print("\n=== planes en la web ===")
    pagina = inicio()

    for codigo in ORDEN:
        plan = PLANES[codigo]
        esperado = f"{plan.historial} partidas de historial"
        ok(esperado in pagina, f"el historial de {codigo} es el del plan", esperado)

    ok("1 liga a la vez" in pagina and "liga(s)" not in pagina,
       "singular y plural bien escritos, sin '(s)'")

    ok("3,99 € / mes" in pagina, "el precio va con coma decimal, no con punto")

    ok("500 partidas" not in pagina,
       "no queda rastro de la cifra de historial que no se podía entregar")

    ok("Siempre gratis" in pagina and "gratis y siempre lo será" in pagina,
       "el tier gratuito se ve, que es lo que exige la política de Riot")

    # El plan gratuito se busca por su propiedad, no por su código: así un
    # renombre no rompe la web con un KeyError.
    gratis = gw._plan_gratis()
    ok(gratis.precio == 0, "el plan gratuito se localiza por precio", gratis.codigo)


def prueba_adsense() -> None:
    print("\n=== AdSense: solo cuando hay ID ===")
    sin = sitio()
    legal_sin = sin["legal.html"]

    terceros = [
        r for r, h in sin.items()
        if "googlesyndication" in h or "adsbygoogle" in h
    ]
    ok(not terceros, "sin ID no se carga ningún script de terceros en ninguna página",
       str(terceros[:3]))

    sin_hueco = [r for r, h in sin.items() if 'class="anuncio"' not in h]
    ok(len(sin_hueco) <= 2,
       "el hueco existe igual, para que la página no salte al activarlo",
       f"sin hueco: {sin_hueco}")

    ok("cookies propias ni de terceros" in legal_sin,
       "y la política dice que no hay cookies")
    ok("AdSense" not in legal_sin.replace("Google AdSense.", ""),
       "sin anuncios, la política no menciona publicidad")

    pub = maq.normalizar_pub("pub-1234567890123456")
    ok(pub == PUB, "un ID copiado del panel de AdSense se corrige con el prefijo", pub)

    con = sitio(pub)
    ok(all(pub in h for h in con.values()),
       "con ID, el script va en todas las páginas")
    ok(con["index.html"].count(pub) >= 2, "y el bloque de anuncio también lleva el ID",
       f"{con['index.html'].count(pub)} veces")
    ok("Cookies y publicidad" in con["legal.html"]
       and "My Ad Center" in con["legal.html"],
       "la política declara las cookies publicitarias y cómo retirar el consentimiento")
    ok("anuncios de Google AdSense" in maq.pie(pub),
       "el pie avisa de que la web lleva publicidad")

    for malo in ("hola", "ca-pub-", "pub-abc", "ca-pub-12ab"):
        try:
            maq.normalizar_pub(malo)
            ok(False, f"un ID inválido se rechaza: {malo!r}")
        except SystemExit:
            ok(True, f"un ID inválido se rechaza: {malo!r}")


def prueba_legal() -> None:
    print("\n=== documento legal ===")
    doc = legal("", "2026-01-15")

    ok('id="terminos"' in doc and 'id="privacidad"' in doc,
       "existen las anclas que hay que pegar en el portal de Discord")
    ok("2026-01-15" in doc, "la fecha se puede fijar (para poder comparar salidas)")

    for aguja in ("/unsubscribe", "2 horas"):
        ok(aguja in doc, f"la política menciona {aguja}")

    ok("no guarda mensajes" in doc and "contenido de mensajes" in doc,
       "se declara el intent de contenido en vez de fingir que no existe")
    ok("30 días" in doc, "hay plazo de respuesta para ejercer derechos")


def prueba_descargo() -> None:
    print("\n=== descargo de Riot ===")
    todo = sitio()
    marca = "trademarks or registered trademarks of Riot Games, Inc."
    faltan = [r for r, h in todo.items() if marca not in h]
    ok(not faltan,
       f"el descargo obligatorio está en las {len(todo)} páginas, no en dos",
       str(faltan[:3]))
    ok(branding.BOT_NOMBRE in maq.descargo_html(),
       "lleva el nombre del producto, como pide la plantilla de Riot")
    ok("_" not in maq.descargo_html().replace("_blank", ""),
       "el subrayado de Markdown se convierte a <em> y no se ve en la web")


def prueba_comparativa() -> None:
    """La comparativa: verificable y con las filas donde perdemos escritas."""
    print("\n=== comparativa ===")
    html = sitio()["alternativas-bots-lol-discord.html"]

    for rival in pags.RIVALES:
        ok(rival["nombre"] in html, f"{rival['nombre']} sale en la tabla")
        ok(rival["fuente"] in html,
           f"y con la URL donde se comprobó su dato", rival["fuente"])

    ok(pags.CONSULTA_RIVALES in html,
       "la fecha de consulta está en la página: sin ella no se puede verificar",
       pags.CONSULTA_RIVALES)

    # La página tiene que mandar al lector a la competencia cuando el otro es la
    # respuesta correcta. Una comparativa que gana en todas las filas es la que
    # nadie cita dos veces.
    ok("Dorans hace eso mejor" in html or "Dorans-bot." in html,
       "dice cuándo el rival es la mejor opción")
    ok("no van a haberlos" in html or "no es lo que hace este bot" in html,
       "y reconoce lo que este bot no hace")


def prueba_avisos() -> None:
    """La página de avisos: el número de latencia sale de config, no de la mano."""
    print("\n=== página de avisos ===")
    html = sitio()["avisos.html"]
    intervalo = datos.ajuste("CHECK_GAMES_INTERVAL", 30)

    ok(intervalo == 30, "el intervalo se lee de config.py", f"{intervalo} s")
    ok(f"{intervalo} segundos" in html,
       "y la página dice ese número, no uno plausible")
    ok("servidor de espectadores" in html,
       "se explica el desfase del reloj de la partida en vez de dejarlo raro")
    ok("/health" in html, "y qué hacer cuando la API de Riot falla")

    jugadores = datos.jugadores_de("lec")
    if jugadores:
        ok(jugadores[0].nombre in html,
           "el ejemplo de aviso usa un jugador real de la base de datos",
           jugadores[0].nombre)


def prueba_historico_de_avisos() -> None:
    """Las dos ramas de `avisos.html`: con histórico registrado y sin él.

    Es la comprobación que convierte esta página en lo que se pidió —"una web que
    emita los mismos avisos que le llegarían al Discord"— sin que pueda mentir en
    ninguno de los dos estados:

    * Con registro: se pinta la tabla, cada fila lleva su `<time>` con la marca
      ISO, el `dateModified` es la fecha del **último aviso** y no la de hoy, y
      aparece el `ItemList` de la lista visible.
    * Sin registro: no se pinta tabla ni se declara `ItemList`, no queda ningún
      encabezado hablando de avisos que no existen, y la coletilla del ejemplo
      dice que todavía no hay ninguno.

    Y una que vale para las dos: la página **nunca** puede publicar el servidor,
    el canal o el usuario que recibió un aviso. `avisos_log.py` no lo guarda, y
    esto lo comprueba desde el otro extremo de la tubería.
    """
    print("\n=== histórico real de avisos ===")
    lista = _avisos_falsos()
    ok(len(lista) == 3, "hay avisos de prueba con forma real", str(len(lista)))

    with con_avisos(lista):
        con = sitio()["avisos.html"]
        pagina = next(p for p in paginas() if p.ruta == "avisos.html")
    vacio = sitio()["avisos.html"]

    # --- Con histórico ---
    ok('class="tabla avisos"' in con, "con registro se pinta la tabla de avisos")
    ok(all(a.jugador in con for a in lista),
       "y sale cada jugador de las entradas registradas")
    ok(con.count("<time datetime=") >= len(lista),
       "cada fila lleva su <time datetime> con la marca completa",
       f"{con.count('<time datetime=')} <time>")
    ok(f'datetime="{lista[0].sello}"' in con,
       "y la marca es la del registro, en ISO con zona", lista[0].sello)
    ok("Cuándo (UTC)" in con,
       "la columna de la hora dice la zona: el HTML es el mismo para todo el mundo")

    # El orden de la tabla es el del registro, del más reciente al más antiguo.
    posiciones = [con.index(a.jugador) for a in lista]
    ok(posiciones == sorted(posiciones),
       "las filas van del aviso más reciente al más antiguo")

    # `dateModified` con la fecha del último aviso, no la de generación: la
    # página no es más nueva porque se regenere el sitio.
    ok(f'"dateModified": "{lista[0].fecha}"' in con,
       "dateModified es la fecha del último aviso, no la de hoy", lista[0].fecha)
    ok(f'"dateModified": "{FECHA}"' not in con,
       "y no se estampa la fecha de generación en una página que no cambió")
    ok('"ItemList"' in con, "se declara ItemList de la lista que ya está visible")

    # El ItemList no puede declarar más elementos que filas visibles.
    for crudo in inventario(con).scripts_ld:
        try:
            d = json.loads(crudo)
        except json.JSONDecodeError:
            continue
        if d.get("@type") == "ItemList":
            ok(d.get("numberOfItems") == len(lista),
               "y con tantos elementos como filas hay", str(d.get("numberOfItems")))
            break

    # --- Sin histórico ---
    ok('class="tabla avisos"' not in vacio,
       "sin registro no se pinta ninguna tabla vacía")
    ok("¿Qué avisos ha mandado el bot últimamente?" not in vacio,
       "ni queda un encabezado prometiendo avisos que no hay")
    ok('"ItemList"' not in vacio,
       "ni se declara un ItemList sin lista que describir")
    ok("todavía no hay avisos registrados" in vacio,
       "y el ejemplo dice que es el formato, no una partida real")
    ok(f'"dateModified": "{FECHA}"' in vacio,
       "sin registro, dateModified vuelve a la fecha de generación")

    # --- Privacidad, en las dos ramas ---
    # `avisos_log.py` no guarda canal, servidor ni usuario. Esto lo comprueba en
    # la salida publicada, que es donde importaría el fallo.
    filtrado = [
        p for p in ("channel_id", "guild_id", "user_id", "destinatarios")
        if p in con or p in vacio
    ]
    ok(not filtrado, "la página no publica canal, servidor ni usuario de nadie",
       str(filtrado))

    # Y el snippet sigue cabiendo: la descripción no depende del histórico, pero
    # si algún día lo hiciera, esto lo cazaría antes de publicar.
    ok(not gw._snippets([pagina]), "el snippet de la página sigue en rango",
       "; ".join(gw._snippets([pagina])[:2]))


def prueba_registro_de_avisos() -> None:
    """El escritor del histórico: `tracking/soloq/avisos_log.py`.

    No se importa el módulo del bot —arrastra `utils.logger` y el intérprete de
    los scripts no tiene sus dependencias, el mismo motivo por el que
    `web_datos.ajuste()` no importa `config`—, así que lo que se prueba es el
    contrato entre los dos: **el formato que escribe uno es el que lee el otro**.

    Se escribe un JSONL a mano con los casos que la vida real produce (una línea
    a medias por un SIGTERM, una línea en blanco, una entrada sin jugador) y se
    comprueba que `web_datos.avisos()` los descarta en vez de romper la
    generación entera.
    """
    print("\n=== registro de avisos (JSONL) ===")

    # Las claves que escribe `registrar()`, copiadas del módulo del bot. Si
    # alguna cambia de nombre allí, esto sigue pasando pero la web deja de
    # pintar ese campo: por eso se comprueba también contra el fichero.
    #
    # Se busca `"clave":` con comillas, que es como aparece una clave del JSON,
    # y no el nombre suelto: la cabecera del módulo **habla** de `channel_id`
    # para explicar que no lo guarda, así que buscar el nombre a secas daría
    # positivo justo por documentar la decisión correcta.
    ruta_log = os.path.join(gw.RAIZ, "tracking", "soloq", "avisos_log.py")
    with open(ruta_log, encoding="utf-8") as fh:
        fuente = fh.read()
    for clave in ("ts", "jugador", "equipo", "liga", "cuenta", "campeon", "rango"):
        ok(f'"{clave}":' in fuente,
           f"el registro escribe la clave {clave} que la web lee")
    for prohibida in ("channel_id", "guild_id", "user_id", "destinatarios"):
        ok(f'"{prohibida}"' not in fuente,
           f"y no escribe {prohibida}: este fichero acaba publicado")

    # Las líneas van **a propósito** en orden no cronológico: Caps es el aviso
    # más nuevo y está en la primera línea, al revés de como lo escribiría el
    # bot. Así se comprueba que el orden de salida lo decide la marca de tiempo
    # y no la posición en el fichero, que es lo que la página promete.
    lineas = [
        json.dumps({"ts": _MOMENTO, "jugador": "Caps", "equipo": "kc",
                    "liga": "lec", "campeon": "Syndra", "rango": "Master (120 LP)",
                    "cuenta": "Caps#EUW", "partida": "7000"}, ensure_ascii=False),
        "",                                    # línea en blanco
        '{"ts": 176720000, "jugador": "Cor',   # línea a medias por un SIGTERM
        json.dumps({"ts": _MOMENTO - 60, "jugador": ""}),   # sin jugador
        json.dumps({"jugador": "SinFecha"}),                # sin ts
        json.dumps({"ts": _MOMENTO - 120, "jugador": "Hans Sama", "equipo": "kc",
                    "liga": "lec"}, ensure_ascii=False),
    ]
    original = datos._AVISOS
    with tempfile.TemporaryDirectory() as tmp:
        fichero = os.path.join(tmp, "avisos.jsonl")
        with open(fichero, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lineas) + "\n")
        datos._AVISOS = fichero
        try:
            leidos = datos.avisos()
        finally:
            datos._AVISOS = original

    ok(len(leidos) == 2, "se leen las entradas válidas y se descarta el resto",
       f"{len(leidos)} de {len(lineas)} líneas")
    ok([a.jugador for a in leidos] == ["Caps", "Hans Sama"],
       "y en orden inverso: el más reciente primero",
       str([a.jugador for a in leidos]))
    ok(leidos[0].equipo == "KC", "el tricode se normaliza a mayúsculas")
    ok(leidos[1].campeon == "" and leidos[1].rango == "",
       "una entrada sin campeón ni rango se lee igual, con los campos vacíos")

    momento = datetime.fromtimestamp(_MOMENTO, timezone.utc)
    ok(leidos[0].fecha == momento.strftime("%Y-%m-%d"),
       "la fecha se calcula en UTC", leidos[0].fecha)
    ok(leidos[0].sello.endswith("+00:00"),
       "y el sello ISO lleva la zona explícita", leidos[0].sello)

    # Fichero ausente: es el estado normal de un despliegue nuevo y no puede
    # hacer fallar la generación.
    datos._AVISOS = os.path.join(gw.RAIZ, "no", "existe", "avisos.jsonl")
    try:
        ok(datos.avisos() == [], "un fichero que no existe devuelve lista vacía")
    finally:
        datos._AVISOS = original


def prueba_estilos() -> None:
    """Que la hoja de estilos y el HTML generado hablen de lo mismo.

    Es el punto de rotura natural de este diseño: el HTML lo escribe un
    generador y el CSS se mantiene a mano, así que una plantilla nueva puede
    salir sin maquetar y nadie se entera hasta que alguien abre esa página
    concreta en un móvil. Con 26 páginas, "abrirlas todas" no es un plan.

    Aquí se comprueban las dos direcciones:

    * Ninguna clase del HTML se queda sin regla → nada sale sin maquetar.
    * Ninguna regla se queda sin clase → el CSS no acumula estilos de páginas
      que ya no existen (peso muerto que se descarga en cada visita).

    Y el `font-display: swap` de la lista de SEO: se cumple si no hay ninguna
    `@font-face`, porque `system-ui` no se descarga. Si algún día se añade una
    fuente propia, esta prueba obliga a declararlo.

    Las clases se recogen de **las dos ramas** de `avisos.html`, con histórico y
    sin él. Con solo una, las reglas de la tabla de avisos saldrían como "CSS sin
    usar" mientras el registro esté vacío, y el arreglo obvio —borrarlas— dejaría
    la página sin maquetar el día que el bot empiece a avisar.
    """
    print("\n=== hoja de estilos ===")
    ruta = os.path.join(gw.RAIZ, "web", "styles.css")
    with open(ruta, encoding="utf-8") as fh:
        css = fh.read()

    paginas_html = list(sitio().values())
    with con_avisos(_avisos_falsos()):
        paginas_html += list(sitio().values())

    usadas: set[str] = set()
    for html in paginas_html:
        for atributo in re.findall(r'class="([^"]+)"', html):
            usadas.update(atributo.split())

    # Los selectores del CSS, sin los comentarios: un `.py` mencionado dentro de
    # un comentario no es una regla.
    limpio = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    definidas = set(re.findall(r"\.([a-zA-Z_][\w-]*)", limpio))

    sin_estilo = sorted(usadas - definidas)
    ok(not sin_estilo,
       f"las {len(usadas)} clases del HTML tienen regla en styles.css",
       str(sin_estilo[:5]))

    sin_usar = sorted(definidas - usadas)
    ok(not sin_usar, "y no hay reglas para clases que ya no se generan",
       str(sin_usar[:5]))

    fuentes = re.findall(r"@font-face\s*\{[^}]*\}", limpio)
    sin_swap = [f for f in fuentes if "font-display: swap" not in f]
    ok(not sin_swap,
       f"toda @font-face declara font-display: swap ({len(fuentes)} fuentes web)",
       str(len(sin_swap)))

    # El hueco del anuncio tiene que tener altura reservada aunque AdSense no
    # esté activo, o la página salta cuando el iframe entra. Es CLS.
    ok("min-height" in re.search(r"\.anuncio\s*\{[^}]*\}", limpio).group(0),
       "el hueco del anuncio reserva altura (evita el salto de maquetación)")


def prueba_generacion_completa() -> None:
    """La comprobación de conjunto: que `main()` acaba en 0 sin escribir en `web/`."""
    print("\n=== generación completa ===")

    with tempfile.TemporaryDirectory() as tmp:
        codigo = gw.main(["--destino", tmp, "--fecha", FECHA, "--sitio", SITIO])
        ok(codigo == 0, "generar la web entera termina sin errores", f"código {codigo}")

        ficheros = set(os.listdir(tmp))
        for obligatorio in ("index.html", "ligas.html", "avisos.html", "404.html",
                            "sitemap.xml", "robots.txt", "og.png", "favicon.svg",
                            "styles.css", "legal.html"):
            ok(obligatorio in ficheros, f"se escribe {obligatorio}")

        ok(len([f for f in ficheros if f.startswith("liga-")]) == len(LIGAS),
           f"y las {len(LIGAS)} páginas de liga",
           f"{len([f for f in ficheros if f.startswith('liga-')])}")

        png = os.path.join(tmp, "og.png")
        medida = datos.medir_imagen(png)
        ok(medida == (seo.OG_ANCHO, seo.OG_ALTO),
           "la imagen social mide lo que declaran las meta etiquetas", str(medida))

        ok(os.path.isdir(os.path.join(tmp, "img", "teams")),
           "las imágenes referenciadas se copian a img/")

        # El sitemap escrito tiene que coincidir con los HTML escritos, leídos
        # del disco: es la comprobación que no se puede hacer en memoria.
        with open(os.path.join(tmp, "sitemap.xml"), encoding="utf-8") as fh:
            xml = fh.read()
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        locs = {n.text for n in ET.fromstring(xml).iter(f"{ns}loc")}
        htmls = {
            seo.absoluta(SITIO, f) for f in ficheros
            if f.endswith(".html") and f != "404.html"
        }
        ok(locs == htmls,
           "el sitemap escrito coincide con los HTML escritos en disco",
           f"sitemap {len(locs)} / html {len(htmls)}")


def main() -> int:
    prueba_html_bien_formado()
    prueba_titulos_unicos()
    prueba_canonicos()
    prueba_un_solo_h1()
    prueba_open_graph()
    prueba_sitemap_y_robots()
    prueba_404()
    prueba_imagenes()
    prueba_jsonld()
    prueba_enlaces_internos()
    prueba_ligas()
    prueba_datos_de_liga()
    prueba_planes()
    prueba_adsense()
    prueba_legal()
    prueba_descargo()
    prueba_comparativa()
    prueba_avisos()
    prueba_historico_de_avisos()
    prueba_registro_de_avisos()
    prueba_estilos()
    prueba_generacion_completa()
    print(f"\nfallos : {len(fallos)}")
    for f in fallos:
        print(f"  - {f}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())




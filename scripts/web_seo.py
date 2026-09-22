"""SEO técnico de la web: cabecera, datos estructurados, sitemap y robots.

Por qué está separado de `generar_web.py`
-----------------------------------------
`generar_web.py` decide *qué dice* la web; esto decide *cómo la leen Google y los
LLM*. La separación no es orden por gusto: la lista de rutas se usa dos veces
—para escribir los ficheros y para escribir el `sitemap.xml`— y mientras las dos
cosas vivían en la misma función era posible añadir una página y olvidarse del
sitemap. Aquí el sitemap **solo** puede construirse a partir de la lista de
páginas que se han escrito de verdad (`sitemap()` recibe esa lista), así que no
se puede desincronizar. Es el requisito de "sitemap generado, nunca mantenido a
mano", cumplido por construcción y no por disciplina.

Las reglas que se aplican, y por qué cada una
---------------------------------------------
* **HTML indexable sin JavaScript.** Todo lo que sale de aquí es fichero
  estático: título, descripción y canónico están en el HTML crudo. Un rastreador
  que no ejecute JS ve la página completa.
* **Canónico absoluto y autorreferente.** Necesita el dominio, y por eso
  `normalizar_sitio()` es obligatorio y valida: un canónico relativo o apuntando
  a otro sitio es *peor* que no ponerlo, porque le está diciendo a Google que la
  página buena es otra.
* **Datos estructurados que coinciden con lo que se ve.** `faq()` recibe las
  mismas preguntas que la página pinta en HTML, y `aplicacion()` solo declara el
  plan gratuito porque es el único que hoy se puede "adquirir" de verdad. Marcar
  un `Offer` de 3,99 € sin pasarela es exactamente el schema que no corresponde
  al contenido visible.
* **Sin invenciones.** No hay `aggregateRating` ni `review`: no hay reseñas que
  contar, y ese es el marcado que Google penaliza cuando es falso.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import date

#: Dominio por defecto. Sale del remoto real del repositorio
#: (github.com/set4jeta/JetaDirectaBot), así que las URL absolutas que genera
#: existen en cuanto se active GitHub Pages, sin inventar un dominio.
SITIO_POR_DEFECTO = "https://set4jeta.github.io/JetaDirectaBot/"

#: Tamaño de la imagen social. 1200x630 es lo que piden Twitter/X ("summary
#: large image") y lo que Facebook recomienda; con menos de 600 de ancho X
#: degrada la tarjeta a la versión pequeña.
OG_ANCHO, OG_ALTO = 1200, 630

#: Idioma de la versión que hoy se publica, y su `og:locale`.
#:
#: Existen como constantes y no escritos a mano en cada sitio porque cuando
#: llegue la versión inglesa hay **seis** lugares que tienen que cambiar juntos:
#: `<html lang>`, `og:locale`, `inLanguage` del `Article`, el `hreflang`, el
#: `x-default` y el idioma de las FAQ. Cambiar cinco de seis es el error típico
#: y no da ningún aviso: simplemente Google decide que las dos versiones son la
#: misma página y se queda con una.
#:
#: El 3 de septiembre de 2026 el proyecto pasó a publicar en **inglés** y no en
#: español. El motivo es de negocio y no de preferencia: el mercado que paga
#: (patrocinios, datos en tiempo real, suscripciones) se negocia en inglés, y el
#: tráfico de búsqueda de esports en inglés es un orden de magnitud mayor que el
#: de "partidos de LoL" en español. El bot ya era bilingüe (`/lang en`), así que
#: la web era la única superficie que faltaba.
IDIOMA = "en"
LOCALES = {"es": "es_ES", "en": "en_US"}

#: Prefijo de ruta por idioma dentro del sitio.
#:
#: Vacío significa "en la raíz". El inglés ocupa la raíz porque la raíz es la
#: URL que se comparte y la que acumula autoridad (ver
#: `docs/seo/04-estrategia-ingles.md`). El español pasará a `/es/` el día que
#: exista; mientras no exista, mover nada sería cambiar direcciones por nada.
PREFIJOS = {"es": "es/", "en": ""}

#: Idiomas con versión publicada. **Mientras esto tenga un solo elemento no se
#: emite ningún `hreflang`**, y eso es deliberado: declarar una alternativa que
#: no existe es un error de rastreo, no un adelanto. Se añade `"es"` el día que
#: las páginas españolas estén escritas de nuevo, no antes.
IDIOMAS_PUBLICADOS: tuple[str, ...] = ("en",)

#: A qué idioma cae quien no encaja en ninguno de los declarados. Tiene que ser
#: el que se sirve en la raíz.
IDIOMA_POR_DEFECTO = "en"


def etiqueta_idioma(idioma: str = "") -> str:
    """`"es"` -> `"es-ES"`. La forma BCP-47 que quiere `inLanguage` de schema.org.

    `og:locale` usa guion bajo (`es_ES`) y schema.org usa guion (`es-ES`). Son dos
    formatos distintos para el mismo dato y confundirlos hace que uno de los dos
    se ignore en silencio, así que se derivan los dos de `LOCALES`.
    """
    return LOCALES[idioma or IDIOMA].replace("_", "-")


def e(texto: str) -> str:
    """Escapa para atributos HTML."""
    return html.escape(str(texto), quote=True)


def normalizar_sitio(valor: str) -> str:
    """Deja la URL base en forma canónica, o levanta si no sirve.

    Exige https y termina en `/`. Las dos cosas por el mismo motivo: todo lo que
    hay debajo concatena rutas a esta cadena, así que `https://x.com` y
    `https://x.com/` producirían `https://x.compagina.html`. Y un canónico en
    http sobre un sitio servido por https es una redirección permanente que
    Google resuelve pero que rompe la coincidencia exacta.
    """
    limpio = (valor or "").strip()
    if not limpio:
        return SITIO_POR_DEFECTO
    if limpio.startswith("http://"):
        limpio = "https://" + limpio[len("http://"):]
    if not limpio.startswith("https://"):
        limpio = "https://" + limpio
    if "?" in limpio or "#" in limpio or " " in limpio:
        raise SystemExit(
            f"URL del sitio no válida: {valor!r}. Se espera algo como "
            "'https://midominio.com/' sin parámetros ni espacios."
        )
    return limpio if limpio.endswith("/") else limpio + "/"


def absoluta(sitio: str, ruta: str) -> str:
    """URL absoluta de una ruta del sitio.

    `index.html` se canoniza a la carpeta (`https://sitio/`) y no a
    `https://sitio/index.html`: las dos sirven la misma página, así que hay que
    elegir una, y la que la gente enlaza y comparte es la carpeta.
    """
    if ruta in ("index.html", "/index.html", ""):
        return sitio
    return sitio + ruta.lstrip("/")


def absoluta_en(sitio: str, ruta: str, idioma: str) -> str:
    """La misma ruta en otro idioma. `PREFIJOS` decide dónde vive cada versión.

    Se usa solo para construir los `hreflang`. Cuando `PREFIJOS["en"]` pase a ser
    `"en/"`, `absoluta_en(sitio, "index.html", "en")` devolverá `https://sitio/en/`
    sin tocar nada más.
    """
    prefijo = PREFIJOS.get(idioma, "")
    if ruta in ("index.html", "/index.html", ""):
        return sitio + prefijo
    return sitio + prefijo + ruta.lstrip("/")


def alternativas(sitio: str, ruta: str) -> str:
    """Las etiquetas `hreflang` de una ruta, o cadena vacía.

    Devuelve vacío mientras solo haya un idioma publicado, y eso es la parte
    importante de esta función. Las reglas que respeta, que son las que se rompen
    siempre:

    * **Autorreferencia**: el conjunto incluye la propia página, no solo las
      otras. Sin ella Google descarta la anotación entera.
    * **Reciprocidad**: como todas las páginas se generan con esta misma función,
      la reciprocidad sale por construcción. Es el motivo de generarlo aquí y no
      escribirlo por página.
    * **URL absolutas**: `hreflang` no admite rutas relativas.
    * **`x-default`**: apunta al idioma que se sirve en la raíz.
    """
    if len(IDIOMAS_PUBLICADOS) < 2:
        return ""
    lineas = [
        f'  <link rel="alternate" hreflang="{idioma}" '
        f'href="{e(absoluta_en(sitio, ruta, idioma))}">'
        for idioma in IDIOMAS_PUBLICADOS
    ]
    lineas.append(
        '  <link rel="alternate" hreflang="x-default" '
        f'href="{e(absoluta_en(sitio, ruta, IDIOMA_POR_DEFECTO))}">'
    )
    return "\n".join(lineas) + "\n"


@dataclass
class Pagina:
    """Una ruta pública del sitio, con todo lo que su `<head>` necesita.

    Existe para que no se pueda escribir una página sin decidir su título y su
    descripción. La comprobación de que los dos son **únicos** entre páginas se
    hace en `scripts/test_web.py`, porque el problema de los títulos duplicados
    no se ve mirando una página: se ve comparándolas todas.
    """

    ruta: str          # "index.html", "liga-lec.html"...
    titulo: str        # el <title> y el og:title
    descripcion: str   # la meta description y el og:description
    #: HTML del cuerpo, ya montado por el generador.
    cuerpo: str = ""
    #: `Article`, `FAQPage`... Se pasa ya serializado por `jsonld()`.
    schemas: list[str] = field(default_factory=list)
    #: Prioridad relativa en el sitemap. No es un ranking: solo le dice al
    #: rastreador qué parte del sitio es el centro.
    prioridad: str = "0.5"
    #: Fuera del sitemap y con `noindex`. Es lo que hay que hacer con el 404:
    #: tiene que existir y devolver 404, pero no ser un resultado de búsqueda.
    indexable: bool = True

    @property
    def es_inicio(self) -> bool:
        return self.ruta == "index.html"


# ---------------------------------------------------------------------- #
# Cabecera
# ---------------------------------------------------------------------- #

def meta_seo(pagina: Pagina, sitio: str, *, og_imagen: str = "og.png") -> str:
    """Las etiquetas de `<head>` que Google y los LLM leen de verdad.

    Orden y contenido salen de la lista del usuario, punto por punto:

    * `<link rel="canonical">` **absoluto y autorreferente** en cada página.
    * Open Graph completo *con imagen*: sin `og:image` Discord y X pintan la
      tarjeta sin nada, y el sitio se va a compartir sobre todo en Discord.
    * `twitter:card` a `summary_large_image`, que es la que usa una imagen de
      1200x630; con `summary` se recorta a un cuadrado pequeño.
    * `og:image:width`/`height` declarados: X y Discord cachean la tarjeta la
      primera vez que ven la URL, y si tienen que descargar la imagen para medirla
      la primera compartición sale sin imagen.
    * `robots` a `noindex` solo en las páginas marcadas (el 404).
    * `hreflang` **solo si hay más de un idioma publicado** (`alternativas()`).
      Declarar una versión que no existe es un error de rastreo, no un adelanto.

    `og:locale` sale de `LOCALES[IDIOMA]` en vez de estar escrito aquí porque es
    uno de los seis sitios que tienen que cambiar juntos el día que exista la
    versión inglesa, y ese es el tipo de cambio que falla en silencio.
    """
    url = absoluta(sitio, pagina.ruta)
    imagen = absoluta(sitio, og_imagen)
    tipo = "article" if not pagina.es_inicio else "website"
    lineas = [
        f'  <title>{e(pagina.titulo)}</title>',
        f'  <meta name="description" content="{e(pagina.descripcion)}">',
        f'  <link rel="canonical" href="{e(url)}">',
    ]
    if not pagina.indexable:
        # `noindex, follow`: que no salga en búsquedas pero que sí siga los
        # enlaces del menú, para que un rastreador que aterrice en el 404
        # encuentre la salida en vez de darse la vuelta.
        lineas.append('  <meta name="robots" content="noindex, follow">')
    lineas += [
        f'  <meta property="og:title" content="{e(pagina.titulo)}">',
        f'  <meta property="og:description" content="{e(pagina.descripcion)}">',
        f'  <meta property="og:type" content="{tipo}">',
        f'  <meta property="og:url" content="{e(url)}">',
        f'  <meta property="og:image" content="{e(imagen)}">',
        f'  <meta property="og:image:width" content="{OG_ANCHO}">',
        f'  <meta property="og:image:height" content="{OG_ALTO}">',
        f'  <meta property="og:locale" content="{LOCALES[IDIOMA]}">',
        '  <meta name="twitter:card" content="summary_large_image">',
        f'  <meta name="twitter:title" content="{e(pagina.titulo)}">',
        f'  <meta name="twitter:description" content="{e(pagina.descripcion)}">',
        f'  <meta name="twitter:image" content="{e(imagen)}">',
    ]
    # El 404 no lleva `hreflang`: no es una página con versiones equivalentes,
    # es una respuesta de error, y anotarla como alternativa de algo confunde
    # al rastreador sin ganar nada.
    if pagina.indexable:
        alt = alternativas(sitio, pagina.ruta)
        if alt:
            lineas.append(alt.rstrip("\n"))
    return "\n".join(lineas) + "\n"


# ---------------------------------------------------------------------- #
# Datos estructurados (JSON-LD)
# ---------------------------------------------------------------------- #
#
# Se escriben a mano en vez de con `json.dumps` de un dict por una razón
# concreta: hay que escapar `</script>` dentro del JSON, y ningún serializador
# lo hace porque para JSON no es un problema. Dentro de un `<script>` de HTML sí:
# el navegador cierra la etiqueta ahí mismo. Con nombres de equipo y de jugador
# que salen de datos remotos, eso es una inyección esperando a pasar.

def _json(valor, nivel: int = 1) -> str:
    """Serializa a JSON seguro para meter dentro de `<script>`.

    Escapa `<`, `>` y `&` a `\\u003c` y compañía, que es lo que hace la propia
    documentación de Google para JSON-LD: sigue siendo JSON válido y ya no puede
    cerrar la etiqueta.
    """
    sangria = "  " * nivel
    if isinstance(valor, dict):
        if not valor:
            return "{}"
        partes = [
            f'{sangria}  {_json(k, nivel + 1)}: {_json(v, nivel + 1)}'
            for k, v in valor.items() if v is not None
        ]
        return "{\n" + ",\n".join(partes) + "\n" + sangria + "}"
    if isinstance(valor, (list, tuple)):
        if not valor:
            return "[]"
        partes = [f"{sangria}  {_json(v, nivel + 1)}" for v in valor]
        return "[\n" + ",\n".join(partes) + "\n" + sangria + "]"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return repr(valor)
    texto = str(valor)
    salida = ['"']
    for ch in texto:
        if ch == '"':
            salida.append('\\"')
        elif ch == "\\":
            salida.append("\\\\")
        elif ch == "\n":
            salida.append("\\n")
        elif ch in "<>&":
            salida.append(f"\\u{ord(ch):04x}")
        elif ord(ch) < 0x20:
            salida.append(f"\\u{ord(ch):04x}")
        else:
            salida.append(ch)
    salida.append('"')
    return "".join(salida)


def jsonld(datos: dict) -> str:
    """Envuelve un bloque de datos estructurados en su `<script>`."""
    return (
        '  <script type="application/ld+json">\n'
        f"  {_json(datos)}\n"
        "  </script>\n"
    )


def organizacion(sitio: str, nombre: str, *, soporte: str = "") -> dict:
    """`Organization` para la home.

    No dice "empresa" en ninguna parte porque no lo es —la política de privacidad
    generada dice literalmente "No hay ninguna empresa detrás"— y el schema no
    puede contradecir al documento legal del mismo sitio.
    """
    datos: dict = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": sitio + "#organizacion",
        "name": nombre,
        "url": sitio,
        "logo": absoluta(sitio, "og.png"),
    }
    if soporte:
        datos["sameAs"] = [soporte]
    return datos


def sitio_web(sitio: str, nombre: str, descripcion: str) -> dict:
    """`WebSite` para la home.

    Sin `SearchAction`: el sitio no tiene buscador. Declarar uno que no existe es
    el marcado que no coincide con el contenido visible.
    """
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": sitio + "#web",
        "name": nombre,
        "url": sitio,
        "description": descripcion,
        "inLanguage": etiqueta_idioma(),
        "publisher": {"@id": sitio + "#organizacion"},
    }


def aplicacion(sitio: str, nombre: str, descripcion: str, *, invite: str = "") -> dict:
    """`SoftwareApplication` del bot.

    El `offers` declara **0 €** y solo eso. Los planes de pago existen en la
    tabla de precios, pero hoy no hay pasarela: un `Offer` de 3,99 € sería un
    precio que nadie puede pagar, y ese es justo el caso que Google trata como
    marcado engañoso. Cuando exista el cobro, se añade aquí y en el mismo commit
    que la pasarela.
    """
    datos: dict = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": nombre,
        "applicationCategory": "GameApplication",
        "operatingSystem": "Discord",
        "url": sitio,
        "description": descripcion,
        # El bot habla los dos idiomas aunque la web todavia no: esto
        # describe la aplicacion, no la pagina.
        "inLanguage": ["es", "en"],
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "EUR",
            "description": "Plan gratuito con avisos de partida completos.",
        },
        "publisher": {"@id": sitio + "#organizacion"},
    }
    if invite:
        datos["installUrl"] = invite
    return datos


def faq(preguntas: list[tuple[str, str]]) -> dict:
    """`FAQPage` a partir de las preguntas que la página **pinta en HTML**.

    Recibe la misma lista que se usa para escribir el `<h2>`/`<p>` visible, y no
    una lista propia, porque la regla del usuario es explícita: nunca schema que
    no coincida con el contenido visible. Si la sección de FAQ se quita del HTML,
    esta lista queda vacía y no se emite el bloque.

    Nota de 2026: Google retiró el *rich result* de FAQ (ya no pinta el
    acordeón en los resultados), pero el tipo de schema sigue siendo válido y
    sigue siendo la forma más limpia de darle a un LLM un par
    pregunta-respuesta delimitado. Se mantiene por eso, no por la estrellita.
    """
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": pregunta,
                "acceptedAnswer": {"@type": "Answer", "text": respuesta},
            }
            for pregunta, respuesta in preguntas
        ],
    }


def articulo(
    sitio: str, pagina: Pagina, fecha: str, autor: str, *, modificado: str = ""
) -> dict:
    """`Article` para una página de contenido.

    `dateModified` va siempre. Es el campo que de verdad importa aquí: los
    sistemas que resumen con IA pesan la recencia, y una comparativa "2026" sin
    fecha de modificación es indistinguible de una de 2023.

    Por defecto es la fecha de generación, que para estas páginas es correcto: su
    contenido sale de los datos del bot y se rehace en cada regeneración.

    `modificado` sirve para declarar una fecha **anterior y más honesta** cuando
    se sabe cuándo cambió el contenido de verdad. `avisos.html` la fija en el
    último aviso registrado: regenerar el sitio un lunes en el que el bot no ha
    avisado no hace que esa página tenga nada nuevo, y estampar la fecha de hoy
    sería exactamente la frescura falsa que estos sistemas acaban descontando.

    Se aplica a los dos campos, no solo a `dateModified`, porque una página no
    puede estar modificada antes de publicarse. Como aquí no se guarda la fecha
    real de primera publicación, lo único que se puede afirmar sin inventar es
    "este contenido es del día X".
    """
    sello = modificado or fecha
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": pagina.titulo,
        "description": pagina.descripcion,
        "mainEntityOfPage": absoluta(sitio, pagina.ruta),
        "datePublished": sello,
        "dateModified": sello,
        "inLanguage": etiqueta_idioma(),
        "image": absoluta(sitio, "og.png"),
        "author": {"@type": "Organization", "name": autor},
        "publisher": {"@id": sitio + "#organizacion"},
    }


def migas(sitio: str, camino: list[tuple[str, str]]) -> dict:
    """`BreadcrumbList`. `camino` son pares `(nombre, ruta)`.

    Se emite en las páginas internas porque es lo que hace que en el resultado de
    búsqueda salga "jetadirectabot.com > Ligas > LEC" en vez de la URL cruda, y
    porque le dice al rastreador cómo está organizado el sitio sin depender de que
    interprete el menú.
    """
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i,
                "name": nombre,
                "item": absoluta(sitio, ruta),
            }
            for i, (nombre, ruta) in enumerate(camino, start=1)
        ],
    }


def lista_items(nombre: str, elementos: list[tuple[str, str]], *,
                ascendente: bool = False) -> dict:
    """`ItemList` para una tabla o ranking visible.

    Es el schema que le pone nombre a una lista ordenada que ya está en el HTML
    (por ejemplo el top de Elo de una liga). Sirve para lo que el usuario busca
    con esto: que un LLM pueda extraer la lista con su orden intacto en vez de
    tener que reconstruirla del texto.

    `ascendente` existe porque el orden se declara y no se adivina: una tabla de
    Elo va de más a menos, pero un calendario va de hoy hacia delante. Declarar
    descendente en un calendario es un dato falso pequeño, y el orden es
    justamente lo que hace útil a una lista extraída.
    """
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": nombre,
        "numberOfItems": len(elementos),
        "itemListOrder": (
            "https://schema.org/ItemListOrderAscending" if ascendente
            else "https://schema.org/ItemListOrderDescending"
        ),
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": item, "description": detalle}
            for i, (item, detalle) in enumerate(elementos, start=1)
        ],
    }


# ---------------------------------------------------------------------- #
# sitemap.xml y robots.txt
# ---------------------------------------------------------------------- #

def sitemap(sitio: str, paginas: list[Pagina], fecha: str | None = None) -> str:
    """El `sitemap.xml`, generado desde las páginas que se escriben de verdad.

    Recibe la lista de páginas en vez de leer la carpeta de salida a propósito:
    si leyera el disco, un fichero viejo de una ejecución anterior (una página
    que se renombró) seguiría en el sitemap apuntando a un 404, y un sitemap con
    URL muertas es peor que no tenerlo.

    Las no indexables se excluyen. Meter el 404 en el sitemap es pedirle a Google
    que indexe una página de error.

    Sobre avisar a Google: **no se hace ping**. Google retiró el endpoint de ping
    de sitemaps en 2023 (lo anunció en su blog de Search Central y ya no
    responde); hoy el sitemap se descubre por `robots.txt` o se sube una vez en
    Search Console. Un script que hiciera ping fallaría en silencio y daría la
    falsa sensación de haber avisado.
    """
    hoy = fecha or date.today().isoformat()
    filas = []
    for pagina in paginas:
        if not pagina.indexable:
            continue
        filas.append(
            "  <url>\n"
            f"    <loc>{e(absoluta(sitio, pagina.ruta))}</loc>\n"
            f"    <lastmod>{e(hoy)}</lastmod>\n"
            f"    <priority>{e(pagina.prioridad)}</priority>\n"
            "  </url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(filas)
        + "\n</urlset>\n"
    )


def robots(sitio: str) -> str:
    """`robots.txt` que permite todo y apunta al sitemap.

    No lleva ningún `Disallow` de `.css` ni de `.js`, que es el error que la lista
    del usuario señala: Google renderiza la página para valorarla, y bloquear la
    hoja de estilos hace que la vea sin maquetar y la juzgue como no apta para
    móvil. Aquí además no hay nada privado que esconder: son cuatro ficheros
    estáticos.

    El `Sitemap:` absoluto es hoy la vía real de descubrimiento, desde que Google
    retiró el ping.
    """
    return (
        "# Todo el sitio es público y estático: no hay nada que bloquear.\n"
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {absoluta(sitio, 'sitemap.xml')}\n"
    )

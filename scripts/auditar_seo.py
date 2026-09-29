"""Audita la web **publicada** contra la lista de comprobación de SEO.

Por qué audita lo publicado y no lo generado
--------------------------------------------
`test_web.py` comprueba lo que el generador produce. Esto comprueba lo que
**sirve internet**, que no es lo mismo: un `canonical` perfecto en local no vale
de nada si Pages sirve una versión vieja, si una página del sitemap da 404 o si
falta un fichero que no se copió. La diferencia entre los dos se llama despliegue
y es donde se rompen las cosas.

Uso:
    python scripts/auditar_seo.py [--sitio https://...] [--local]

Sin argumentos audita el sitio de producción. Con `--local` audita
`http://127.0.0.1:8899`, que sirve para comprobar antes de publicar.

Qué **no** puede comprobar, y por eso lo dice en vez de callarlo
--------------------------------------------------------------
Lo que depende de terceros o de personas: si el sitemap está enviado a Search
Console, si hay GA4, las Core Web Vitals medidas de verdad (aquí solo se estima
el peso), el `dateModified` real, las palabras clave de la competencia y los
enlaces entrantes. Esas salen marcadas como «a mano» para que la lista no parezca
más completa de lo que es.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

TIEMPO = 20

ok_count = 0
fallos: list[str] = []
avisos: list[str] = []
manual: list[str] = []


def linea(estado: str, etiqueta: str, detalle: str = "") -> None:
    global ok_count
    if estado == "OK":
        ok_count += 1
    print(f"  [{estado:^5}] {etiqueta}" + (f" — {detalle}" if detalle else ""))


def bien(etiqueta: str, detalle: str = "") -> None:
    linea("OK", etiqueta, detalle)


def mal(etiqueta: str, detalle: str = "") -> None:
    fallos.append(etiqueta)
    linea("FALLA", etiqueta, detalle)


def ojo(etiqueta: str, detalle: str = "") -> None:
    avisos.append(etiqueta)
    linea("AVISO", etiqueta, detalle)


def a_mano(etiqueta: str, detalle: str = "") -> None:
    manual.append(etiqueta)
    linea("A MANO", etiqueta, detalle)


# ---------------------------------------------------------------------- #
# Descarga
# ---------------------------------------------------------------------- #

def traer(url: str) -> tuple[int, str]:
    peticion = urllib.request.Request(url, headers={"User-Agent": "LoLProTrackr-SEO/1.0"})
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


class Pagina(HTMLParser):
    """Lo que hace falta de cada página, sin dependencias."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titulo = ""
        self.descripcion = ""
        self.canonical = ""
        self.hreflang: list[str] = []
        self.lang = ""
        self.viewport = False
        self.og: set[str] = set()
        self.robots = ""
        self.encabezados: list[tuple[int, str]] = []
        self.imagenes: list[tuple[str, str]] = []
        self.enlaces: list[str] = []
        self.jsonld: list[str] = []
        self.scripts_externos: list[str] = []
        self.scripts_diferidos: set[str] = set()
        self._en_titulo = False
        self._en_h: int | None = None
        self._texto_h = ""
        self._en_script_ld = False
        self._buf_ld = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self._en_titulo = True
        elif tag == "meta":
            nombre = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            if nombre == "description":
                self.descripcion = a.get("content", "")
            elif nombre == "viewport":
                self.viewport = True
            elif nombre == "robots":
                self.robots = (a.get("content") or "").lower()
            if prop.startswith("og:") or nombre.startswith("twitter:"):
                self.og.add(prop or nombre)
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if rel == "canonical":
                self.canonical = a.get("href", "")
            elif rel == "alternate" and a.get("hreflang"):
                self.hreflang.append(a["hreflang"])
        elif tag in ("h1", "h2", "h3", "h4"):
            self._en_h = int(tag[1])
            self._texto_h = ""
        elif tag == "img":
            self.imagenes.append((a.get("src", ""), a.get("alt", "")))
        elif tag == "a" and a.get("href"):
            self.enlaces.append(a["href"])
        elif tag == "script":
            tipo = (a.get("type") or "").lower()
            if "ld+json" in tipo:
                self._en_script_ld = True
                self._buf_ld = ""
            elif a.get("src"):
                self.scripts_externos.append(a["src"])
                # `defer`/`async` = no bloquea el render, que es lo que importa.
                if "defer" in a or "async" in a:
                    self.scripts_diferidos.add(a["src"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._en_titulo = False
        elif tag in ("h1", "h2", "h3", "h4") and self._en_h is not None:
            self.encabezados.append((self._en_h, " ".join(self._texto_h.split())))
            self._en_h = None
        elif tag == "script" and self._en_script_ld:
            self.jsonld.append(self._buf_ld)
            self._en_script_ld = False

    def handle_data(self, datos):
        if self._en_titulo:
            self.titulo += datos
        if self._en_h is not None:
            self._texto_h += datos
        if self._en_script_ld:
            self._buf_ld += datos


# ---------------------------------------------------------------------- #
# Comprobaciones
# ---------------------------------------------------------------------- #

def auditar(sitio: str) -> None:
    sitio = sitio.rstrip("/") + "/"
    print("=" * 72)
    print(f"AUDITORÍA SEO · {sitio}")
    print("=" * 72)

    # ---- rastreable -------------------------------------------------- #
    print("\n### Rastreo e indexación\n")

    estado, robots = traer(sitio + "robots.txt")
    if estado == 200 and "sitemap" in robots.lower():
        bien("robots.txt existe y apunta al sitemap")
    else:
        mal("robots.txt", f"estado {estado}")

    estado, sitemap = traer(sitio + "sitemap.xml")
    if estado != 200:
        mal("sitemap.xml accesible", f"estado {estado}")
        return
    # El sitemap declara las URL del dominio de **producción** (tiene que
    # hacerlo: un sitemap con `localhost` sería un error). Al auditar en local
    # hay que traducirlas, o la auditoría se sale a internet sin avisar y
    # comprueba producción creyendo que comprueba tu copia.
    declaradas = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    base_declarada = declaradas[0].rsplit("/", 1)[0] + "/" if declaradas else sitio
    urls = [
        sitio + u[len(base_declarada):] if u.startswith(base_declarada) else u
        for u in declaradas
    ]
    bien("sitemap.xml accesible", f"{len(urls)} URL"
         + (f" (reescritas desde {base_declarada})" if base_declarada != sitio else ""))

    # Cada URL del sitemap tiene que responder 200. Una URL muerta en el sitemap
    # es peor que no tenerlo: le pides a Google que rastree un 404.
    muertas = []
    for u in urls:
        e, _ = traer(u)
        if e != 200:
            muertas.append(f"{u} -> {e}")
    if muertas:
        mal("ninguna URL del sitemap da error", "; ".join(muertas[:3]))
    else:
        bien("todas las URL del sitemap responden 200", f"{len(urls)} comprobadas")

    # Páginas huérfanas: están en el sitemap pero no las enlaza nadie. Google las
    # encuentra por el sitemap, pero sin enlaces internos no reciben autoridad.
    enlazadas: set[str] = set()
    paginas: dict[str, Pagina] = {}
    for u in urls:
        e, html = traer(u)
        if e != 200:
            continue
        p = Pagina()
        p.feed(html)
        paginas[u] = p
        for h in p.enlaces:
            absoluta = urllib.parse.urljoin(u, h).split("#")[0]
            enlazadas.add(absoluta)

    huerfanas = [u for u in urls if u not in enlazadas and u != sitio]
    if huerfanas:
        ojo("páginas sin enlaces internos", f"{len(huerfanas)}: " +
            ", ".join(u.rsplit("/", 1)[-1] for u in huerfanas[:4]))
    else:
        bien("ninguna página huérfana", f"{len(urls)} páginas enlazadas")

    # Enlaces internos roscados: comprobar unos pocos, no todos (serían miles).
    internos = {u for u in enlazadas if u.startswith(sitio)}
    roscados = []
    for u in sorted(internos)[:40]:
        if u in paginas or u in urls:
            continue
        e, _ = traer(u)
        if e != 200:
            roscados.append(f"{u.rsplit('/', 1)[-1]} -> {e}")
    if roscados:
        mal("ningún enlace interno roto", "; ".join(roscados[:3]))
    else:
        bien("enlaces internos sin 404", f"{min(len(internos), 40)} comprobados")

    # ---- on-page ------------------------------------------------------ #
    print("\n### On-page\n")

    cortos = [u for u, p in paginas.items() if len(p.titulo.strip()) < 50]
    largos = [u for u, p in paginas.items() if len(p.titulo.strip()) > 60]
    if largos:
        ojo("títulos de 50-60 caracteres", f"{len(largos)} se pasan de 60")
    elif cortos:
        ojo("títulos de 50-60 caracteres", f"{len(cortos)} por debajo de 50")
    else:
        bien("títulos entre 50 y 60 caracteres", f"{len(paginas)} páginas")

    titulos = [p.titulo.strip() for p in paginas.values()]
    if len(set(titulos)) != len(titulos):
        mal("títulos únicos")
    else:
        bien("títulos únicos", f"{len(titulos)}")

    sin_desc = [u for u, p in paginas.items() if not p.descripcion.strip()]
    if sin_desc:
        mal("todas las páginas tienen meta descripción", f"{len(sin_desc)} sin ella")
    else:
        descs = [p.descripcion.strip() for p in paginas.values()]
        if len(set(descs)) != len(descs):
            mal("meta descripciones únicas")
        else:
            # Dos umbrales, y la diferencia importa.
            #
            # 190 es la regla del propio proyecto (`generar_web.DESC_MAX`, que
            # `test_web` hace cumplir): por encima de eso Google corta con «...»
            # a mitad de frase y deja de ser una promesa legible.
            #
            # 160 es más fino: a partir de ahí **puede** recortarse en escritorio,
            # porque el límite real de Google es en píxeles y una descripción de
            # 170 cabe o no según qué letras tenga. Por eso es aviso y no fallo:
            # no está mal, está al límite.
            pasadas = [u for u, p in paginas.items() if len(p.descripcion) > 190]
            al_limite = [u for u, p in paginas.items() if 160 < len(p.descripcion) <= 190]
            if pasadas:
                mal("meta descripciones de menos de 190 caracteres",
                    f"{len(pasadas)} se pasan: " +
                    ", ".join(u.rsplit("/", 1)[-1] for u in pasadas[:3]))
            elif al_limite:
                ojo("meta descripciones por debajo de 160 (pueden recortarse)",
                    f"{len(al_limite)}: " +
                    ", ".join(u.rsplit("/", 1)[-1] for u in al_limite[:3]))
            else:
                bien("meta descripciones únicas y holgadas", f"{len(descs)}")

    sin_h1 = [u for u, p in paginas.items() if sum(1 for n, _ in p.encabezados if n == 1) != 1]
    if sin_h1:
        mal("exactamente un <h1> por página",
            f"{len(sin_h1)} con 0 o varios: " + ", ".join(u.rsplit("/", 1)[-1] for u in sin_h1[:3]))
    else:
        bien("exactamente un <h1> por página", f"{len(paginas)}")

    # Saltos de nivel: un h3 sin h2 antes despista a los lectores de pantalla.
    saltos = []
    for u, p in paginas.items():
        anterior = 0
        for nivel, _ in p.encabezados:
            if anterior and nivel > anterior + 1:
                saltos.append(f"{u.rsplit('/', 1)[-1]}: h{anterior}->h{nivel}")
                break
            anterior = nivel
    if saltos:
        ojo("jerarquía de encabezados sin saltos", "; ".join(saltos[:3]))
    else:
        bien("jerarquía de encabezados sin saltos")

    # Alt en las imágenes. Las decorativas llevan alt="" a propósito, así que se
    # cuentan como correctas: lo que se busca es el atributo que falta.
    sin_alt = []
    for u, p in paginas.items():
        faltan = [s for s, alt in p.imagenes if alt is None]
        if faltan:
            sin_alt.append(f"{u.rsplit('/', 1)[-1]}: {len(faltan)}")
    if sin_alt:
        mal("todas las imágenes llevan atributo alt", "; ".join(sin_alt[:3]))
    else:
        total = sum(len(p.imagenes) for p in paginas.values())
        bien("todas las imágenes llevan alt", f"{total} imágenes")

    sin_canonical = [u for u, p in paginas.items() if not p.canonical]
    if sin_canonical:
        mal("todas las páginas declaran canónico", f"{len(sin_canonical)} sin él")
    else:
        # Y el canónico tiene que ser la propia página: uno que apunte a otra le
        # está diciendo a Google que no indexe esta.
        #
        # Se compara por **nombre de fichero** y no por URL completa ni por ruta.
        # Por URL completa fallaría siempre en local, porque el canónico lleva el
        # dominio de producción a propósito. Y por ruta también, porque el sitio
        # vive en un subdirectorio (`/JetaDirectaBot/`) que en local no existe.
        # El nombre de fichero comprueba lo que importa —que cada página se
        # apunte a sí misma y no a otra— y funciona en los dos entornos.
        def _fichero(u: str) -> str:
            ruta = urllib.parse.urlparse(u).path
            # Una URL que termina en `/` es la portada: su fichero es
            # `index.html`. Sin esto, el canónico de la home
            # (`.../JetaDirectaBot/`) se comparaba contra el nombre del
            # repositorio y daba un fallo que no existía.
            if ruta.endswith("/"):
                return "index.html"
            return ruta.rsplit("/", 1)[-1] or "index.html"

        malos = [u for u, p in paginas.items() if _fichero(p.canonical) != _fichero(u)]
        if malos:
            mal("el canónico apunta a la propia página", f"{len(malos)} no")
        else:
            bien("canónicos correctos y autorreferentes", f"{len(paginas)}")

    indexables = [u for u, p in paginas.items() if "noindex" in p.robots]
    if indexables:
        mal("ninguna página del sitemap lleva noindex",
            ", ".join(u.rsplit("/", 1)[-1] for u in indexables[:3]))
    else:
        bien("ninguna página indexable lleva noindex")

    sin_lang = [u for u, p in paginas.items() if not p.lang]
    if sin_lang:
        mal("todas declaran <html lang>", f"{len(sin_lang)} sin él")
    else:
        idiomas = {p.lang for p in paginas.values()}
        bien("todas declaran <html lang>", ", ".join(sorted(idiomas)))

    sin_viewport = [u for u, p in paginas.items() if not p.viewport]
    if sin_viewport:
        mal("todas llevan viewport (móvil)", f"{len(sin_viewport)} sin él")
    else:
        bien("todas llevan viewport", f"{len(paginas)}")

    con_schema = [u for u, p in paginas.items() if any(j.strip() for j in p.jsonld)]
    if len(con_schema) < len(paginas):
        ojo("schema.org en todas las páginas",
            f"{len(con_schema)}/{len(paginas)} lo llevan")
    else:
        bien("schema.org en todas las páginas", f"{len(con_schema)}")

    tipos: set[str] = set()
    invalidos = []
    for u, p in paginas.items():
        for crudo in p.jsonld:
            if not crudo.strip():
                continue
            try:
                d = json.loads(crudo)
            except json.JSONDecodeError:
                invalidos.append(u.rsplit("/", 1)[-1])
                continue
            for bloque in (d if isinstance(d, list) else [d]):
                if isinstance(bloque, dict) and bloque.get("@type"):
                    t = bloque["@type"]
                    tipos.update(t if isinstance(t, list) else [t])
    if invalidos:
        mal("el JSON-LD es JSON válido", ", ".join(sorted(set(invalidos))[:3]))
    else:
        bien("el JSON-LD es JSON válido", f"tipos: {', '.join(sorted(tipos))}")

    sin_og = [u for u, p in paginas.items()
              if not {"og:title", "og:image", "og:description"} <= p.og]
    if sin_og:
        ojo("Open Graph completo (se ve al compartir)",
            f"{len(sin_og)} incompletas")
    else:
        bien("Open Graph completo en todas", f"{len(paginas)}")

    # Migas de pan: ayudan a Google a entender la jerarquía y salen en el
    # resultado de búsqueda en vez de la URL cruda.
    con_migas = 0
    for u, p in paginas.items():
        if any("breadcrumb" in j.lower() for j in p.jsonld):
            con_migas += 1
        elif any("›" in t or "&gt;" in t for _, t in p.encabezados):
            con_migas += 1
    if con_migas < len(paginas) - 3:
        ojo("migas de pan", f"{con_migas}/{len(paginas)} las llevan")
    else:
        bien("migas de pan", f"{con_migas}/{len(paginas)}")

    # ---- peso ---------------------------------------------------------- #
    print("\n### Rendimiento\n")
    pesos = []
    for u in urls:
        e, html = traer(u)
        if e == 200:
            pesos.append((len(html.encode("utf-8")), u))
    if pesos:
        media = sum(p for p, _ in pesos) / len(pesos)
        peor = max(pesos)
        if media > 150_000:
            ojo("peso medio del HTML", f"{media/1024:.0f} kB de media")
        else:
            bien("peso del HTML contenido", f"{media/1024:.0f} kB de media")
        if peor[0] > 300_000:
            ojo("la página más pesada", f"{peor[1].rsplit('/',1)[-1]}: {peor[0]/1024:.0f} kB")

    # Un script externo cuenta como bloqueante solo si no lleva `defer` ni
    # `async`, y los propios no cuentan: se sirven del mismo dominio y no añaden
    # una conexión nueva. La versión anterior marcaba `live.js` porque comparaba
    # el `src` en crudo contra el dominio — pero es relativo, así que resolvía a
    # la propia web y lo contaba como de terceros.
    bloqueantes = 0
    for u, p in paginas.items():
        for s in p.scripts_externos:
            absoluto = urllib.parse.urljoin(u, s)
            if absoluto.startswith(sitio):
                continue
            if s in p.scripts_diferidos:
                continue
            bloqueantes += 1
    if bloqueantes:
        ojo("scripts de terceros que bloquean el render", f"{bloqueantes}")
    else:
        bien("ningún script de terceros bloqueando el render")

    # ---- lo que no se puede comprobar desde aquí ---------------------- #
    print("\n### A mano (no se puede comprobar desde aquí)\n")
    a_mano("Google Search Console + GA4 conectados")
    a_mano("sitemap enviado a GSC y a Bing")
    a_mano("Core Web Vitals medidas con datos reales (aquí solo se estima el peso)")
    a_mano("palabras clave de la competencia y de volumen alto / dificultad baja")
    a_mano("enlaces entrantes: menciones de marca, listas «best X», hilos de Reddit")
    a_mano("respuestas a «People also ask» y FAQ en las consultas reales")
    a_mano("`dateModified` actualizado de verdad al refrescar cada página")

    # ---- resumen ------------------------------------------------------- #
    print("\n" + "=" * 72)
    print(f"RESUMEN · {ok_count} correctas · {len(fallos)} fallos · "
          f"{len(avisos)} avisos · {len(manual)} a mano")
    print("=" * 72)
    if fallos:
        print("\nFallos, por orden de gravedad:")
        for f in fallos:
            print(f"  · {f}")
    if avisos:
        print("\nAvisos (no rompen nada, pero se pueden mejorar):")
        for a in avisos:
            print(f"  · {a}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Auditoría SEO de la web publicada.")
    ap.add_argument("--sitio", default="https://set4jeta.github.io/JetaDirectaBot/")
    ap.add_argument("--local", action="store_true",
                    help="audita http://127.0.0.1:8899 en vez de producción")
    args = ap.parse_args()

    auditar("http://127.0.0.1:8899/" if args.local else args.sitio)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())

# 03 · SEO técnico: la lista que sí mueve la aguja

Patrick Stox (Ahrefs) reduce el SEO técnico a cinco cosas (2026-04-02). Todo lo
demás que venden las auditorías automáticas son "minor things, not major issues":

> Focus on **indexing, redirects, internal linking, hreflang issues, schema** (if
> it gets you SERP features).

Este archivo es esa lista aplicada a `web/`, con el estado real medido.

## 1. Indexación

El requisito previo a todo. Una página que no está indexada no rankea, no sale en
AI Overviews y no se puede citar.

**Estado actual de esta web: catastrófico, y no por SEO.**

El sitio no está publicado. `git status` da `?? web/` — los 82 ficheros nunca se
han subido. Y GitHub Pages está en modo "deploy from a branch", que sirve la raíz
del repositorio a través de Jekyll. Resultado medido:

| URL | Respuesta |
|---|---|
| `set4jeta.github.io/JetaDirectaBot/` | 200, pero sirve el README |
| `.../ligas.html` | **404** |
| `.../sitemap.xml` | **404** |
| `.../robots.txt` | **404** |

El *workflow* `.github/workflows/publicar-web.yml` arregla la mitad (sube solo
`web/` como artefacto, así `web/index.html` pasa a ser la raíz). La otra mitad
necesita el `push` y cambiar la fuente de Pages a "GitHub Actions".

Recordatorio de Illyes sobre el umbral: si una página está justo por debajo del
umbral de calidad, Google **no la indexa**, y reenviarla en Search Console solo
le da vida temporal. La solución es contenido propio, no reenviar.

### `.nojekyll`

El *workflow* hace `touch web/.nojekyll`. Sin ese archivo, Jekyll procesa el sitio
e **ignora todo directorio que empiece por `_`**, además de intentar interpretar
plantillas. En un sitio ya generado eso solo puede romper cosas.

## 2. Redirecciones

No hay ninguna y no debería haber ninguna: es un sitio nuevo, sin historial de
URLs. La única regla a mantener: **una URL publicada no se cambia**. Si alguna
página de liga cambia de nombre después de publicar, hace falta redirección, y
GitHub Pages no permite redirecciones de servidor — habría que usar un
`<meta http-equiv="refresh">`, que es peor. Así que **las rutas se deciden ahora**.

Decisión a tomar antes de publicar: las páginas de liga son
`liga-lec.html`, `liga-lck.html`… Si algún día se quiere `/lec/`, hay que hacerlo
antes del primer `push`, no después.

## 3. Enlazado interno

Es una de las tres señales "ABC" (Anchors) del cubo de relevancia, así que no es
navegación: es ranking.

**Arquitectura actual:** menú de 5 entradas en las 26 páginas, más `ligas.html`
como hub que enlaza a las 20 páginas de liga. Cualquier página de liga está a dos
saltos de cualquier otra.

Esto está bien pensado y hay una razón documentada en `web_layout.py` para no
meter las 20 ligas en el menú global: un menú de 25 entradas repetido 25 veces
diluye el enlace. Es correcto.

**Lo que falta:** enlaces *laterales* entre páginas de liga relacionadas. La página
de la LEC debería enlazar a la LCK y la LTA con texto tipo "compara con la LCK",
porque quien mira el elo de la LEC probablemente mire otra liga después. Ahora
mismo el único camino es volver al hub.

### El *anchor text* importa

Hay que evitar "aquí", "más información", "ver". El texto del enlace le dice a
Google de qué es la página destino. `<a href="liga-lck.html">clasificación de la
LCK</a>` es señal; `<a href="liga-lck.html">ver</a>` no es nada.

## 4. `hreflang`: aquí es donde la web va a cambiar

**Estado actual: 26 de 26 páginas con `<html lang="es">` y cero `hreflang`.**

El comentario en `web_seo.py` es correcto en su contexto:

> `og:locale` es `es_ES` porque la web está en español. […] declarar `hreflang` a
> una URL que no existe es un error de rastreo, no un detalle.

Eso es verdad y hay que respetarlo: **primero se crean las páginas en inglés,
después se declara el `hreflang`**. Nunca al revés.

### Las reglas de `hreflang` que se rompen siempre

1. **Es bidireccional.** Si `/en/index.html` declara que `/index.html` es su
   versión española, la española tiene que declarar la inglesa. Sin
   reciprocidad, Google ignora la anotación entera.
2. **Cada página se declara a sí misma.** El conjunto de `hreflang` de una página
   incluye una entrada para esa misma página.
3. **URLs absolutas.** Relativas no valen en `hreflang`.
4. **`x-default`** para quien no encaja en ningún idioma declarado. Debe apuntar a
   la versión que se sirve por defecto.
5. **Códigos correctos.** `es` y `en` (ISO 639-1). Si algún día hay variantes:
   `en-US`, `es-ES`, `es-MX`. El código de país **solo** puede ir después del de
   idioma; `hreflang="us"` no existe.
6. **Cada versión se enlaza y se canonicaliza a sí misma.** El canónico de
   `/en/index.html` es `/en/index.html`, no la española. Un canónico cruzado
   borra la versión inglesa del índice.

### El canónico es una pista, no una orden

Natzir Turrado (`@natzir9`, 2026-09-01):

> Exhibit num 4,859,102 that **canonicals are just a hint**.

Es literal: Google puede ignorar el `rel="canonical"` y elegir otra URL como
canónica si le parece mejor candidata. Consecuencias para nosotros:

- No basta con declarar el canónico: hay que **no crear duplicados**. Que
  `/`, `/index.html`, y `/?utm=…` sean la misma página con tres URLs es pedirle
  a Google que elija, y elige mal.
- Con la versión inglesa, si la española es una traducción muy próxima, Google
  puede plegar una sobre otra. La defensa es que **el contenido sea de verdad
  distinto** (preguntas distintas en la FAQ, no traducción literal), más el
  `hreflang` recíproco.
- En Search Console, "Canónica seleccionada por Google" distinta de la declarada
  es el aviso de que esto está pasando. Hay que mirarlo tras publicar.

Forma final que va a tener cada página, con el inglés en la raíz (ver
`04-estrategia-ingles.md` para el por qué):

```html
<link rel="alternate" hreflang="en" href="https://…/index.html">
<link rel="alternate" hreflang="es" href="https://…/es/index.html">
<link rel="alternate" hreflang="x-default" href="https://…/index.html">
```

### Estructura de URL: subcarpeta

Tres opciones y por qué se elige la tercera:

| Opción | Ejemplo | Veredicto |
|---|---|---|
| Dominio por idioma | `jetadirectabot.es` | Dos dominios que ganar autoridad por separado. No. |
| Subdominio | `es.jetadirectabot.com` | Google lo trata casi como sitio aparte. No. |
| **Subcarpeta** | `jetadirectabot.com/es/` | **Sí.** Toda la autoridad en un dominio. |

Con GitHub Pages la subcarpeta es además lo único fácil de hacer.

## 5. Schema: solo lo que da función en el SERP
La coletilla de Stox — *"if it gets you SERP features"* — es la parte que la gente
ignora. El JSON-LD **no es factor de ranking**. Vale si produce algo visible.

Ya está implementado en `web_seo.py`: `Organization`, `WebSite`,
`SoftwareApplication`, `FAQPage`, `Article`, `BreadcrumbList`, `ItemList`. La
implementación tiene un detalle bien resuelto que merece quedar apuntado: el JSON
se serializa a mano en lugar de con `json.dumps` **para escapar `</script>`**,
porque los nombres de jugador y equipo vienen de datos remotos y meterlos crudos
en un `<script>` es una inyección esperando a ocurrir. Ningún serializador de JSON
escapa eso, porque para JSON no es un problema.

Lo que **no** hay que hacer:
- `AggregateRating` inventado. Es motivo de acción manual y es la primera cosa que
  Google verifica en un `SoftwareApplication`. Sin valoraciones reales, no va.
- `FAQPage` esperando el desplegable en el SERP: Google lo retiró en 2023 salvo
  para sitios oficiales de salud y gobierno. Se mantiene porque los LLM lo leen y
  ayuda a la extracción de respuestas, no por el SERP.

## 6. `llms.txt`: no

Decisión tomada, con dos fuentes.

Glenn Gabe (2026-09-02) lo probó forzándolo como sitemap en Search Console: Google
**no pudo descargar el archivo** y el tipo salió como `unknown`.

> llms.txt will not do anything for you in Search, even if you try to force it
> into GSC.

Patrick Stox (2026-08-10) va al fondo del diseño:

> having markdown on a different URL is not a good way to do it. **Content
> negotiation, putting the markdown on the same URL** is what will win in the end,
> and I'm sure we'll all have to clean up the LLMs.txt nonsense years later.

**No se crea `llms.txt`.** Es trabajo sin retorno demostrado y probablemente
deuda técnica.

## 7. Core Web Vitals

Ya está bien y no hay que tocarlo. HTML estático, un solo CSS, sin JavaScript.

El único riesgo es AdSense: los anuncios se inyectan después de pintar y mueven el
contenido (CLS). Está mitigado con `min-height` en `.anuncio`. **Cuando se active
AdSense de verdad hay que volver a medir el CLS**, porque los anuncios automáticos
pueden colocarse en sitios que no tienen reservado el hueco.

Y la advertencia de Illyes para no invertir aquí más de lo necesario: lavar el
coche cien veces no evita quedarse tirado en la autopista.

## 8. `robots.txt` y `sitemap.xml`

Ambos se generan desde la lista de páginas real, nunca a mano. Eso elimina el
fallo clásico de añadir una página y olvidar el sitemap.

Comprobaciones al publicar:
- El sitemap **no** incluye el 404 (marcado `indexable: False`).
- `robots.txt` apunta al sitemap con URL absoluta.
- El sitemap usa la URL canónica exacta, con la misma barra final. `/index.html`
  y `/` son URLs distintas para un rastreador.

Cuando exista la versión inglesa, el sitemap tiene que crecer al doble y **cada
entrada debe llevar sus `xhtml:link` de `hreflang`** o, alternativamente, dejar el
`hreflang` solo en el `<head>`. Las dos formas valen; mezclarlas a medias es lo
que da errores en Search Console. Decisión: **solo en el `<head>`**, que es más
simple de generar y de verificar.

## 9. Search Console es la única fuente fiable de posiciones

Contexto de agosto de 2026: Google metió parámetros `goto` en los enlaces del SERP
para rastrear quién extrae resultados. Gabe documentó que afectó a Sistrix,
Ahrefs, Semrush, SE Ranking, SeoClarity y DataForSEO. Y ya se ven botones
"Continue" retardados a propósito: *"They want humans as much as possible."*

Los datos de posición de terceros van a ser menos fiables una temporada.
**Primera acción tras publicar: verificar el sitio en Search Console.** Es gratis,
es dato de primera mano, y es lo único que permite ver las consultas reales.

Como nota de contexto sobre lo cerrada que está la puerta: Natzir Turrado publicó
tres formas de sacar las URLs limpias de los enlaces `/goto` cifrados —cambiar el
`Accept-Language` a un idioma distinto del de los resultados para que aparezca el
enlace "Traducir esta página" con la URL limpia (2026-08-27, 361 likes y 330
guardados, el post más guardado de todo el barrido en español), y usar Brave, que
los eliminó (2026-08-31). Sirve para entender que esto es una carrera activa, no
un cambio estable. **No lo vamos a usar**: no necesitamos raspar el SERP de nadie,
necesitamos nuestros propios datos, y esos están en Search Console.

Tomek Rudzki (2026-06-11) tiene un montaje que merece copiar cuando haya datos:
Search Console → BigQuery → consultas en lenguaje natural vía MCP, para preguntar
cosas como *"which pages rank well but barely get clicks?"*.

# 01 · Cómo rankea Google de verdad

Fuente principal: los documentos internos que salieron en el juicio antimonopolio
de Estados Unidos, resumidos por Cyrus Shepard (`@CyrusShepard`, 2026-08-17, 278
likes y **362 guardados** — el post con más guardados de todo el barrido, lo que
en X significa "esto lo quiero releer").

## Los tres grandes cubos de ranking

### 1. Topicality (relevancia): las señales «ABC»

Cuánto responde la página a la consulta. Se determina sobre todo con tres cosas:

- **A**nchors — los enlaces que apuntan a la página, y **con qué texto**.
- **B**ody — el texto de la propia página.
- **C**licks — señales de clic de usuarios para determinar relevancia.

Que el *anchor text* siga siendo una de las tres patas es importante para esta
web: significa que el enlazado interno no es relleno. Si todas las páginas de
liga se enlazan desde `ligas.html` con el texto "LEC", "LCK", "LTA Norte", ese
texto es señal de relevancia para esas consultas.

### 2. Navboost: 13 meses de clics

Un sistema de *re-ranking* que usa **13 meses de datos de clic** para ajustar
resultados. Mira tres cosas: primer clic, clic largo (*long click*) y último
clic. Un usuario que entra, se queda y no vuelve a buscar es la señal buena.

Consecuencia práctica: una página que rankea y hace que la gente vuelva atrás
inmediatamente pierde posiciones. Para nosotros esto significa que la tabla de
elo tiene que estar **arriba y visible sin scroll**, no después de tres párrafos
de introducción. Quien busca "elo de los mid de la LEC" quiere la tabla, no una
explicación de lo que es la LEC.

Y algo más incómodo: **Navboost necesita clics para existir**. Una web nueva no
tiene datos de clic, así que arranca sin esa señal. Es una de las razones por las
que el tráfico tarda: no es que Google no vea el sitio, es que no tiene historial
de comportamiento con el que ajustar.

### 3. Quality (Q\*): autoridad del sitio

Shepard lo llama "una de las señales más importantes de Google", basada en
**autoridad del sitio** más ajustes de calidad (Panda, Helpful Content, spam).

Es señal de **sitio**, no de página. Una página excelente en un dominio sin
autoridad rankea peor que una página mediocre en un dominio con ella. Esto es
justo el problema de arrancar en `set4jeta.github.io/JetaDirectaBot/`: es un
subdirectorio de un dominio compartido por millones de proyectos, y no hereda
autoridad de él.

Shepard cierra con una advertencia dirigida a sí mismo:

> SEOs—including yours truly—often get distracted by shiny things.

## El umbral de indexación

Gary Illyes (`@methode`, Google, 2021-07-28) respondiendo por qué una página
aparece y desaparece del índice:

> the page is likely very close to, but still above the quality threshold below
> which Google doesn't index pages.

Y en otro post: enviar la URL a mano en Search Console le da "vida temporal",
pero se cae otra vez. O sea: **existe un umbral de calidad por debajo del cual
Google simplemente no indexa**, y forzar la indexación no lo sube. Si una página
de liga con datos escasos no se indexa, la solución no es reenviarla: es que
tenga más contenido propio.

Esto es directamente relevante para las 20 páginas de liga. Si son 20 plantillas
idénticas con la tabla cambiada, van a estar rozando ese umbral. Necesitan algo
que solo esa liga tenga.

## Core Web Vitals: necesario, no suficiente

Illyes otra vez (2021-07-24, 191 likes), con una comparación que resume el tema:

> putting work in core web vitals doesn't mean that the site can't lose rankings
> over time. I also washed my car hundreds of times and it still left me standing
> on the highway.

Traducción operativa: las CWV son un requisito de higiene, no una palanca de
crecimiento. Nuestra web es HTML estático sin JavaScript, así que las CWV van a
salir bien casi por accidente. **No hay que invertir más tiempo ahí.** Lo único
que puede romperlas es AdSense (por eso el hueco del anuncio lleva `min-height`,
para que no haya salto de layout).

## Prioridades técnicas según quien las mide

Patrick Stox (Ahrefs, `@patrickstox`, 2026-04-02), sobre qué mueve la aguja de
verdad:

> Focus on indexing, redirects, internal linking, hreflang issues, schema (if it
> gets you SERP features). These are valuable things. Things that will move the
> needle.

Ese "if it gets you SERP features" sobre schema es una corrección importante a la
creencia común. El JSON-LD no es un factor de ranking: sirve si te da una función
visible en el resultado (estrellas, FAQ desplegable, migas de pan). Marcar cosas
que no producen ninguna función es trabajo sin retorno.

Nuestros schemas actuales y para qué sirven de verdad:

| Schema | ¿Da función en el SERP? | Veredicto |
|---|---|---|
| `FAQPage` | Ya casi nunca desde 2023 | Mantenerlo, pero sin esperar nada |
| `BreadcrumbList` | **Sí**, cambia la URL por la ruta | Mantener, es de los pocos que rinde |
| `SoftwareApplication` | Con `AggregateRating`, estrellas | Mantener; sin valoraciones reales no pongas rating |
| `Organization` | Alimenta el panel de conocimiento | Mantener |
| `WebSite` | `SearchAction` (sitelinks searchbox) | Solo si hay buscador interno de verdad |
| `Article` | Fecha visible en algunos casos | Mantener |

## El contenido «con esfuerzo» como señal

Shepard (2026-08-13, 74/61): *Content Effort - The Google Ranking Signal Nobody
Talks About*.

> Google has been measuring and scoring "subjective" factors like EFFORT for
> nearly 20 years, and we've barely noticed. In the age of low-effort, scaled
> content, knowing the difference is important, and we CAN optimize for it.

Cómo se demuestra esfuerzo en nuestro caso, concretamente: datos que nadie más
tiene juntos (elo actual + rol + equipo + liga, actualizado), imágenes propias de
jugadores y logos, y tablas que salen de la API de Riot en vez de copiarse de
otra web. Eso es esfuerzo *medible*, no adjetivos.

## Lo que NO es una señal

- **No hay bonus por *byline*** si no le sirve al lector (Sullivan, 2024-01-09).
- **`llms.txt` no hace nada en Search.** Glenn Gabe (`@glenngabe`, 2026-09-02) lo
  probó: Google no pudo ni descargar el archivo cuando lo forzó como sitemap, y
  el tipo salió como "unknown". Patrick Stox es más directo: *"the LLMs.txt
  nonsense"* que habrá que limpiar años después, y defiende negociación de
  contenido en la **misma URL** en vez de una URL distinta con markdown.
  **Decisión para esta web: no crear `llms.txt`.**
- **Minar las "otras preguntas" (PAA) y pegarlas todas al final.** Gabe
  (2026-09-01): eso es lo que castigó el Helpful Content Update, y la versión
  moderna con *query fan-outs* ya está siendo golpeada por las actualizaciones de
  spam. Nuestra FAQ tiene que responder preguntas que un usuario real haría, no
  todas las que devuelva una herramienta.

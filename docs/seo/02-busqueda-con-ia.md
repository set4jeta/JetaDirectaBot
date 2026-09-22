# 02 · Búsqueda con IA: el cambio que decide si esta web tiene sentido

Este es el archivo más importante de la carpeta. Todo lo demás son detalles
técnicos; esto es el suelo moviéndose.

## El dato que hay que interiorizar: 68 % de búsquedas sin clic

Rand Fishkin (`@randfish`, SparkToro, 2026-06-09, con datos de Similarweb):

> From Jan-April of this year, **68.01 % of Google searches** in Similarweb's
> mobile+desktop panel **ended without a click**. That's 12.5 % growth from two
> years ago; the fastest we've seen the zero-click search trend rise in the last
> decade.

Y la cifra corregida que publicó ocho días después, porque la primera tenía un
error de cálculo:

> For every 1,000 Google searches, **232 clicks go to the open web**.

**232 de cada 1000.** No 680. El resto se queda en Google (AI Overviews, paneles,
propiedades de Google) o se abandona.

Fishkin también midió el desglose por país (2026-06-17). Reino Unido tiene el
cero-clic **más alto**; Alemania el **más bajo**. España no estaba en la muestra
de seis países, pero el patrón general es que los mercados anglosajones son los
que más tráfico retienen — algo que hay que tener en cuenta al orientar la web al
inglés: más volumen de búsqueda, pero también más cero-clic.

Y el peor dato para quien vive de tráfico orgánico, de Patrick Stox
(`@patrickstox`, Ahrefs, 2026-06-03):

> if AI search was 100 % of search traffic, websites would have **5 % of current
> traffic levels**. People aren't clicking there.

## Lo que esto significa para JetaDirectaBot

No es "hay que hacer SEO mejor". Es que **la estrategia de "escribo contenido y
Google me manda gente" está en declive estructural**, y hay que diseñar para eso
desde el principio en vez de descubrirlo en un año.

Fishkin lo dice sin anestesia (2026-05-25, 48/33):

> Ignore traffic. Make inimitable products. Shift your priorities away from
> "great content" on your own site and toward "great marketing" on the platforms
> where your audience pays attention. **Influence is the new traffic.**

Aplicado a este proyecto, y esto es una conclusión mía sobre el proyecto, no una
cita: la web **no es el producto**. El producto es el bot dentro de Discord. La
web tiene dos trabajos, en este orden:

1. **Ser la página de aterrizaje que convierte** a quien ya oyó hablar del bot
   (por Discord, por un amigo, por un post) en una instalación. Esto no depende
   de SEO en absoluto y es donde está el retorno inmediato.
2. **Capturar la búsqueda de intención alta que sigue dando clic**: "lol discord
   bot pro player alerts", "bot para saber cuándo juega Caps". Consultas de
   herramienta, no informativas. Estas son las que sobreviven al cero-clic,
   porque el AI Overview no puede *instalar* el bot por ti.

Fishkin, sobre por qué no hay que rendirse (2026-05-25):

> For anyone who thinks the Zero Click Web is inevitable... It's not. Big tech
> platforms decide whether to give traffic. Judge accordingly.

Y Cyrus Shepard citando a Google (2026-07-14): *"Google says organic traffic to
your website is alive and well"* — con el tono de quien no se lo cree.

## Qué consultas sí siguen dando clic

Aleyda Solís (`@aleyda`, 2026-09-03), citándose a sí misma en un recurso de
Kinsta sobre afiliación en la era de la IA:

> The affiliate sites continuing to grow for non-branded queries despite the rise
> of AI Overviews share a common pattern: they're **not relying on shallow
> informational content that can be easily summarized**. They're winning where
> users still need help making a confident purchase.

Las cuatro cosas que menciona como defensa: **especialización vertical**,
**evidencia de primera mano**, y **formatos de alta confianza para mitad y fondo
de embudo** (MOFU/BOFU).

Traducido a nuestras páginas, esto reordena las prioridades:

| Página | ¿Resumible por un AI Overview? | Prioridad real |
|---|---|---|
| "Qué es la LEC" (si existiera) | Totalmente | **No hacerla nunca** |
| Tabla de elo actual de la LEC | No: es un dato que cambia | Alta |
| "Cómo son los avisos" (con capturas) | No: es evidencia de primera mano | Alta |
| Comparativa con otros bots | Parcialmente, pero es decisión de compra (BOFU) | **La más alta** |
| Página de liga sin datos propios | Sí | Reforzar o quitar |

La comparativa (`alternativas-bots-lol-discord.html`) es la página más valiosa del
sitio bajo este marco, y ahora mismo está tratada como una más. Quien busca
"alternativas a X bot" está a un paso de instalar algo.

## Query fan-out: cómo los LLM investigan una marca

Esto es lo más accionable de todo el barrido. María José Cachón analizó **189
prompts de marca en 723 ejecuciones de GPT-5.5**, identificando 1.797 subconsultas
(vía `@aleyda`, 2026-08-26):

- **10,3 subconsultas distintas** por prompt, a lo largo de 4 ejecuciones
- **93,4 %** incluían el nombre de la marca
- **30,2 %** usaban `site:`
- **23,8 %** usaban comillas de coincidencia exacta
- **10,1 %** investigaban **reputación y confianza**
- Solo **0,8 %** mencionaban competidores

La secuencia típica: *pregunta amplia → estrecha a un dominio → verifica
afirmaciones exactas → reformula si hace falta.*

Aleyda extrae la lista de lo que hay que tener por eso: **indexabilidad,
información corporativa clara, consistencia, frescura, perfiles oficiales,
reputación.**

MJ Cachón, autora del estudio, lo resume en una frase que conviene tener pegada
en la pared (`@mjcachon`, 2026-08-26):

> Tu marca en ChatGPT no depende del prompt del usuario…. Depende más de las
> consultas que hace el modelo a partir de dicho prompt: las Query Fan-out.

O sea: no se optimiza para lo que la gente pregunta, se optimiza para lo que el
modelo busca después de que la gente pregunte. Y lo que busca, según su propio
estudio, es el nombre exacto, el `site:` del dominio, y la reputación.

Consecuencias directas y concretas para esta web:

1. **`site:` en el 30 % de las subconsultas.** Si el sitio está en un
   subdirectorio (`set4jeta.github.io/JetaDirectaBot/`), `site:jetadirectabot.com`
   no devuelve nada. Un dominio propio deja de ser cosmético: es lo que hace que
   el 30 % de las subconsultas de un LLM sobre el bot encuentren algo.
2. **Coincidencia exacta en el 23,8 %.** El nombre tiene que aparecer escrito
   igual en todas partes: web, Discord, GitHub, X. "JetaDirectaBot" siempre igual,
   nunca "Jeta Directa Bot" ni "JetaDirecta".
3. **Reputación en el 10,1 %.** Hace falta que exista algo *fuera* de nuestro
   dominio que hable del bot. Un `README` de GitHub, un listado en un directorio
   de bots de Discord, un post. Sin eso, la subconsulta de reputación no
   encuentra nada y el LLM no recomienda.
4. **Información corporativa clara.** Quién está detrás, cómo contactar. La página
   legal ya lo cubre en parte, pero necesita el contacto real.

## Fan-out visible en Search Console

Lily Ray (`@lilyraynyc`, 2026-08-31, 281/360) encontró cómo verlas:

> I'm pretty confident these are ChatGPT fan-out queries in Google Search
> Console. You can use this regex filter to check your own sites:
> `(?i)(site:.*official|official.*site:)`
> […] many impressions, **0 clicks**, and a whole lot of queries that look
> exactly like ChatGPT fan-outs in GSC.

Variante para sitios YMYL (2026-09-01): `site:.*\.gov|\.gov.*site:` — le dio 14K
impresiones en 108 consultas, 0 clics.

Y la conclusión que saca (2026-09-01), que va contra lo que todo el mundo asume:

> if this theory is true, it would imply that **Google is still part of the mix
> of search engines that ChatGPT uses** when doing live web search. It's not just
> Bing.

**Apuntado para cuando la web esté en Search Console**: filtrar consultas con esa
regex es la forma de saber si algún LLM está investigando el bot. Impresiones sin
clics dejan de ser un problema y pasan a ser un indicador.

## El 95 % usa ChatGPT gratis, y eso lo cambia todo

Shepard (2026-08-13, 79/75), citando datos de Suganthan:

> ChatGPT *already knows* what brands it's going to recommend **before it
> searches** […] Even more relevant when you learn **95 % of users use the "free"
> version of ChatGPT, which barely searches at all**.

Gabe lo confirma desde el trabajo con clientes (2026-09-01):

> the results can be very very different between the free version and the paid
> version. And most people are on the free version.

Consecuencia dura: para la mayoría de usuarios de ChatGPT, **no hay búsqueda en
vivo**. Lo que importa es si el modelo ya conoce el bot de su entrenamiento. Y a
los datos de entrenamiento no se entra optimizando el `<head>`: se entra estando
mencionado en sitios que se rastrean masivamente (GitHub, Reddit, listados,
foros). Esto refuerza el punto 3 de la lista de fan-out.

## Volatilidad de las citas en IA

Shepard (2026-07-15, 56/13) probó la misma consulta en cuatro contextos:

> Confident you rank in Google AI answers + citations? These vary SO much, even
> for the exact same query. Below: • Logged in • Incognito, USA • Incognito,
> Brazil • Incognito, Ukraine. Completely different results based on
> personalization, location, language, and LLM fuzziness.

O sea: **no existe "salgo en el AI Overview"**. Hay una distribución. Cualquier
comprobación puntual es anécdota. No merece la pena perseguir esto.

## GEO / AEO: ¿es otra disciplina?

Shepard (2026-08-04, 65/38), y esta es la respuesta corta que ahorra mucho tiempo:

> **These SEO Strategies Drive 90 % of Your AI Visibility.** Asking if GEO/SEO
> are the same isn't the right question, it's seeing where they overlap. If you
> tweak traditional SEO, you can use the same strategies+tactics for • AI
> Inclusion • AI Citations • AI Recommendations.

**Decisión: no hay una estrategia GEO aparte.** El 90 % es el SEO técnico y de
contenido de siempre. Lo que se añade encima: indexabilidad impecable, datos
frescos con fecha visible, nombre consistente, y presencia fuera del dominio
propio.

Dato de calendario que conviene conocer: Google **actualizó su propia guía de
optimización para IA mencionando expresamente GEO/AEO** (MJ Cachón, 2026-08-01).
Que Google use los términos significa que dejó de ser jerga de consultoría, pero
no cambia la conclusión de Shepard: el 90 % sigue siendo SEO normal.

Aleyda mantiene un *3 Layer Framework to Measure AI Search Presence, Readiness
and Business Impact* con ejemplos para SaaS, ecommerce y finanzas (2026-08-26).
Pendiente de mirar cuando haya tráfico que medir; ahora mismo no hay nada que
meter en el marco.

### Lo difícil no es optimizar: es medir

Encuesta de Aleyda con 111 respuestas (#SEOFOMO State of AI Search Optimization,
2026-08-24). El mayor problema **no es presupuesto ni convencer a nadie**:

- **60** no consiguen medir con fiabilidad la visibilidad en búsqueda con IA
- **44** no entienden qué la influye de verdad
- **44** no logran conectar visibilidad con tráfico, conversiones e ingresos
- **36** señalan falta de datos fiables

Esto es un permiso para no obsesionarse. Si profesionales que cobran por esto no
saben medirlo, nosotros tampoco vamos a saberlo, y perseguir métricas de IA con
herramientas de pago sería gastar dinero en ruido. **La métrica que sí se puede
medir en este proyecto es la única que importa: instalaciones del bot.** Discord
las da gratis.

### Los modelos cambian bajo los pies

MJ Cachón (2026-08-10): ChatGPT cambió su modelo por defecto el 6 de agosto, de
GPT-5.5 a GPT-5.6, y *"tus métricas de visibilidad en IA han podido verse
afectadas"*. Aleyda lo cuantifica (2026-08-22): tras ese cambio **Reddit, arXiv y
YouTube cayeron en citas**, y subieron competidores, publicaciones especializadas
y sitios de gobierno — con comportamiento consistente en varios países e idiomas:
*"in the US in English, Spain or Argentina in Spanish, France in French"*, y en
verticales de ecommerce, fintech, SaaS, gaming y fitness.

Su conclusión, que es la misma que la de Cachón (2026-08-18: *"Exprimir tácticas
cortoplacistas no es el camino, tener una estrategia sí lo es"*):

> Another reminder **not to make any single platform your AI visibility
> strategy**.

Y el recordatorio de Cachón de que lo viejo sigue vivo (2026-08-18): *"Aunque la
IA está en nuestro día a día más que nunca, los cambios de algoritmo siguen
sucediendo en busca de potenciar la calidad, que no se nos olvide"*.

### ChatGPT reescribió su buscador

Aleyda (2026-08-21), citando investigación de Suganthan:

> Between 16th and 20th August, ChatGPT's search tool call went **from JSON to a
> compact query language with freshness windows, domain targeting and separate
> verticals** for products, places, images and widgets.

Dos cosas de ahí que sí son accionables: **ventanas de frescura** (la fecha de
actualización visible en la página importa, y nuestras tablas de elo cambian a
diario — es una ventaja real que hay que exponer con `dateModified`) y
**segmentación por dominio** (otra razón para tener dominio propio).

## Contenido a escala: el camino rápido a la penalización

Lily Ray (2026-08-31): *"Scaled/programmatic content... worked for a long time
until the Aug spam update 👀"*.

Gabe analizó cuatro casos de la **actualización de spam de agosto de 2026** —
completada en 3 días según Aleyda (2026-08-21). Las políticas aplicadas:
**`scaled content abuse`, `thin affiliation`, `malicious functionality`**. Y su
advertencia específica:

> Scaling AI-generated content in a YMYL category = a bad combination that won't
> end well for the site owner.

**Esto nos afecta directamente.** Tenemos 20 páginas de liga generadas por
plantilla. Eso es contenido programático. La diferencia entre "programático
legítimo" y `scaled content abuse` es si cada página aporta algo que las otras no:

- ✅ Datos reales y distintos por liga (clasificación, jugadores, elo actual)
- ✅ Imágenes propias por equipo y jugador
- ⚠️ Texto de introducción idéntico salvo el nombre de la liga ← **esto es el riesgo**
- ⚠️ La misma FAQ en las 20 páginas ← **también**

No estamos en YMYL (esports no es salud ni finanzas), lo que baja el riesgo. Pero
la parte de texto duplicado hay que arreglarla antes de publicar.

## Abuso de reputación del sitio

Shepard (2026-08-29, 59/18) explicando la política, que conviene conocer para no
pisarla sin querer:

> "Site Reputation Abuse" is, broadly, when a strong site publishes (monetized)
> third-party content that probably wouldn't rank on its own, but rides the
> coattails of the strong site in order to make money.

Google dejó caer algunas penalizaciones en Europa por regulación de la UE, pero
la política sigue. **Nota para nosotros: si algún día se acepta contenido de
terceros o enlaces patrocinados en la web, ahí empieza este riesgo.**

## Google contra los rastreadores

Contexto de finales de agosto de 2026, que explica por qué las herramientas de
SEO fallan últimamente. Gabe (2026-08-31) documentó el asunto de los enlaces
`goto`: Sistrix, Ahrefs, Semrush, SE Ranking, SeoClarity y DataForSEO afectados.

> I think this is just Google wanting to track *who* is scraping (and possibly
> for legal reasons).

Y vio botones "Continue" en gris unos segundos antes de activarse: *"They want
humans as much as possible."* Fishkin es menos diplomático (2026-07-22): llama a
lo de Google *"disgusting betrayal"* y agradece a SerpApi por defenderse.

**Implicación práctica:** los datos de posiciones de herramientas de terceros van
a ser menos fiables una temporada. **Search Console es la única fuente de verdad**
para esta web. Es gratis y es la primera cosa que hay que conectar tras publicar.

## Publishers considerando salir de Google

Shepard (2026-07-23 y 2026-07-10): Reddit ha discutido cortar el acceso de Google
a su contenido para uso de IA; otros grandes editores preparan "la opción nuclear"
de salirse de Google del todo.

> There's little incentive for them to remain.

Contexto, no acción. Pero explica por qué las citas de Reddit en ChatGPT cayeron
(Aleyda, 2026-08-23: *"Reddit, arXiv, YouTube have dropped in citations - Another
reminder not to make any single platform your AI visibility strategy"*).

**La lección aplicable: no apostar todo a una plataforma.** Ni a Google, ni a
ChatGPT, ni a Discord. Para este proyecto el canal más sólido no es ninguno de los
tres: es que el bot funcione y la gente lo recomiende en su servidor.

## Sobre el texto generado por IA

Shepard (2026-08-19, 108/53), citando un estudio de Ahrefs:

> Before folks get worked up about AI watermarking, important to note that Google
> doesn't seem to care all that much. In this Ahrefs study, **nearly 1/2 of
> top-ranking URLs contained at least 20-50 % AI text**. The very TOP results had
> slightly *less* AI text.

Y de Pew Research (2026-08-27): 35 % de las páginas publicadas después de ChatGPT
muestran edición o autoría de IA significativa.

Conclusión: **Google no penaliza texto de IA por ser de IA.** Penaliza contenido
de bajo esfuerzo y escalado sin valor. Son cosas distintas y se confunden todo el
tiempo. Que el texto de esta web esté generado no es el problema; que sea el mismo
texto 20 veces sí.

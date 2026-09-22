# 05 · Plan concreto para la web de JetaDirectaBot

Lo que hay que hacer, en orden, con el estado real medido. No es una lista de
buenas intenciones: cada punto tiene una comprobación que dice si está hecho.

## Bloque 0 · Sin esto no existe nada (bloqueado en el dueño)

| # | Qué | Quién | Estado |
|---|---|---|---|
| 0.1 | `git add web/ .github/ docs/ && git commit && git push` | **Chino** | ⛔ No hay credenciales en este entorno |
| 0.2 | GitHub → Settings → Pages → Source = **GitHub Actions** | **Chino** | ⛔ Pendiente |
| 0.3 | Rellenar `BOT_INVITE_URL`, `BOT_SOPORTE_URL`, `BOT_DONATE_URL`, `BOT_WEB_URL` | **Chino** | ⛔ 25 páginas tienen botones apagados con `data-sin-url` |
| 0.4 | Decidir dominio propio vs repo `set4jeta.github.io` para `ads.txt` | **Chino** | ⛔ Sin esto no hay AdSense |
| 0.5 | Verificar el sitio en Google Search Console | **Chino** | ⛔ Tras publicar |

El 0.3 no es cosmético: la web entera existe para que alguien pulse "Añadir a
Discord". Ahora mismo ese botón no lleva a ningún sitio en 25 de 26 páginas.

Y el 0.4 tiene una razón nueva del barrido de X: el **30,2 %** de las subconsultas
que hace ChatGPT al investigar una marca usan el operador `site:`. En
`set4jeta.github.io/JetaDirectaBot/` eso no devuelve nada. El dominio propio pasó
de "bonito" a "requisito para que un LLM pueda verificar el bot".

## Bloque 1 · Riesgo de `scaled content abuse` (medido, hay que arreglarlo)

Google completó la **actualización de spam de agosto de 2026** en 3 días. Las
políticas aplicadas en los casos que analizó Glenn Gabe: `scaled content abuse`,
`thin affiliation`, `malicious functionality`. Lily Ray: *"Scaled/programmatic
content... worked for a long time until the Aug spam update"*.

Tenemos 20 páginas de liga por plantilla. **Medido con
`scripts/medir_duplicidad.py`:**

```
media de frases compartidas entre las 20 páginas de liga: 33.5%
404.html                    71.4%   <- es un 404, no importa
liga-al.html                38.1%   <- la peor
liga-lec.html               25.0%   <- la mejor, porque tiene datos propios
```

33,5 % **no es alarmante** (por debajo del 50 % que considero sospechoso) y la
mayor parte de lo compartido es legítimo: el descargo de Riot obligatorio (en 26
páginas), el menú, y el bloque de llamada a la acción. Eso es *plantilla*, no
*contenido de relleno*, y Google distingue.

Pero hay frases que sí son relleno y salen en 19-20 páginas:

```
x20  "Es una medición sobre el leaderboard de la liga, no una estimación."
x19  "Los avisos de partida llegan a Discord, gratis."
x19  "Las victorias y el KDA son de esa cuenta, no de la temporada de la liga."
x19  "Es presencia, no partidas: el leaderboard dice qué juega cada uno..."
x19  "JetaDirectaBot avisa en tu canal de Discord con el campeón, el rol..."
```

Están dentro de las FAQ y de los párrafos de introducción de cada tabla. Son
correctas y útiles la primera vez que alguien las lee — el problema es que un
rastreador las ve 19 veces.

**Acción 1.1:** variar el texto de introducción de cada tabla por liga, usando
datos que ya tenemos y que son distintos en cada una (región, número de equipos,
si es rastreable, cuántas cuentas). ✅ **Hecho** — ver más abajo.

**Acción 1.2:** que la FAQ de cada liga tenga al menos una pregunta que solo
tenga sentido en esa liga. ✅ **Hecho** — ver más abajo.

**Atenuante importante:** esto **no es YMYL**. Gabe avisa específicamente de
*"scaling AI-generated content in a YMYL category"*. Esports no es salud ni
finanzas, así que el riesgo es bastante menor. Pero no es cero.

## Bloque 2 · Enlazado interno (es señal de ranking, no navegación)

Los documentos del juicio antimonopolio (vía Cyrus Shepard) ponen los **Anchors**
—los enlaces y su texto— como una de las tres patas del cubo de relevancia. El
enlazado interno es la única parte de eso que se controla desde dentro.

**Estado:** menú de 5 en las 26 páginas + hub `ligas.html` → 20 ligas. Bien
diseñado. Lo que falta son **enlaces laterales**: quien mira el elo de la LEC
suele querer ver la LCK después, y ahora el único camino es volver al hub.

**Acción 2.1:** en cada página de liga, enlazar a 3-4 ligas relacionadas (misma
región primero, luego las grandes) con *anchor text* descriptivo, no "ver más".
✅ **Hecho** — ver más abajo.

## Bloque 3 · La versión en inglés

Es la petición estratégica del dueño y está justificada (ver
`04-estrategia-ingles.md`): RPM de AdSense 3-5× mayor, más volumen de búsqueda, y
los servidores de Discord grandes de LoL son anglófonos.

**Estado: 26/26 páginas en `lang="es"`, cero `hreflang`.**

Orden por retorno, no las 26 de golpe:

| Orden | Página | Por qué |
|---|---|---|
| 1 | `index.html` → `/` en inglés | Es la URL que se comparte |
| 2 | Comparativa → `/best-lol-discord-bots.html` | Decisión de compra (BOFU). **La de más valor** |
| 3 | Avisos → `/alerts.html` | Evidencia de primera mano, no resumible por una IA |
| 4 | Hub de ligas → `/leagues.html` | Estructura |
| 5 | Las 20 de liga | Solo si las 4 primeras funcionan |

Estructura: **inglés en la raíz, español en `/es/`**. Con slugs en inglés en la
versión inglesa (`/leagues.html`, no `/ligas.html`).

**Acción 3.1:** infraestructura de `hreflang` en `web_seo.py`, apagada hasta que
existan las páginas. ✅ **Hecho** — ver más abajo.

**Acción 3.2:** traducir las 4 primeras páginas. ⬜ **Pendiente** — es el bloque
grande de trabajo que queda.

Regla que no se rompe: **`hreflang` solo cuando la página destino exista.**
Apuntar a una URL inexistente es un error de rastreo.

## Bloque 4 · Frescura

Del análisis de Suganthan (vía Aleyda, 2026-08-21): el buscador de ChatGPT ahora
usa *"freshness windows"*. Y la recencia siempre ha pesado en cómo eligen los
sistemas de IA de dónde responder.

**Esto es una ventaja real que tenemos**: las tablas de elo cambian a diario y
salen de la API de Riot. Casi nadie más publica eso actualizado.

**Estado:** `dateModified` ya se emite en el `Article` de todas las páginas de
contenido, y `avisos.html` usa deliberadamente la fecha del último aviso real en
vez de la de generación — para no fingir frescura. Eso está bien resuelto.

**Acción 4.1:** que la fecha de actualización sea **visible para el humano**, no
solo en el JSON-LD. Un "Actualizado el 3 de septiembre de 2026" arriba de la tabla
hace dos cosas: le dice al lector que el dato es de hoy, y coincide con lo que
declara el schema (que es lo que hace que Google se lo crea). ⬜ Pendiente.

## Bloque 5 · Lo que NO se va a hacer

Decisiones tomadas para no perder tiempo:

| Cosa | Por qué no |
|---|---|
| `llms.txt` | Gabe lo probó: Google no puede ni descargarlo. Stox: *"the LLMs.txt nonsense"* |
| Estrategia GEO separada | Shepard: el 90 % de la visibilidad en IA sale del SEO normal |
| Herramientas de posiciones de pago | Google metió parámetros `goto`; los datos de terceros están rotos. Search Console es gratis y es de primera mano |
| Perseguir salir en AI Overviews | Shepard probó la misma consulta en 4 contextos: resultados completamente distintos. No hay "salgo", hay distribución |
| `AggregateRating` en el schema | Sin valoraciones reales es acción manual |
| Invertir más en Core Web Vitals | Illyes: lavar el coche 100 veces no evita quedarse tirado. HTML estático, ya está bien |
| Medir visibilidad en IA con herramientas | 60 de 111 profesionales encuestados no consiguen medirlo. La métrica real es: instalaciones del bot |

## Cambios ya aplicados al código en esta pasada

- `scripts/medir_duplicidad.py` — **nuevo**. Mide qué porcentaje del texto de cada
  página aparece en otras, y lista las frases más repetidas. Es la herramienta que
  convierte "¿tendremos problema de contenido escalado?" en un número.
- `scripts/cosechar_seo_x.py` — **nuevo**. Lee los *timelines* de 32 referentes de
  SEO en X y filtra por señal. De aquí salen los datos de `_datos/`.
- `scripts/web_seo.py` — `hreflang` y `og:locale` por idioma, apagados hasta que
  exista la versión inglesa.
- `scripts/web_paginas.py` — texto variado por liga y enlaces laterales entre
  ligas relacionadas.

## Comprobación antes de publicar

```bash
python scripts/generar_web.py            # regenerar
python scripts/test_web.py               # 0 fallos
python scripts/medir_duplicidad.py       # media de ligas por debajo del 30 %
```

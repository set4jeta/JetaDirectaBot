# AGENTS.md — Continuidad y entrega de LoLProTrackr

Documento de mano para el **siguiente agente** (o para ti en un futuro). El
proyecto ya tiene mucha base hecha; este archivo fija lo que se hizo, por qué, y
hacia dónde va, para que cualquiera pueda retomar sin re-descubrirlo todo.

> Idioma: el proyecto y el usuario se comunican en español. El código y los
> comentarios internos están en español. Mantenlo así en lo que escribas.

---

## 1. Qué es y hacia dónde va

**LoLProTrackr** es un bot de Discord (nextcord) que avisa cuando un jugador
profesional de LoL entra a SoloQ. 20 ligas, ~1 000 jugadores, barrida con cadencia
variable según el presupuesto de ancho de banda (2-30 min; ver §8 de `DESPLIEGUE.md`).
Tiene capa gratuita + planes de pago (Pro 3,99 €, Elite 8,99 €, definidos en
`tracking/soloq/plans.py`).

**Dirección estratégica acordada con el usuario (sept 2026):** convertir la base
ya funcionante (bot + lógica de notificación + capacidad de leer la API de Riot)
en un activo que **genere tráfico y dinero**, con tres patas:

1. **Web esports "espectacular"** que enseñe los datos en vivo y atraiga
   audiencia (hecho: rediseño `web/` con tema Arena + `partners.html`).
2. **Patrocinios de marcas.** La web avisa en el momento exacto de la
   partida → intención en tiempo real → público cualificado. `partners.html` es la
   landing de alianzas (afiliado / embed patrocinado / socio principal).
3. **SEO automático + tráfico.** Sentar la web para que posicione (sitemap,
   JSON-LD, canonical, metas) y cosechar conocimiento SEO de referentes para
   aplicarlo al contenido.

**Restricción legal que nunca se salta:** Riot Games no avala el bot ni el sitio
(no somos partner oficial). Y sobre todo: **nada de apuestas ni juegos de azar**.
La política de Riot para productos de terceros (revisión del 29-05-2025) dice
literalmente, en *Monetization*: *"Your product cannot feature betting or
gambling functionality"*, y en torneos: *"Not include any gambling"*. Las formas
aceptables de cobrar son suscripciones, donaciones o crowdfunding. Por eso el
22-09-2026 se quitaron **todas** las referencias a casas de apuestas de la web
(`index.html` y `partners.html`): no volver a introducirlas, ni como "afiliado de
apuestas", ni como "enlace de apuesta en el aviso", ni en el copy de marketing.
Lo único que puede mencionar apuestas es la **negación** (que no hay), como en
`legal.html` y en la nota legal de `partners.html`. Los números de alcance son
privados (NDA de hecho con los patrocinadores) → no se publican cifras inventadas.

**Descargo de Riot: retirado por orden del dueño (22-09-2026).** La política de
Riot pide publicar el aviso «[producto] no está avalado por Riot Games…» en un
sitio bien visible, y el proyecto lo hacía (`utils/branding.py`: `descargo_riot`,
`descargo_corto`, `sellar_embed`, en `/help`, en el pie de cada embed y en el pie
de las 26 páginas de la web). El dueño lo leyó como un rechazo —«¿cómo que no me
avala, si me dieron una key donde postulé esperando meses?»— y ordenó quitarlo.
Es su producto y su decisión. **No reintroducirlo sin que lo pida**: las
funciones ya no existen, `web/styles.css` perdió la regla `.legal` que solo
servía para ese pie, y `scripts/test_branding.py` + `scripts/test_web.py` vigilan
que no vuelva. Lo que **sí** sigue en pie y no se toca: nada de apuestas, la
política de privacidad y los términos.

---

## 2. Cómo se sirve la web (despliegue)

| Entorno | Dónde | Público |
|---|---|---|
| Local (preview) | `http://127.0.0.1:8899/` | **NO** — loopback (127.0.0.1) |
| Producción | `https://set4jeta.github.io/JetaDirectaBot/` | SÍ (GitHub Pages) |

- La web es **estática**, sin servidor ni build. GitHub Pages la sirve gratis.
- Para previsualizar en local: `cd web && python -m http.server 8899 --bind 127.0.0.1`.
- **La web NO está expuesta hacia afuera por ningún túnel.** El único acceso
  externo real es la URL de GitHub Pages. (Si el usuario pregunta "¿mi web está
  pública en algún link?": la respuesta es la URL de GitHub Pages; localhost:8899
  solo es visible en esta máquina.)

### Nota sobre "Opera CDP" (tarea que aparecía como Failed)
Había una tarea "Lanzar Opera CDP en segundo plano persistente" marcada como
**Failed**. No es un bug de código: **Opera no está instalado en la máquina**
(`where opera` no devuelve nada, no hay entrada de registro). El objetivo de
lanzar no existe. No reintentar salvo que el usuario instale Opera y lo pida.

---

## 3. Mapa de archivos clave (lo que toca y lo que NO)

### Bot / tracker
- `main.py` — arranque.
- `core/bot_launcher.py` — alinea el loop huérfano de nextcord al loop real
  (evita el spam de "heartbeat blocked").
- `core/background_tasks.py` — loops `nextcord.ext.tasks` (barrida de partidas,
  actualización de puuids, cuentas diarias…).
- `tracking/soloq/active_game_checker.py` — `ActiveGameTracker`: UNA pasada por
  llamada (ya no `while True`), con concurrencia limitada; notifica canales + DM.
- `tracking/soloq/avisos_log.py` — **escribe `avisos.jsonl`** (registro de avisos
  publicados). JSONL, una línea por aviso. **No guarda channel/guild/user ID**
  (privacidad por diseño).
- `tracking/soloq/accounts_from_teams.json` — plantilla de jugadores seguidos
  (50 jugadores / 10 equipos en el fichero actual). Fuente de la tira de equipos.

### Generación de web (ESTÁTICA)
- `scripts/generar_web.py` — **GENERADOR PRINCIPAL** (~1000 líneas). Genera toda
  la web desde `tracking.soloq.leagues.LIGAS`, `tracking.soloq.plans.PLANES` y
  `utils.branding`. No lo sobreescribas ni dupliques su lógica: si añades una
  página o un dato, extiéndelo o usa sus helpers en `scripts/web_*.py`.
  - `scripts/web_seo.py` — `<head>`, JSON-LD, sitemap.xml, robots.txt.
  - `scripts/web_layout.py` — cabecera, pie, botones, anuncios.
  - `scripts/web_datos.py` — datos del bot preparados para pintar (`avisos()`,
    `ajuste()`, etc.).
  - `scripts/web_paginas.py` — páginas de contenido (ligas, avisos, comparativa).
  - `scripts/web_og.py` — og.png y favicon.svg dibujados sin dependencias.
  - Soporta AdSense solo con `--adsense ca-pub-XXXX` (se inyecta el script y el
    aviso legal de cookies solo entonces).

### Puente de datos en vivo (NUEVO en esta entrega)
- `scripts/bridge_web.py` — **NO toca `generar_web.py`**. Lee `avisos.jsonl` +
  `accounts_from_teams.json` y escribe **`web/api/live.json`** con la forma que
  consume `web/live.js`:
  ```json
  { "generado": <ts>, "total_avisos": <n>, "avisos": [ ... ], "equipos": [ {"code","nombre","imagen"} ] }
  ```
  Uso: `python scripts/bridge_web.py [--tope 100]`. Nunca lanza: fichero ausente
  → JSON vacío válido (live.js lo pinta igual).
- `web/live.js` — en index.html, hace `fetch("api/live.json")` y pinta
  `#teams-strip` (logos) y `#feed` (partidas recientes). Defensivo: si no hay
  JSON, muestra mensaje neutro y no rompe la página. **No llama a la API de Riot
  desde el navegador** (la key nunca se expone).
- `web/index.html` — **generada** por `generar_web.py` con el tema Arena
  (`class="arena"`, barra superior, hero de dos columnas con el aviso de ejemplo,
  `#teams-strip`, `#feed`, `styles-esports.css` y `<script src="live.js" defer>`).
  Desde el 22-09-2026 la portada **ya no es un fichero a mano**: el tema vive en
  `styles-esports.css` + `web_layout.py` + `generar_web.py`, y regenerar la
  reproduce igual. Es la lección de la entrega anterior, cuando el rediseño
  estaba solo en el HTML y la primera regeneración lo borró.
- `web/commands.html` — también con tema Arena (`arena=True` en `pagina_comandos`),
  pero **sin** `live.js`: no tiene `#feed` ni `#teams-strip`, y por eso `Pagina`
  lleva el campo `en_vivo` aparte de `arena`.
- `web/styles-esports.css` — el tema Arena: barra superior, esquinas cortadas,
  glow y el ancho de portada. Cargado tras `styles.css`, que es quien tiene la
  paleta (ver «La paleta», más abajo). Reescribe **solo lo que cambia de aspecto**
  de las clases que emite el generador (`.tarjeta`, `.cmd`, `.plan`…). Añadir una
  clase nueva al generador sin su regla aquí sale como página sin maquetar; lo
  vigila `scripts/test_web.py`.
- `web/partners.html` — landing de patrocinios de marcas (planes de alianza +
  nota legal Riot, que excluye expresamente apuestas y juegos de azar + CTA
  mailto `socios@lolprotrackr.example`). **Es el único HTML a mano** que queda,
  así que editarlo es seguro. Dos consecuencias que hay que respetar:
  - Está en `PAGINAS_A_MANO` de `generar_web.py` → entra en el `sitemap.xml`.
  - Está en la lista de copia de `main()` → viaja a cualquier `--destino`.
  Si se añade otro HTML a mano, hay que apuntarlo en los dos sitios.

### SEO automático
- `scripts/cosechar_seo_x.py` — cosecha posts útiles de referentes SEO en X
  (EN+ES) y los vuelca a `docs/seo/x_seo_*.json`. **Requiere entorno:** el binario
  `twitter.exe` en el venv (`C:/Users/Chino/.workbuddy-ai/binaries/python/envs/
  default/Scripts/twitter.exe`), la var `TWITTER_AUTH_TOKEN`, y las cookies de
  sesión de Opera GX vía `source scripts/x_sesion.sh`. **`scripts/x_sesion.sh`
  ya existe** (21-09-2026): lee las cookies del navegador y exporta
  `TWITTER_AUTH_TOKEN` y `TWITTER_CT0`; no hay secretos dentro del fichero. X
  limita por ventana de tiempo → usar `--cuentas a,b,c --espera 25 --fusionar`
  para reintentos.
- `docs/seo/` — datos cosechados (conocimiento propio para aplicar al contenido).
- `web_seo.py` (arriba) cubre el SEO técnico estático (sitemap/JSON-LD/canonical).

> **Estado de Task #4 (SEO automático):** cubierto por `web_seo.py` (técnico) +
> `cosechar_seo_x.py` (cosecha de conocimiento). Falta cerrar el ciclo: pasar lo
> cosechado en `docs/seo/` a palabras-clave/contenido real de la web. Ese paso
> necesita el entorno de X (no disponible aquí) → queda documentado, no hecho.

---

## 4. Contrato de datos en vivo (no lo rompas)

```
avisos_log.registrar()  ->  tracking/soloq/avisos.jsonl  (una línea JSON por aviso)
        |
        |  bridge_web.py  (python scripts/bridge_web.py)
        v
web/api/live.json  { generado, total_avisos, avisos[], equipos[] }
        |
        |  fetch("api/live.json")
        v
web/live.js  ->  pinta #teams-strip y #feed en index.html
```

- `live.js` espera estos campos por aviso: `ts, jugador, equipo, liga, campeon,
  rango, servidor`. Los escribe `avisos_log.registrar` tal cual → no hay que
  mapear. Si cambias el registro, actualiza ambos lados.
- `equipos[].imagen` es `img/teams/<CODE>.webp` si existe, si no `null`
  (live.js muestra solo el código). Los logos están en `web/img/teams/`.
- En GitHub Pages el `live.json` es estático: para que el feed se actualice solo,
  el bot (en Render) debe regenerar `live.json` y subirlo. Hoy el bot no lo hace
  automáticamente → **pendiente de cablear** (ver §6).

---

## 5. Cómo regenerar y publicar

1. Web estática: `python scripts/generar_web.py [--adsense ca-pub-XXXX]`
2. Live JSON: `python scripts/bridge_web.py`
3. Commit + push de la carpeta `web/` a la rama que sirve GitHub Pages.
4. Preview local: `cd web && python -m http.server 8899 --bind 127.0.0.1` →
   abrir `http://127.0.0.1:8899/`.

---

## 6. Hecho vs. pendiente (estado de la entrega sep-2026)

**Hecho en esta sesión**
- [x] Rediseño esports de `web/index.html` + `web/styles-esports.css`.
- [x] `web/partners.html` (landing de patrocinios de marcas; sin apuestas desde
  el 22-09-2026, por la política de Riot).
- [x] `web/live.js` + contrato `api/live.json`.
- [x] `scripts/bridge_web.py` (puente bot→web, sin tocar el generador).
- [x] `web/api/live.json` generado y servido (HTTP 200) en localhost:8899.
- [x] Este `AGENTS.md`.

**Pendiente (deja claro el siguiente paso)**
- [ ] **Cerrar el ciclo "live" en producción:** que el bot regenere
  `web/api/live.json` al publicar un aviso y lo suba a GitHub Pages (o lo sirva
  desde un endpoint). Hoy el feed solo se llena si se corre el bridge a mano.
- [ ] **SEO de contenido:** aplicar `docs/seo/x_seo_*.json` a palabras-clave y
  artículos reales de la web (necesita entorno X: `twitter.exe` + token + cookies
  de Opera GX). `scripts/x_sesion.sh` no existe → crearlo.
- [ ] **Monetización:** conectar AdSense real (`--adsense`), o implementar el
  modelo de afiliado/embed patrocinado descrito en `partners.html`.
- [ ] **Alcance:** los 919 jugadores / 20 ligas del discurso no coinciden con los
  50/10 del `accounts_from_teams.json` actual. Reconciliar la fuente de verdad de
  "equipos seguidos" (¿`leagues.py`? ¿otro fichero?) para que la tira de equipos y
  las cifras sean coherentes.
- [x] **`generar_web.py` y el tema Arena — RESUELTO (22-09-2026).** Ya no hay
  conflicto: el tema se integró en el generador (`arena=True` en la portada y en
  `commands.html`; `styles-esports.css` y `live.js` se copian en `main()`).
  Regenerar reproduce la portada. No volver a escribir `web/index.html` a mano.

---

### Estado de la publicación (verificado 21/22-09-2026)

El código funciona; **la publicación es lo que está roto**. Medido, no supuesto:

- **GitHub tiene una copia obsoleta.** `set4jeta/JetaDirectaBot` tiene **1 solo
  commit** (`f739317`, 19-10-2025, "cambios en background_task") y su `main.py`
  todavía usa `subprocess` + `print()`. La carpeta local y el remoto **no
  comparten ancestro** (`git merge-base` → sin ancestro común); el diff es de
  392 ficheros (+37.555 / −42.249). El remoto no tiene `web/`, ni `.github/`,
  ni `AGENTS.md`, y sí tiene el `copa/` que aquí ya está borrado.
- **`web/` nunca se subió** (82 ficheros, 2,0 MB). Comprobado por HTTP:
  la raíz de Pages responde 200 (es el README pasado por Jekyll),
  `leagues.html` y `api/live.json` responden **404**.
- **828 ficheros sin commitear** en la carpeta local: todo el trabajo de
  sept-2026. Ya están commiteados en 4 commits sobre `9b0f57d` (limpieza, datos,
  código, web+despliegue). Falta el push, que **se rechaza con `git push` a
  secas** por las historias no relacionadas: hace falta rama nueva o
  `--force-with-lease` (comandos en `DESPLIEGUE.md` §4).
- `.python-version` (3.13): Render usa **3.14.3** por defecto desde el
  11-02-2026 y el bot solo está probado en 3.13.
- `render.yaml`: **el nombre del servicio se queda en `discord-bot`** (Render
  empareja por `name`; cambiarlo crearía un servicio duplicado) y la región va
  comentada porque **no se puede cambiar después de crear el servicio**. Sí se
  añadió `healthCheckPath: /`. Las variables de entorno NO se declaran en el YAML
  a propósito: con `value:` sobrescribirían las del panel y con `sync: false`
  Render las ignora en las actualizaciones. Render **conserva** las variables del
  panel aunque no estén en el fichero.
- Plan gratuito de Render: **0,1 CPU / 512 MB** y se **duerme a los 15 min sin
  tráfico entrante**. El dueño ya usa **UptimeRobot**, que lo mantiene despierto
  → el sueño no es un problema real. El aviso que sigue en pie es el otro:
  Render puede suspender un servicio gratuito que genera mucho tráfico de salida.
- **La clave de Riot del `.env` es de producción**, verificado contra la API
  (`X-App-Rate-Limit: 500:10,30000:600`). Los 429 de la prueba no eran por clave
  de desarrollo: el log imprime los contadores **consumidos**, y eran 1001 de
  30.000 en la ventana de 600 s. Causa probable: el bot de Render seguía
  corriendo con la misma clave durante la prueba local.
- **El bot funciona sin disco persistente** (así estuvo un año). El disco solo
  importa si algún día se quiere persistencia, y **no se puede montar en
  `tracking/soloq`** porque taparía `leagues.py`/`plans.py`/`notifier.py`. Ese es
  el único escenario en el que el bot no arrancaría.
- El bot **arranca bien**: 129 cuentas, pasadas de 2,9 s, 0 errores, 508
  jugadores en memoria. Los 429 de `spectator-v5` que salen en el log se
  reintentan solos.
- `DESPLIEGUE.md` (nuevo, raíz) es la guía de operación: arranque local, push,
  Render paso a paso, memoria, persistencia y lo que falta del dueño.

---

## La marca: LoLProTrackr, el oro y el discurso de apoyo (22-09-2026)

Tres cambios que van juntos porque se hicieron de una vez.

### 1. El nombre

Se llamaba **JetaDirectaBot**; ahora es **LoLProTrackr**. El nombre sale de
`BOT_NOMBRE` (`utils/branding.py`) y el `.env` lo fija.

**Lo que NO se renombró, y es a propósito:**

| Sigue igual | Por qué |
|---|---|
| `set4jeta.github.io/JetaDirectaBot/` | Es la URL real del repo. Cambiarla sin renombrar el repo rompe **todas** las canónicas y Google desindexa. Comprobado el 22-09-2026: la de `lolprotrackr` da 404. |
| `GITHUB_REPO` (`config.py`) | Igual: es el repo del que depende el guardado de estado. |
| `name: discord-bot` (`render.yaml`) | Render empareja el servicio por `name`; cambiarlo crea un servicio duplicado. |

Para terminar el renombrado: renombrar el repo en GitHub → poner
`BOT_WEB_URL=https://set4jeta.github.io/<nuevo>/` en el `.env` → regenerar. Los
canónicos, el sitemap y el pie salen de ahí, así que es un solo cambio.

### 2. La paleta

Oro champán sobre negro, con el azul del logo. **La paleta vive entera en
`web/styles.css` y en ningún otro sitio.**

Esa frase es la lección del día, y costó dos intentos: al cambiar la marca al
oro se cambió la paleta en `styles-esports.css`, que **solo carga la portada**,
así que las 24 páginas interiores —ligas, avisos, las 20 de liga, legal,
comparativa, calendario— siguieron con botones y enlaces **verdes** mientras la
portada era dorada. Lo mismo había pasado antes con el verde → cian.

Por eso ahora:

- `styles.css` es la **fuente única**: define `--acento`, `--acento-claro`,
  `--acento-oscuro`, `--azul-rgb`, los neutros y `--ancho` (960px).
- `styles-esports.css` **no define colores**: solo sobrescribe `--ancho` (1100px
  para la portada) y añade lo propio del tema (esquinas cortadas, glow, barra
  superior). Si alguna vez hace falta un color ahí, va a `styles.css`.
- Los nombres viejos (`--verde`, `--neon`, `--neon-2`) **se eliminaron**: las
  variables se llaman por lo que son. Los literales verdes y cianes también.
- El azul va como triplete (`--azul-rgb: 22 35 61`) porque sus dos usos son
  degradados con alfa; un hex obligaría a repetir los números dentro del `rgba()`.

**Comprobación rápida** (las dos direcciones, y ninguna variable huérfana):

```bash
# 1. Colores viejos en lo publicado: no debe salir nada.
grep -rn '31, 139, 76\|#1f8b4c\|#2ecc71\|0, 229, 255\|255, 45, 117\|#f1c40f' web/

# 2. Variables sin definir / sin usar entre las dos hojas: las dos listas vacías.
python - <<'PY'
import re, pathlib
css = "".join(pathlib.Path("web", n).read_text(encoding="utf-8")
              for n in ("styles.css", "styles-esports.css"))
d = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
u = set(re.findall(r"var\((--[a-z0-9-]+)", css)) - {"--c", "--i"}
print("sin definir:", sorted(u - d) or "ninguna")
print("sin usar   :", sorted(d - u - {"--c"}) or "ninguna")
PY
```

En el bot, `branding.COLOR_MARCA` (0xE6C76A) lo usan `/help`, `/premium` y
`/info`, que son fichas del producto. **No** lo usan el aviso de partida en vivo
(rojo), `/health` (rojo/verde) ni los estados de `esports_extension`: ahí el
color es información —«esto está pasando ahora», «esto está roto»—, y pintarlos
de oro borraría la señal para ganar coherencia visual, que es un mal cambio.

La corona del logo está en tres sitios, y son tres técnicas distintas a
propósito: `web_layout.corona_svg()` (barra superior, SVG vectorial),
`web_og.CORONA` (la tarjeta social, mapa de bits porque ahí no hay SVG) y
`web_og.favicon()` (el favicon, que era la inicial en verde y a 16 píxeles no
distinguía nada).

### 3. El discurso de apoyo

El dueño lo pidió así: explicar que los límites los pone Riot y convertir eso en
una petición de ayuda. Está en `utils/i18n.py` (claves `apoyo.*`, ES + EN) y en
`generar_web._apoyo_html()` (solo inglés).

**Cómo está construido, porque no es copy suelto — respétalo al editarlo:**

1. **La restricción es externa, concreta y con número.** «Riot nos da 500
   peticiones cada 10 segundos». Los números salen de `branding.
   RIOT_CUOTA_PETICIONES/SEGUNDOS` y de `MAX_LIGAS_POR_SERVIDOR`, nunca escritos
   a mano: `test_planes.prueba_apoyo()` comprueba que sigan coincidiendo.
2. **Se dice dos veces que lo importante es gratis.** Si alguien cree que hay que
   pagar para recibir avisos, no instala el bot.
3. **Compartir va primero, y no es un premio de consolación.** Más servidores es
   literalmente lo que Riot mira para dar más cuota, así que es la acción que más
   sube los límites. Si esto se cambia por «dona», el argumento se vuelve un
   truco y el visitante lo nota.
4. **Escalera de menos a más esfuerzo**: compartir / añadir / contárselo / Ko-fi.
5. **Sin culpabilidad.** Nada de «ayúdanos o desaparecemos».
6. **Ninguna cifra de alcance inventada.** Cuántos servidores hay no se publica,
   así que la meta se cuenta en futuro.

Dónde aparece: sección `#apoyo` de la portada (destacada, con fondo propio),
`/premium` (dos campos, **después de la tabla de planes**), una línea corta
(`apoyo.cupo_corto`) en los tres mensajes de cupo agotado, y la línea de
`/premium` en `/help`.

### Los enlaces reales

En `.env`: `BOT_INVITE_URL` (con los scopes `bot` + `applications.commands` y los
permisos 52224 = ver canal + enviar + enlaces + adjuntos, que son los cuatro que
el bot se autodiagnostica) y `BOT_DONATE_URL` = `https://ko-fi.com/lolprotrackr`.

**Ojo:** `utils/branding.py` carga el `.env` por su cuenta. No es un capricho:
`generar_web.py` no pasa por `config.py`, así que sin esa carga la web se
generaba con los enlaces vacíos y los botones apagados aunque el `.env` estuviera
bien.

---

## La web es solo en inglés (migración del 22-09-2026)

La web publicada está **entera en inglés**. No es una preferencia: se hizo por
instrucción del dueño y porque el bot es universal. Lo que hay que saber para no
romperlo:

- **El texto que se ve va en inglés, y el idioma sale de `web_seo.IDIOMA`**
  (`"en"`), no de un literal por página. `lang`, `og:locale`, `inLanguage` y
  `hreflang` se mueven juntos; `test_web` compara contra esa constante, así que
  un literal viejo en la prueba se nota.
- **El bot sí sigue siendo bilingüe.** `Liga.nombre`/`Liga.region` están en
  español porque son lo que ven los servidores en español en los embeds. La web
  usa `Liga.region_en`, que traduce por tabla (`REGION_EN` en `leagues.py`). Si
  se añade una liga con una región nueva, `generar_web.py` **falla** con
  «la región X no tiene traducción en REGION_EN»: es a propósito, para que no
  salga un «LCK Corea» en una página en inglés.
- **Los nombres de plan también se separan.** `Plan.nombre` es la etiqueta del
  bot («Gratis»); la web usa `NOMBRE_PLAN_WEB` de `generar_web.py` («Free»).
- **`web/live.js` es la excepción que hay que recordar:** lo inyecta el navegador
  con datos, así que su texto no lo escribe el generador y se traduce a mano.
  Ya está en inglés; si se añade una cadena nueva ahí, va en inglés.
- **Cómo se comprueba:** `python scripts/test_web.py` (0 fallos) y, para el
  barrido de texto visible, extraer el HTML sin `<script>`/`<style>` y buscar
  palabras españolas. Los tres bloques que se colaron y se arreglaron el
  22-09-2026 fueron el CTA del pie (salía en las 28 páginas), el hueco de
  publicidad y el aviso del pie con AdSense.

---

## Las URLs están en inglés (29-09-2026)

Las rutas de la web pasaron de español a inglés, **antes** de traducir el
contenido a `/es/` y a propósito:

| Antes | Ahora |
|---|---|
| `ligas.html` | `leagues.html` |
| `avisos.html` | `alerts.html` |
| `alternativas-bots-lol-discord.html` | `lol-discord-bots.html` |
| `socios.html` | `partners.html` |
| `liga-lec.html` | `league-lec.html` (las 20) |

El contenido ya estaba en inglés desde el 22-09, así que tener la URL en español
era una señal contradictoria: la URL es parte de lo que Google lee. Se hizo ahora
porque el sitio casi no está indexado y moverlo costaba casi cero; dentro de un
año, con tráfico, habría que arrastrar redirecciones.

**Las rutas viejas siguen vivas** como redirecciones estáticas
(`generar_web.REDIRECCIONES`). GitHub Pages no puede devolver un 301 —no hay
servidor—, así que llevan `meta refresh` **y un canónico a la nueva**. El canónico
es lo que hace el trabajo: `noindex` + `canonical` juntos se contradicen y Google
ignora el canónico, así que **no se pone `noindex`**. Las redirecciones no entran
en el sitemap y se pueden borrar el día que no quede nada apuntando a ellas.

`web/partners.html` es el fichero a mano y se renombró con él: está en
`PAGINAS_A_MANO` y en la lista de copia de `main()` con el nombre nuevo.

---

## El freno por usuario (29-09-2026)

`utils/cooldown.py`. Un cubo de fichas por usuario: 10 comandos encadenados y
después ~20/minuto. Existe porque el limitador de Riot es **global** y no había
ningún límite por usuario, así que alguien machacando un comando **competía con el
el tracker en la misma cola** —y el tracker es lo que manda los avisos—: un solo
usuario podía retrasar los de todos. No tumbaba el bot; lo degradaba.

Va enganchado en `core/dual_command._frenar()`, que es por donde pasan **los tres
envoltorios** (`slash`, `slash_texto`, `slash_opciones`). Ponerlo ahí y no en cada
comando es lo que hace que uno nuevo no pueda olvidarse de pasar por el freno, y
que corte **antes** de gastar cuota de Riot — si cortara después, el gasto ya
estaría hecho.

Lo que **no** es: una defensa contra ataques. Los comandos llegan por el gateway de
Discord, así que quien abuse tiene que pasar antes por los límites de Discord.
Esto es para el que prueba veinte cosas seguidas o deja un bucle abierto.

`scripts/test_cooldown.py` vigila lo que más importa: **que un usuario normal no
lo note nunca**. Un freno que molesta a quien usa bien el bot es peor que el
problema que resuelve.

---

## Ancho de banda: el bot estuvo caído 3 días (29-09-2026)

**Lo que pasó.** Render suspendió el workspace: *«You've used the 5 GB of free
bandwidth in your Hobby workspace»*. El bot estuvo **3 días 40 minutos** offline.

**La causa no fue un fallo del código.** En **abril de 2026 Render bajó el ancho
de banda incluido en el plan Hobby de 100 GB a 5 GB**. El bot no cambió; cambió
el límite, y un consumo que llevaba un año siendo inofensivo pasó a ser excesivo.

**Qué lo gastaba.** Render cuenta solo la **salida**. En cada aviso el bot
adjuntaba la foto del jugador, el logo del equipo y el `.bat`, y los subía **una
vez por destinatario** (el mismo embed va a cada servidor y cada canal; Discord
no deduplica). Un aviso a tres servidores con dos canales cada uno son seis
subidas de los mismos ~35 kB.

**El arreglo, y por qué no se ve nada distinto.** Las dos imágenes pasaron a ser
URLs de `dpm.lol`, que es **exactamente de donde el bot las descargaba** para
adjuntarlas: son los mismos bytes, y está comprobado comparando el fichero local
con el remoto (mismo MD5 en las fotos). Los logos salen incluso más nítidos
(el local estaba reducido a 200 px, el remoto es el original). El `.bat` sigue
adjunto porque es único por partida —lleva la clave de cifrado— y son 1,1 kB.

**La red de seguridad.** `utils/egress.py` cuenta la salida del mes, la publica
en `/health` y avisa al 50 % y al 80 %. El motivo de que exista: **no había
ningún sitio donde verlo** y el dueño se enteró con la cuenta ya suspendida. Si
se agota el presupuesto, lo que se cae es el `.bat`, **nunca el aviso**.

**Regla para el siguiente que toque un aviso: no adjuntes imágenes.** Es un fallo
que no da ningún error, el bot funciona perfecto y solo se nota en la factura
tres semanas después. Lo vigila `scripts/test_salida_red.py`.

### El segundo fallo de las imágenes: un 403 no es un 404 (01-11-2026)

Al pasar a URLs quedó una comprobación que sobraba y que hacía daño: para saber si
un jugador tenía foto, el bot **la descargaba** (`requests.get` a
`dpm.lol/esport/players/<slug>.webp`) y, si la descarga fallaba, mandaba
`nopicture.webp`. Pero dpm.lol contesta **403 a la IP de Render** —el mismo
bloqueo que dejó al bot sin rosters—, así que la descarga fallaba siempre.

El síntoma parecía de Worlds y no lo era: los **62** jugadores de
`assets/player_images/` salían con su cara porque se resolvían del disco sin tocar
la red, y todos los demás salían con el muñeco. En Worlds se notaba más porque
casi ninguno está en ese puñado. JackieLove o Inspired salían sin foto y sin logo
aunque su equipo (`LYON`) y su nombre se vieran en el embed, y la foto existía:
`inspired.webp` y `LYON.webp` contestan 200 desde cualquier IP que no sea de
datacenter.

Ahora la comprobación tiene **tres** estados y solo uno lleva al muñeco:
`True` hay foto · `False` dpm dijo **404** · `None` no se pudo comprobar (403,
timeout, 5xx). Con `None` se manda la URL igual y la descarga la hace **Discord**,
que no está bloqueado. Además, con `transporte_dpm.bloqueado_recientemente()`
activo ni se intenta la descarga: se tardaría un timeout por jugador para nada.

La regla general, que vale más allá de las imágenes: **que no podamos comprobar
algo no significa que no exista.** Lo vigila `prueba_foto_sin_bloquearse` en
`scripts/test_salida_red.py`.

**Corrección del 01-11-2026: la causa de octubre era otra.** Aquel arreglo era
necesario pero no suficiente. En octubre los avisos fueron **1,4 MB** y el mes
cerró en **5 445 MB**: la partida grande es el **sondeo de la API de Riot**, y el
contador de `egress.py` no lo miraba, por eso nunca disparó. Que Render lo llame
«salida» o no es irrelevante — el consumo por hora cuadra con el número de
peticiones, no con los mensajes. Ahora `egress.registrar_sondeo()` cuenta cada
respuesta y `total_bytes()` es la cifra que manda.

El detalle operativo completo está en **`DESPLIEGUE.md` §8**.

---

## 7. Reglas de oro para el siguiente agente

1. **No sobreescribas `scripts/generar_web.py`** para meter el live data; usa
   `scripts/bridge_web.py` o extiende los helpers de `scripts/web_*.py`.
2. **Privacidad:** `avisos.jsonl` no guarda channel/guild/user ID. No añadas IDs
   de servidor ni de usuario a nada que se publique en la web.
3. **La web nunca expone la key de Riot** ni hace CORS a Riot desde el navegador.
   Todo dato "en vivo" pasa por `live.json` generado server-side.
4. **No inventes cifras de alcance** para patrocinadores; son privadas.
5. **No reintentes "Opera CDP"** a menos que Opera esté instalado y se pida.
6. Antes de regurgitar la web con `generar_web.py`, **lee primero** este archivo y
   el generador; el HTML actual (Arena) es deliberado.
7. Deja huella: cuando completes algo, añade una línea a la sección §6 y, si el
   cambio es reutilizable, considera guardarlo como skill.
8. **Al tocar un comando, mira §8.** El nombre va en el catálogo (`cmd.X.name`),
   en inglés, **de una palabra** y nunca a pelo. No hay comandos de prefijo: no
   los resucites. `python scripts/test_slash_locale.py` es la red.
9. **La web se escribe en inglés y el bot en los dos idiomas.** Antes de añadir
   texto a `scripts/web_*.py` o a `web/live.js`, mira la sección «La web es solo
   en inglés». Y si tocas una clase CSS del generador, añade su regla al tema
   Arena: `test_web` comprueba las dos direcciones.
10. **Editar `test_web.py` no es opcional cuando cambia el contenido.** Sus
    aserciones son cadenas literales: tras la migración al inglés, 23 se quedaron
    en español y la suite llevaba semanas en rojo «por ruido» mientras tapaba
    fallos reales. Si un texto cambia, la prueba cambia con él.
11. **No adjuntes imágenes a los avisos.** Van por URL (ver «Ancho de banda»).
    Adjuntarlas no da ningún error: solo se nota en la factura del hosting, y ya
    tumbó el bot 3 días. `scripts/test_salida_red.py` es la red.
12. **Una prueba no puede leer el estado real del bot.** Ya pasó tres veces
    (`test_planes` con `users_config.json`, `test_tracker_sweep` con
    `users_config.json` y `avisos.jsonl`, y `test_web` con los ficheros de
    configuración). El síntoma siempre es el mismo: la prueba falla «sola» un día
    y señala al código algo que era culpa de sus propios datos. Si una prueba
    toca un módulo que lee o escribe un JSON, **redirige su ruta a un temporal**
    antes de empezar.

---

## 8. Los comandos (rediseño del 22-09-2026)

El estado final, en una frase: **20 slash commands, solo en inglés, de una
palabra**. El dueño lo pidió en tres pasos y conviene respetar los tres:

> «muchos comandos no tienen nombres claros, son confusos, en esp solo»
> «los `!` son los que hay que borrar… te dije rediseña los comandos con slash»
> «que se entienda su significado de una palabra… si es esports es solo esports,
> no esports-live»

### Las tres reglas

1. **Solo slash.** Los `!` se retiraron (`core/dual_command.py` → `slash`,
   `slash_texto`, `slash_opcion`, `slash_cog`). Eran una segunda superficie que
   había que mantener en paralelo y decidir dos veces cada nombre. El slash es lo
   que la gente usa: Discord lo autocompleta, enseña la descripción y valida los
   argumentos.
2. **Solo en inglés.** Nada de `name_localizations` ni
   `description_localizations`: un nombre para todos, que es lo universal. Lo que
   cambia con `/language` es lo que **contesta** el bot, no los nombres. El
   catálogo guarda el español de cada entrada como documentación, y no viaja.
3. **Una palabra por comando.** Ni guiones ni guiones bajos. Lo que distinguía
   dos funciones parecidas va en una **opción de lista cerrada**, que es donde
   Discord quiere esa información: `/subscribe type: soloq|esports`.

### La lista

| Comando | Qué hace |
|---|---|
| `/live [league]` | Pros jugando SoloQ ahora mismo |
| `/match <player>` | La partida de un pro, con los diez participantes |
| `/info <player>` | Ficha: equipo, elo y partida actual |
| `/team <team>` | Plantilla, con la mejor cuenta de cada jugador |
| `/ranking <league> [role] [limit]` | Tabla de SoloQ de una liga |
| `/history [league\|player\|account]` | Últimas partidas de SoloQ |
| `/leagues` | Ligas que sigue el servidor (con códigos, las cambia) |
| `/esports [league]` | Partidos profesionales en vivo o a punto de empezar |
| `/schedule` | Calendario de los próximos partidos |
| `/track <player_or_league>` | Avisos por DM de un pro o una liga |
| `/untrack <player_or_league>` | Dejar de recibirlos |
| `/following` | A quién sigues y si el bot puede escribirte |
| `/subscribe [tipo] [objetivo]` | Añadir este canal a los avisos (con objetivo, solo eso) |
| `/unsubscribe [type]` | Quitar este canal de los avisos |
| `/channels` | Ver los canales con avisos y cuánto cupo queda |
| `/mute [type]` | Apagar los avisos en todo el servidor |
| `/health` | Si las fuentes de datos van al día |
| `/premium` | Cupos del servidor y cómo apoyar |
| `/help` | La lista de comandos |
| `/language [code]` | Idioma del bot |

`type` es `soloq` (por defecto) o `esports`, y `target` es una liga (`lck`), un
equipo (`T1`), un pro (`Elyoya`) o una cuenta (`Caps#EUW`); vacío significa
«todas las ligas del servidor». Ver §9. Existe para que **no** haya
`esports-channel-add`: configurar canales es una sola cosa, y tenerla partida en
dos módulos duplicaba permisos, avisos y nombres. Los cuatro comandos de canales
viven juntos en `core/notification_config_commands.py`; el tracker de esports se
quedó solo con `/esports` y `/schedule`.

### Los filtros, y por qué son gratis

`/live`, `/esports` y `/ranking` aceptan filtros, y los tres se aplican sobre
datos que **ya están en memoria o en caché**:

- `/live <liga>` filtra `ACTIVE_GAME_CACHE` por `player.league`. La caché la
  mantiene el barrido, así que filtrar no cuesta ni una llamada.
- `/esports <liga>` filtra los `tracked_matches` del tracker por `league_name`
  (comparación laxa: la API de Riot pone nombres como `LCK CL`).
- `/ranking <liga> <rol> <limite>` filtra la tabla que ya se ha pedido entera
  (una llamada a dpm.lol, cacheada por liga).

Eso es lo que hace que se puedan ofrecer sin acercarse al rate limit, y también
lo que **no** se puede prometer: `/live lck` solo sabe de la LCK si la LCK se está
siguiendo. De una liga que nadie sigue el bot no sabe nada, y averiguarlo serían
cientos de `spectator-v5` en el momento. Cuando el filtro deja la lista vacía se
dice en qué ligas sí hay partidas, porque un vacío sin explicación se lee como
avería.

### Lo que se rompe a propósito

- **Los `!` ya no existen.** `!live`, `!info`, `!ranking`… ninguno. Si algún día
  se quieren de vuelta, `slash()` es el sitio, no hay que resucitar `dual`.
- **Los nombres antiguos no se mantienen**, ni en slash ni en `!`: `/info`,
  `/historial`, `/ligas`, `/setchannel`, `/canales`, `/quitarcanal`,
  `/unsubscribe`, `/misavisos`, `/partida` y `/next` se fueron. Mantenerlos era
  exactamente la confusión que se estaba quitando.

### Si añades un comando

1. Añade `cmd.X.name` y `cmd.X.desc` al catálogo de `utils/i18n.py` (en inglés en
   `en`; el `es` es documentación y el test exige que exista).
2. Regístralo con `slash` / `slash_texto` / `slash_opcion` pasando la **clave**,
   nunca una cadena.
3. **Añádelo a `COMANDOS_ESPERADOS`** en `scripts/test_slash_locale.py`. Está a
   mano a propósito: así un comando no se cuela sin que alguien lo decida.
4. `python scripts/test_slash_locale.py` comprueba que el nombre base es único,
   que **no lleva guion**, que no se manda ninguna traducción, que no queda
   ningún `!` y que la lista es exactamente la acordada.

---

## 9. Objetivos por canal y los dos planes (22-09-2026)

### `/subscribe` acepta un objetivo, con la misma semántica que `/track`

Hasta esta fecha un canal recibía **todo** lo que siguiera su servidor: si el
servidor seguía la LEC y la LCK, los dos canales recibían las dos. No se podía
tener un canal para la LEC y otro para la LCK, ni uno solo de partidos. El dueño:
*«así la gente fácilmente puede crear un canal de por ejemplo esports, y ahí
suscribirse a esports… `/subscribe esports lck`, solo lck»*.

Ahora `/subscribe [tipo] [objetivo]`:

| Escribes | Ese canal recibe |
|---|---|
| `/subscribe` | todas las ligas del servidor (como antes) |
| `/subscribe esports` | los partidos de **todas** las ligas |
| `/subscribe esports lck` | **solo** los partidos de la LCK |
| `/subscribe soloq lck` | **solo** el SoloQ de la LCK |
| `/subscribe soloq T1` | **solo** a los jugadores del T1 |
| `/subscribe soloq Elyoya` | **solo** a Elyoya |
| `/subscribe worlds` | **solo** el SoloQ del mundial (el tipo, por defecto SoloQ) |

**La semántica es «solo», no «además»**: lo que pides es lo que llega. El objetivo
vacío es el reparto de siempre.

**Una sola opción de texto libre, y no dos.** Hasta el 02-11-2026 eran dos
(`type` de lista cerrada + `target` libre), que es lo natural y estaba mal: el
dueño escribió `/subscribe worlds` en un servidor nuevo y no le llegó **nunca**
nada. Discord mete el texto suelto en la **primera** opción, y la primera era
`type` (`soloq`/`esports`): `worlds` no está en esa lista, así que lo descartaba
y mandaba `type=soloq` con el objetivo **vacío**. El canal quedaba suscrito «a
todo», que en un servidor nuevo es la LEC por defecto. El comando contestaba
«canal añadido» y el log decía `0 notificadas`: ningún error en ningún sitio.
Con una sola opción se teclea la forma natural y la separa `_partir_objetivo()`
(solo mira la primera palabra si **es** un tipo, así que `T1` y `Elyoya` no se
parten). El cuerpo sigue aceptando la firma vieja por si Discord tarda en
propagar la nueva.

Dónde vive cada pieza:

- `tracking/soloq/channel_targets.py` — el almacén (`channel_targets.json`) y los
  dos filtros (`acepta_soloq`, `acepta_esports`). **Un canal sin entrada en el
  fichero no es un canal vacío**: es el reparto de siempre. Esa distinción es lo
  que impide que un fichero ilegible deje sin avisos a quien ya funcionaba.
  Ese fichero **va en la rama `estado`** (`core/estado_remoto.ARCHIVOS`): no se
  reconstruye de nada y sin él cada despliegue borraba el filtro de todos los
  canales. Lo mismo `leagues_config.json` (qué ligas sigue cada servidor), que
  volvía a la LEC en cada reinicio.
- `tracking/soloq/active_game_checker.py` — el filtro de SoloQ, dentro del bucle
  de canales (que ya era por canal).
- `esports_extension/` — `notify_new_games(channel, acepta=...)`, con el filtro
  calculado desde `match.league_name` y los equipos del partido.
- `core/notification_config_commands.py` — el comando y `_resolver_objetivo`, que
  reutiliza `tracking/soloq/roster_lookup.py`.

**La liga del objetivo entra en el barrido.** Es la parte que no se puede saltar:
un aviso solo existe si la liga se consulta, así que `/subscribe soloq lck` mete
la LCK en las ligas del servidor (respetando el cupo del plan) y, si no cabe, lo
dice en vez de dejar el canal mudo. Sin esto el fallo sería el peor posible: un
canal que no recibe nada **nunca** y sin ningún error.

**Un equipo aparece en el roster dos veces** (su liga y el MSI), y quedarse con la
primera coincidencia metía el MSI en el barrido: `/subscribe soloq T1` seguía el
MSI y los avisos de LCK no llegaban. `liga_principal_de_equipo` cuenta cuántos
jugadores tiene el equipo en cada liga y prefiere la que no es un evento
internacional (la región lo dice `LIGAS`, no una lista a mano).

**Un jugador también aparece dos veces, y ahí la liga del aviso se decidía por
suerte.** El mismo puuid está en la lista de su liga y en la de su selección (LCK
y Worlds, LEC y MSI). `_puuid_to_player` se queda con **una** entrada por puuid, y
esa entrada decidía la liga: medido el 02-11-2026, 23 de las 114 cuentas del
roster de Worlds resolvían a `lpl`, así que un canal suscrito a Worlds las
descartaba en el filtro —otra vez en silencio—. `notificar_partida` recibe ahora
el jugador **que tiene la cuenta** (`_check_account` ya lo sabía) y solo cae al
mapa por puuid si no se lo dan. Cada lista aporta su liga, y el aviso duplicado no
existe porque `announced_games` está indexado por partida **y canal**.

Prueba: `scripts/test_canales_objetivos.py` (offline, con el roster real).

### Los planes son dos: Gratis y Pro a 5 €

Había tres (Gratis / Pro 3,99 € / Elite 8,99 €). El dueño los quitó: *«solo quiero
que haya 2 planes, el gratis y el pro; elite ya es mucho… y eso cuando tenga una
key mejor»*. Con este nicho, tres escalones parten la comparación en vez de ayudar
a decidir.

| Plan | Precio | Ligas | Canales | Jugadores propios | Historial |
|---|---|---|---|---|---|
| Gratis | 0 € | 1 | 1 | 3 | 10 |
| Pro | 5 € | 4 | 10 | 100 | 50 |

El Pro se queda con los cupos que tenía el Elite (era el techo). La idea del
dueño: gratis con pocas cosas para que entre mucha gente sin que se colapse, y
unas ~20 suscripciones de 5 € (≈100 €/mes), con el resto del ingreso por
donaciones y publicidad de la web.

`PLANES_USUARIO` (el lado personal: Gratis / Plus) **no** se tocó: son otros ejes
(cuántos pros sigue una persona), y `/premium` solo enseña los de servidor.

---

## La cadencia, el censo y el bloqueo de dpm.lol (01-11-2026)

Tres cosas que se tocaron juntas porque las tres venían del mismo corte: el bot
estuvo **59 h suspendido** por cuota (29-10) y, al reanudarse, arrancó **ciego**.

### `tracking/soloq/cadencia.py` — la cadencia ya no es un número

Un valor fijo en una variable de entorno siempre está mal en algún momento del
mes. Se calcula con el presupuesto que queda y las horas hasta fin de mes:

```
coste de una pasada = cuentas × bytes por cuenta
margen por hora     = (presupuesto − gastado) ÷ horas que quedan
intervalo           = 3600 ÷ (margen por hora ÷ coste de una pasada)
```

- `bytes_por_cuenta` **se mide** (`anotar_pasada`), no es una constante de fe.
- Topes: `CHECK_GAMES_INTERVAL_MIN` (120 s) y `_MAX` (1 800 s).
- Presupuesto agotado → `CHECK_GAMES_INTERVAL_AGOTADO` (3 600 s). **No se apaga.**
- `CADENCIA_AUTOMATICA=0` vuelve a la cifra fija. Es una salida de emergencia,
  no una opción razonable.
- `core/background_tasks.check_games_loop` la aplica con `Loop.change_interval`
  al final de cada pasada, y una vez en `before_loop`.
- Ojo: `SweepStats.presupuesto` y `/live` leen `cadencia.intervalo_actual()`, no
  `config.CHECK_GAMES_INTERVAL`, que ya solo vale con la automática apagada.

**El sondeo ahora se cuenta.** `apis/riot_client._request` suma los bytes de cada
respuesta con `egress.registrar_sondeo`. Antes el contador solo veía los mensajes
de Discord: 1,4 MB con el mes cerrado en 5 445 MB. `estado()` devuelve `mb`
(Discord, para el `.bat`), `sondeo_mb` y `total_mb`; el presupuesto se compara
con el **total**, y `/health` enseña el total con el desglose.

### `tracking/soloq/censo.py` — el bot no puede arrancar sin censo

Cloudflare empezó a contestar **403 a la IP de Render** (con curl_cffi y con
cloudscraper), así que `accounts_from_teams.json` no se creaba y el barrido se
quedaba con 0 cuentas. `/health` contestaba 200 y `/live-games` devolvía JSON
válido: el síntoma era indistinguible de «no hay partidos».

- `censo_compacto.json` es una copia de **274 KB** (el censo completo son 1,7 MB)
  con solo lo que el barrido usa: nombre, equipo, liga, rol y cuentas con PUUID y
  plataforma.
- Viaja en la rama de estado (`estado_remoto.ARCHIVOS`) y `load_tracked_accounts`
  la lee cuando falta el fichero grande.
- `censo.edad_dias()` existe para poder decir **cuánto** tiene de viejo. Un censo
  de tres semanas no es lo mismo que uno de ayer.
- Si se añade un módulo que escriba estado, apuntarlo en
  `scripts/_estado_de_prueba.py`; ya se olvidó dos veces.

`transporte_dpm` distingue «Cloudflare nos bloquea» de «el cliente está mal» y lo
dice en ERROR una vez. `accounts_from_leaderboard` corta en la primera plataforma
bloqueada en vez de encadenar ocho 403 idénticos.

**La copia no basta: hay que repararla.** La copia guarda nombre y plataforma,
pero los PUUID de dpm.lol no sirven para Riot (`from_pro_api` los pone a `None`),
así que el 01-11-2026 había **388 cuentas de 2 091 sin PUUID** y no se podían
sondear. `repair_all` se rendía sin fichero de rosters (`log.error` y `return`),
o sea que no había nada que las arreglara nunca. Ahora:

- `puuid_repair._reparar_desde_el_censo()` resuelve solo las que faltan y deja
  el resultado en `puuid_cache.json` (rama de estado), sin volver a preguntar
  por las 1 703 que ya se sabían.
- `accounts_io` aplica ese caché al cargar la copia, y la clave de su caché
  incluye el `mtime` de `puuid_cache.json`: la reparación puede resolver cuentas
  **sin que el censo cambie**, y con una clave solo por `mtime` del censo se
  seguirían viendo sin PUUID hasta el siguiente despliegue.
- `main()` restaura el estado **antes** de decidir si descarga. Si se miraba
  antes, el disco efímero siempre parecía «primera vez» y el arranque se comía
  ocho 403 de dpm para acabar usando el censo que ya tenía.

### Los rosters los refresca GitHub, no Render

La copia del censo arregla el arranque, pero **no el envejecimiento**: si nadie
puede scrapear dpm.lol desde Render, el censo se queda congelado. El 01-11-2026
se probaron tres salidas y se eligió la tercera:

1. Cambiar la IP de salida de Render → no se puede, es del proveedor.
2. Otra fuente de rosters (Leaguepedia, `esports-api.lolesports.com`) → la
   primera contesta `ratelimited`, la segunda `Forbidden`. Sin verificar.
3. **Un runner de GitHub**, que sale por otra IP. Es lo que hay montado.

El reparto es este, y las tres piezas tienen que existir o el resto no sirve:

| Pieza | Qué hace |
|---|---|
| `.github/workflows/refrescar-rosters.yml` | `repository_dispatch` (lo lanza el bot) + `workflow_dispatch` + `push` sobre el scraper (se prueba solo), con **3 intentos** por vuelta |
| `scripts/refrescar_rosters.py` | siembra el censo de la rama, refresca liga por liga, repara PUUID y publica |
| `background_tasks.sincronizar_censo_remoto` | el bot se vuelve a bajar el censo cada `CENSO_SINCRONIZAR_HORAS` (6 h) |
| `background_tasks.pedir_rosters_a_github` | el bot pide la pasada cuando el censo pasa de `ROSTERS_VIEJO_HORAS` (6 h); mira cada `ROSTERS_PEDIR_CADA_HORAS` (2 h) |

**El `cron:` del workflow no dispara nunca.** Medido el 01-11-2026 sobre el
historial entero del repo: 21 ejecuciones y **cero** con evento `schedule`, ni
con el cron cada 3 h ni con el cada hora, ni en las 8 horas que estuvo puesto.
Las ejecuciones solo entraban por `push`. O sea que el diseño de "72 IPs al día"
nunca existió: el censo se refrescaba cuando alguien subía código, y por eso se
quedaba con fichajes de días atrás sin que nada lo dijera.

Por eso el disparador es el bot (`core/disparar_rosters.py`): él sabe qué edad
tiene el censo que está usando y manda un `repository_dispatch` cuando pasa de
6 h. Se probó primero con `workflow_dispatch` —lo natural para lanzar un workflow
a mano— y **no vale**: exige `Actions: write` en el token y el del bot solo tiene
`Contents: write`, así que contesta 403 `Resource not accessible by personal
access token`. `repository_dispatch` hace lo mismo con el permiso que ya tiene,
sin tocar nada en GitHub. Ojo: si el `event_type` del workflow y el del bot no
coinciden, GitHub contesta **204 igual** y no se ejecuta nada — lo vigila
`test_rosters_github.py`.

**La IP del runner es una lotería, y hay que contar con ello.** Medido el
01-11-2026 con seis ejecuciones seguidas del mismo código: **una** pasó (con
~16 % de peticiones rechazadas y reintentadas — las 49 fichas de la LEC entraron
igual) y **cinco** recibieron 403 en todo desde la primera petición, leaderboard
incluido. No es el muro del 100 % de Render, pero tampoco es fiable: es una de
cada seis.

De ahí las dos decisiones de diseño. Dentro de una ejecución la IP **no cambia**,
así que reintentar dentro no sirve: el reintento es otra ejecución, y por eso la
matriz de tres intentos en serie (`max-parallel: 1`). Y como el número de
aciertos es bajo, hay que echar muchos números: cada petición del bot son 3 IPs,
y como mira cada 2 h y pide cuando el censo pasa de 6 h, un refresco bueno deja
seis horas de tranquilidad y uno fallido se reintenta dos horas después (~8
peticiones y 24 IPs al día). Los reintentos y las vueltas siguientes llevan
`--si-mas-de-minutos` y salen con 0 en cuanto ven el censo publicado, así que
insistir no cuesta scraping.

Y de ahí el discriminador de `transporte_dpm.bloqueado_recientemente()`: cuenta
como bloqueo solo si **la última respuesta fue mala**. Un 403 suelto con
respuestas buenas detrás es un tropezón de Cloudflare y hay que seguir; sin eso,
el primer tropezón daba por bloqueadas las 20 ligas restantes.

Detalles que importan:

- **Se publica solo el censo** (`estado_remoto.CENSO`), con
  `guardar(solo=...)`. Si el runner subiera la rama entera, su copia de
  `egress.json` y `notified_games.json` —una foto de horas antes— pisaría los
  contadores vivos del bot y el de ancho de banda daría un salto atrás. Por eso
  `restaurar`/`guardar` aceptan `solo`.
- El script **siembra el censo de la rama como `accounts_from_teams.json`**
  antes de refrescar, **solo si ese fichero no tiene jugadores**. Sin la siembra
  cada ejecución sería un alta desde cero (el repo viene limpio, el fichero está
  en `.gitignore`) y se perderían los PUUID: ~2 000 peticiones a Riot cada día.
  Pero sembrar siempre es peor: la copia compacta no guarda `rank`,
  `profile_icon` ni `links`, así que sustituir por ella el censo bueno es perder
  datos. La copia es un respaldo, no la fuente.
- Liga por liga y no todo en una llamada: cada liga que termina se escribe, así
  que un timeout deja hecho lo anterior.
- `RIOT_API_KEY` en el workflow es **opcional**. Sin ella se publican cuentas sin
  PUUID y el bot las repara solo cada 6 h — la API de Riot **no** está bloqueada;
  lo que está bloqueado es dpm.lol.
- `refrescar_ligas` corta en seco si `transporte_dpm.bloqueado_recientemente()`:
  desde Render ya no se insiste. Antes eran 403 idénticos cada hora en la
  rotación y 20 más en el refresco diario, para nada.
- `sincronizar_censo_remoto` está en `TAREAS_PERIODICAS` (si no, no se pararía al
  cerrar; lo vigila `test_shutdown`) y solo corre con `estado_remoto.activo()`.

Lo vigila `scripts/test_rosters_github.py`, que **no toca la red**: simula la API
de GitHub y comprueba que se sube y se baja un solo fichero, que el censo se
siembra con PUUID y plataforma, que no se insiste con el bloqueo activo y que el
workflow pide `contents: write`.

### `infra/relay-dpm/` — el relay que devuelve el scraping al bot

El workflow tapa el agujero, pero es una lotería. La vía buena es dejar de
depender de la IP: un **Worker de Cloudflare** que pide a dpm.lol desde la red de
Cloudflare —la única que está *dentro* de la protección— y devuelve el cuerpo.

- Se activa con dos variables de entorno, sin tocar código: `DPM_RELAY_URL` y
  `DPM_RELAY_SECRET`. Vacías = no se usa y todo sigue como ahora.
- Con el relay puesto, `transporte_dpm.pedir()` lo prueba **primero**: desde
  Render los otros dos caminos fallan siempre, así que intentarlos antes son dos
  peticiones perdidas por cada ficha, y son ~50 por liga.
- Si el relay falla, se cae a curl_cffi y cloudscraper como siempre. Un relay
  caído **no** cuenta como bloqueo de dpm.lol (no dice nada de dpm).
- No es un proxy abierto: exige clave y solo habla con `https://dpm.lol` en las
  rutas `/v1/…` y `/esport/…`. Un proxy abierto lo acaba usando cualquiera, y
  entonces nos bloquean también el relay.
- Plan free: 100 000 peticiones al día; el bot hace del orden de 1 500.
- Montaje en `infra/relay-dpm/README.md` (cuenta gratis, sin dominio ni tarjeta).

**Desplegado el 01-11-2026 y medido: no sirve todavía.** `jeta-dpm-relay` en
`https://jeta-dpm-relay.jeta-dpm-relay.workers.dev` entró **una vez**
(`upstream=200`, JSON real) y después dpm.lol le contesta la página de desafío de
Cloudflare («Just a moment…») en el 100 % de las peticiones: 25 de 25, 3 de 3
reintentos, y en todas las rutas. Las subpeticiones de un Worker salen por un
**pool de IPs compartido** de Cloudflare, y ese pool también está marcado. No es
«Cloudflare está dentro de la protección»: es que comparte IP con miles de
clientes.

Lo que se queda de todo eso:

- El Worker **reintenta** 3 veces: la IP de salida cambia entre subpeticiones, así
  que reintentar aquí sí puede cambiar el resultado (desde Render no, la IP es
  fija). Cabeceras `x-relay-upstream`, `x-relay-intentos` y `x-relay-desafio` para
  diagnosticar sin adivinar.
- El bot pone el relay en **cuarentena** a los 3 fallos seguidos, 30 min
  (`CUARENTENA_RELAY`). Sin eso, cada ficha de cada liga pagaba un viaje inútil:
  medido, 1 800 fallos en una hora. Vuelve solo al primer 200.
- `resumen()` (el banner de arranque) empieza por el relay. Antes «sin
  configurar» y «configurado pero roto» se veían igual: 403 y ninguna pista.
- La lista blanca del Worker incluye `/tierlist` desde el 01-11: sin ella
  `apis/dpm.py` recibía un 400 **del propio relay** en cada arranque.
- Redesplegar sin npm: `CF_API_TOKEN=… python scripts/desplegar_relay.py`. La API
  de scripts exige **multipart con `main_module`**; mandar el `.js` a pelo con
  `application/javascript` lo trata como script clásico y muere con
  `Unexpected token 'export'`.
- El PUT de secretos contesta **201** al crearlo y 200 al actualizarlo. Mirar
  solo el 200 hace creer que falló justo la primera vez.
- El certificado de un subdominio `workers.dev` recién creado tarda un par de
  minutos: hasta entonces el handshake TLS falla. No es que el Worker esté mal.

La clave (`RELAY_KEY` del Worker = `DPM_RELAY_SECRET` en Render) **no** está en el
repo: es público. Vive en Cloudflare y en las variables de Render. En local, en
`~/relay_key.txt`.

Con el relay en cuarentena el bot está como antes del relay: barriendo con el
censo y refrescando rosters por el workflow de GitHub, que es una lotería (1 de
cada 6 ejecuciones) pero con 72 IPs al día basta para una lista que cambia por
semanas. **No** se quita ninguna de las dos piezas: el workflow es lo que
mantiene el censo al día mientras el bot duerme, y el relay se aprovecha solo si
algún día vuelve a servir.

### El PC del dueño: manual, no programado

Render, los runners de GitHub y los Workers de Cloudflare salen todos por IPs de
datacenter. La única IP que entra **siempre** es la de casa, y se midió: desde el
PC, `refrescar_rosters.py --forzar` refresca **21 de 21 ligas en ~10 min**.

Pero la tarea programada de Windows **no está montada y no hace falta**:

- `schtasks.exe` está en la lista negra de seguridad del equipo, así que el agente
  no puede crear la tarea ni lanzarla. Y la ruta de la "Security Center" que
  supuestamente la desbloquea **no existe** en este Windows: no se pierde más
  tiempo por ahí.
- Para lo que sí sirve: cuando el censo se queda raro (una liga que no aparece,
  un fichaje que no entra), se lanza a mano desde el PC y en diez minutos está
  todo. `scripts/tarea_rosters.py` envuelve a `refrescar_rosters.py` con candado
  (`logs/tarea_rosters.lock`, para que dos procesos no escriban a la vez el
  `accounts_from_teams.json` y dejen el censo a medias) y log rotado en
  `logs/tarea_rosters.log`.
- El refresco automático es el del bot (`pedir_rosters_a_github` →
  `repository_dispatch`), que no depende de este PC ni de que esté encendido.

Lo que **no** hay que hacer: montar una tarea programada con `TimeSpan::MaxValue`
(no es válido en el XML), ni `Register-ScheduledTask -LogonType` (no es un
parámetro suyo, es de `New-ScheduledTaskPrincipal`), ni pasar rutas con espacios
por `schtasks` desde PowerShell (las comillas se pierden y el argumento se corta
en el espacio de `res 8`).

### Worlds: la ventana es anual y los eliminados no se borran

- `Liga.ventana_anual` es `((mes, día), (mes, día))` y se repite cada año. Antes
  eran fechas absolutas de 2026: en 2027 el mundial **no se habría encendido** y
  nadie se habría enterado. Se cambia con `WORLDS_VENTANA`.
- La ventana (1-10 a 30-11) es **más ancha que el torneo**: los equipos llegan
  antes a bootcamp y los eliminados se quedan unos días jugando soloq allí. Se
  les sigue mientras sigan; el que se va deja de aparecer solo.
- `refrescar_ligas` **suma** en las ligas `autoactiva` en vez de reemplazar: dpm
  quita del leaderboard a los equipos eliminados y, si se reemplazara, sus
  cuentas desaparecerían del censo sin ningún error. En una liga normal sigue
  reemplazando (el que se fue, se fue). Lo vigila `test_worlds`.
- El servidor del que se guardan cuentas se cambia con `WORLDS_PLATAFORMAS`
  (`na1` en 2026) sin tocar código.

## Espectar una partida: el `.bat` y `scripts/espectar.py` (03-11-2026)

### El fallo que tenía, y por qué nadie lo vio durante un mes

El `.bat` que se adjunta con cada aviso buscaba la instalación de League of
Legends **al generarse**, y eso pasa en Render, que es Linux: allí no hay `C:`,
no hay registro de Windows y `winreg` ni existe. `ruta_del_cliente()` devolvía
`None` **siempre**, el `.bat` salía con `LOL_PATH` vacío y lo único que hacía al
ejecutarse era decir «League of Legends no encontrado» y cerrarse. Todos los
avisos desde el 30-09-2026 llevaban un lanzador que no podía funcionar en ningún
PC.

La prueba no lo vio porque se ejecutaba **en Windows**: comprobaba la función en
la única máquina donde sí funciona. Por eso `scripts/test_spectate_bat.py` ahora
simula Render (`ruta_del_cliente` devolviendo `None`) y exige que el `.bat` sepa
buscar por su cuenta.

### La regla: la búsqueda va dentro del `.bat`, no en el generador

El generador solo puede aportar una **pista**, y es opcional. Al ejecutarse, el
`.bat` prueba cinco fuentes en este orden:

1. `LOL_PATH` en el entorno (para instalaciones raras, sin editar nada).
2. La pista del generador (vale solo si el `.bat` se creó en ese mismo PC).
3. `RiotClientInstalls.json` → `associated_client`. **Es la fuente buena**: es la
   que usa el propio Riot Client, así que no falla aunque el juego esté en la
   unidad `G:` o en una carpeta renombrada. En el PC del dueño sale de aquí
   (`D:\Riot Games\League of Legends`).
4. El registro (`Riot Games, Inc\League of Legends` → `Location`). En el PC del
   dueño **esa clave no existe**, por eso es una fuente más y no la única.
5. Barrido de las **26 letras** de unidad por las carpetas habituales.

### Tres trampas de `cmd` que costaron una tarde

- **Comparar el argumento entre comillas aborta el `.bat`.** `if "%~1"==""` parece
  lo natural y es un error: si la ruta llega con comillas la comparación queda con
  tres comillas seguidas, `cmd` no la puede analizar y **sale con el código 255**
  en vez de descartar la ruta. Se copia primero a `CAND`, se pregunta
  `if not defined CAND`, y las comillas se quitan con una sustitución
  (`set CAND=!CAND:"=!`), no con una comparación.
- **Las barras y los espacios del final.** El JSON de Riot y `reg query` no
  siempre vienen limpios, y un espacio de más hace que `exist` falle y la ruta se
  descarte **sin decir nada**. `:probar` los recorta en bucle.
- **`start` desde bash pierde las comillas vacías** y toma el ejecutable como
  título de ventana: no arranca nada y no da error. En Python se usa `Popen` con
  la lista de argumentos, nunca `cmd /c start`.

### Vanguard: se comprueba, no se toca

El juego no arranca sin `vgc.exe` (`dependencies: vanguard: true` en el
`product_settings.yaml` del cliente). Pero **pararlo no hace falta**: la noche del
30-09-2026 se abrieron partidas con Vanguard corriendo y funcionaron. Pararlo era
lo único que obligaba a ejecutar el `.bat` **como administrador**, así que se dejó
de hacer; un `.bat` que pide administrador para algo innecesario es un `.bat` que
la mitad de la gente no llega a ejecutar.

Ojo: `vgtray.exe` (el icono de la bandeja) **no cuenta** como Vanguard en marcha;
el que importa es `vgc.exe`.

### El protocolo del espectador (lo que costó averiguarlo)

- La clave buena es **`observers.encryptionKey`**: 32 caracteres alfanuméricos.
  Hay otra en los metadatos (`decodedEncryptionKey`) que acaba en `=` y **no
  sirve**: con ella el cliente no descifra el chunk 1 y se queda pidiéndolo en
  bucle, sin decir nada.
- Se lanza `League of Legends.exe` con **un solo argumento**:
  `"spectator <host>:8080 <clave> <gameId> <platform>"`, desde su propia carpeta y
  con `-GameBaseDir` absoluto.
- El host es `spectator.<plataforma>.lol.pvp.net`, puerto **8080**, en **HTTP
  plano** (por HTTPS contesta `WRONG_VERSION_NUMBER`, que parece un problema de
  certificados y es solo el protocolo equivocado). Medido el 03-11-2026: las 18
  plataformas de la tabla resuelven y aceptan TCP. `NA2` no existe (DNS
  `gaierror`), por eso no está en `HOSTS`.
- La partida **no se ve hasta que pasa el retardo del espectador (~3 min)**. Antes
  de eso el cliente se abre y se queda sin imagen, que parece un fallo.

### `scripts/espectar.py`: lo mismo, pero depurable

Un `.bat` no se puede depurar: si falla, se cierra. El script hace lo mismo desde
Python con diagnóstico y mensajes de error de verdad.

```
python scripts/espectar.py --diagnostico
python scripts/espectar.py --pro Caps [--esperar] [--sin-lanzar]
python scripts/espectar.py --partida 5651554245 --clave <32 chars> --region NA1
python scripts/espectar.py --bat --pro Caps
```

Lo que el diagnóstico destapó y que estaba mal:

- **`tasklist` no escribe UTF-8** en un Windows en español: manda cp850. Leerlo
  como UTF-8 revienta en el primer acento (`INFORMACIÓN`) y deja la cadena vacía,
  así que la comprobación de procesos contestaba «no está corriendo» **siempre**.
  Ahora `_tasklist()` prueba utf-8, oem, cp850 y cp1252.
- **La API local del cliente se iba por el proxy.** Con VPN o Clash, `urllib`
  manda `https://127.0.0.1:<puerto>` por el proxy y contesta **502 Bad Gateway**:
  parece que el cliente no escucha cuando el que no llega es el proxy. La petición
  va con `ProxyHandler({})`.
- **El `lockfile` se queda** con el puerto de la sesión anterior si el cliente se
  cierra de golpe. Ahora se comprueba que el pid del fichero siga vivo antes de
  fiarse de él.
- Un puuid de otra región contesta `400 Exception decrypting` y tumbaba el script
  con la traza entera; ahora se apunta y se sigue con la siguiente cuenta. Y si
  **todas** fallan, dice «no se pudo comprobar» en vez de «no está en partida»,
  que manda a buscar el problema donde no está.

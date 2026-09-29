# AGENTS.md — Continuidad y entrega de LoLProTrackr

Documento de mano para el **siguiente agente** (o para ti en un futuro). El
proyecto ya tiene mucha base hecha; este archivo fija lo que se hizo, por qué, y
hacia dónde va, para que cualquiera pueda retomar sin re-descubrirlo todo.

> Idioma: el proyecto y el usuario se comunican en español. El código y los
> comentarios internos están en español. Mantenlo así en lo que escribas.

---

## 1. Qué es y hacia dónde va

**LoLProTrackr** es un bot de Discord (nextcord) que avisa cuando un jugador
profesional de LoL entra a SoloQ. 20 ligas, 919 jugadores, barrida cada 30 s.
Tiene capa gratuita + planes de pago (Pro 3,99 €, Elite 8,99 €, definidos en
`tracking/soloq/plans.py`).

**Dirección estratégica acordada con el usuario (sept 2026):** convertir la base
ya funcionante (bot + lógica de notificación + capacidad de leer la API de Riot)
en un activo que **genere tráfico y dinero**, con tres patas:

1. **Web esports "espectacular"** que enseñe los datos en vivo y atraiga
   audiencia (hecho: rediseño `web/` con tema Arena + `socios.html`).
2. **Patrocinios de marcas.** La web avisa en el momento exacto de la
   partida → intención en tiempo real → público cualificado. `socios.html` es la
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
(`index.html` y `socios.html`): no volver a introducirlas, ni como "afiliado de
apuestas", ni como "enlace de apuesta en el aviso", ni en el copy de marketing.
Lo único que puede mencionar apuestas es la **negación** (que no hay), como en
`legal.html` y en la nota legal de `socios.html`. Los números de alcance son
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
- `web/socios.html` — landing de patrocinios de marcas (planes de alianza +
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
- [x] `web/socios.html` (landing de patrocinios de marcas; sin apuestas desde
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
  modelo de afiliado/embed patrocinado descrito en `socios.html`.
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
  `ligas.html` y `api/live.json` responden **404**.
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
| `/subscribe [type] [target]` | Añadir este canal a los avisos (con objetivo, solo eso) |
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
  mantiene el barrido cada 30 s, así que filtrar no cuesta ni una llamada.
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

Ahora `/subscribe [type] [target]`:

| Escribes | Ese canal recibe |
|---|---|
| `/subscribe` | todas las ligas del servidor (como antes) |
| `/subscribe esports` | los partidos de **todas** las ligas |
| `/subscribe esports lck` | **solo** los partidos de la LCK |
| `/subscribe soloq lck` | **solo** el SoloQ de la LCK |
| `/subscribe soloq T1` | **solo** a los jugadores del T1 |
| `/subscribe soloq Elyoya` | **solo** a Elyoya |

**La semántica es «solo», no «además»**: lo que pides es lo que llega. El objetivo
vacío es el reparto de siempre.

Dónde vive cada pieza:

- `tracking/soloq/channel_targets.py` — el almacén (`channel_targets.json`) y los
  dos filtros (`acepta_soloq`, `acepta_esports`). **Un canal sin entrada en el
  fichero no es un canal vacío**: es el reparto de siempre. Esa distinción es lo
  que impide que un fichero ilegible deje sin avisos a quien ya funcionaba.
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

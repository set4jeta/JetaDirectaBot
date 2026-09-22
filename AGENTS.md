# AGENTS.md — Continuidad y entrega de JetaDirectaBot

Documento de mano para el **siguiente agente** (o para ti en un futuro). El
proyecto ya tiene mucha base hecha; este archivo fija lo que se hizo, por qué, y
hacia dónde va, para que cualquiera pueda retomar sin re-descubrirlo todo.

> Idioma: el proyecto y el usuario se comunican en español. El código y los
> comentarios internos están en español. Mantenlo así en lo que escribas.

---

## 1. Qué es y hacia dónde va

**JetaDirectaBot** es un bot de Discord (nextcord) que avisa cuando un jugador
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
- `web/index.html` — landing rediseñada con tema Arena (`class="arena"`),
  `#teams-strip`, `#feed`, `styles-esports.css` y `<script src="live.js" defer>`.
- `web/styles-esports.css` — estilos esports (neón, grid, glow), cargado tras
  `styles.css`. No reemplaza a `styles.css`, lo complementa.
- `web/socios.html` — landing de patrocinios de marcas (planes de alianza +
  nota legal Riot, que excluye expresamente apuestas y juegos de azar + CTA
  mailto `socios@jetadirecta.example`). **Es un fichero a mano: no lo genera
  ningún script**, así que editarlo es seguro.

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
- [ ] **Verificar `generar_web.py`** tras el rediseño: asegurar que la próxima
  regeneración no machaca `index.html`/`socios.html` con la versión anterior
  (el generador escribe index.html; confirmar que respeta el tema Arena o
  integrar el tema en el generador).

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

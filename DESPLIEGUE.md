# DESPLIEGUE.md — Cómo levantar JetaDirectaBot (local, GitHub y Render)

Guía de operación. Todo lo que dice aquí está **medido**, no supuesto: fecha de la
comprobación, 21 de septiembre de 2026. Si algo no coincide con lo que ves,
es que el proyecto ha cambiado y esta guía se ha quedado vieja.

Resumen en una línea: **el bot funciona y arranca en local sin tocar nada; lo
que está roto es la publicación** — GitHub tiene una copia vieja (octubre de
2025) y el trabajo de septiembre de 2026 nunca se ha subido.

---

## 1. Estado verificado hoy

| Qué | Resultado |
|---|---|
| Arranque en local (`python main.py`) | **Funciona.** Conecta a Discord, registra los 22 comandos |
| Tiempo hasta estar operativo | ~40 s (descarga de cuentas y reparación de PUUID en segundo plano) |
| Barrida de partidas | 129 cuentas, **2,9 s por pasada**, 0 errores |
| Jugadores en memoria | 508 |
| PUUIDs | 537 correctas / 2 no halladas sobre 539 cuentas (`accounts.json`) |
| Fugas de memoria | **Causa raíz identificada y arreglada** (ver §6) |
| Repositorio GitHub | **Copia obsoleta**: 1 solo commit, del 19-10-2025 |
| Trabajo de sept-2026 subido | **No.** 828 ficheros sin commitear, `web/` nunca subido |
| Web pública | `https://set4jeta.github.io/JetaDirectaBot/` sirve el **README**, no la web |

Cómo se comprobó el arranque: se lanzó el bot 3 minutos y 21 segundos con el
`.env` real de esta máquina y se leyó el log. Ese log es la fuente de la tabla.

---

## 2. Encenderlo en tu PC (manual)

Requisitos: el intérprete con las dependencias instaladas y el `.env` en la raíz
(ya está; tiene `RIOT_API_KEY`, `DISCORD_TOKEN`, `LOL_API_KEY`,
`TWITTER_OAUTH_TOKEN`, `FIREBASE_API_KEY`).

```bash
cd "C:/jetabot res 8/JetaDirectaBot"
"C:/Users/Chino/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe" main.py
```

Ese es todo el arranque. Un solo proceso: comprueba la configuración, abre el
puerto de salud, arranca las tareas de fondo y conecta con Discord.

- Para pararlo: **Ctrl+C** (cierre ordenado: vuelca los rangos pendientes y
  cierra las sesiones HTTP).
- Si `python` a pelo no es el intérprete correcto, usa la ruta completa como
  arriba.
- El primer arranque de un equipo limpio descarga cuentas y tarda minutos; los
  siguientes arrancan en segundos porque los ficheros ya están.
- Variables útiles: `LOG_LEVEL=DEBUG` para ver el detalle del tracker,
  `STARTUP_REFRESH=1` para forzar la descarga antes de conectar.

Aviso legal/ético: en local el bot **avisa de verdad** a los canales de Discord
configurados. No es un simulador.

---

## 3. El problema real: qué hay en GitHub

Esto es lo que hay que entender antes de tocar nada.

```
Tu carpeta (esta máquina)                GitHub (set4jeta/JetaDirectaBot)
─────────────────────────                ───────────────────────────────
6 commits, el último del 29-07-2025      1 commit, del 19-10-2025
   + 828 ficheros SIN COMMITEAR            "cambios en background_task"
   = todo el trabajo de sept-2026
                                          NO existe `web/`
                                          NO existe `.github/`
                                          NO existe `AGENTS.md`
                                          SÍ existe `copa/` (ya borrado aquí)
```

Dos cosas, ambas importantes:

1. **Las dos historias no tienen nada que ver.** `git merge-base` dice que no
   hay ancestro común: el repo remoto no es un ancestro de tu carpeta. El
   `main.py` del remoto todavía lanza el bot con `subprocess` y `print()`
   (versión vieja); el tuyo es el reescrito. Comparado, el remoto está **392
   ficheros por detrás**: +37.555 / −42.249 líneas de diferencia.
2. **La web nunca se subió.** Los 82 ficheros de `web/` (2,0 MB, 26 páginas
   HTML) están sin trackear, así que GitHub Pages sigue publicando el README.
   Medido ahora mismo: la raíz responde **200** (es el README pasado por
   Jekyll), `ligas.html` responde **404** y `api/live.json` responde **404**.
   El workflow que lo arregla (`.github/workflows/publicar-web.yml`) también
   está sin subir.

Traducción: **si mañana borras esta carpeta, se pierde el proyecto.** Ese es el
riesgo que hay que cerrar primero, antes que Render.

---

## 4. Subirlo a GitHub

Primero se commitea (ya está hecho, ver §9) y luego se empuja. Como las
historias no están relacionadas, empujar a `main` a secas **falla**; hay que
elegir:

**Ruta A — rama nueva, sin tocar nada de lo que hay (la más segura).**

```bash
git push origin HEAD:refs/heads/produccion
```

No borra nada. Luego, en GitHub → Settings → Branches, se pone `produccion`
como rama por defecto, o se apunta Render a ella. La pega: el workflow de Pages
está configurado para `main`, así que habría que cambiar esa línea.

**Ruta B — sustituir `main` por el código actual (la más limpia).**

Primero se guarda el commit viejo para no perderlo nunca:

```bash
git push origin f7393174b2d21cb66cf8ef537ec9944415f960b1:refs/heads/backup-oct-2025
git push --force-with-lease origin HEAD:main
```

`backup-oct-2025` deja el snapshot antiguo accesible para siempre. Después,
`main` pasa a ser el código bueno y todo lo demás (Render, Pages) sigue
apuntando donde apuntaba.

**Ruta C — lo haces tú.** Se te dan los dos comandos y los pegas.

En cualquiera de las tres hace falta **autenticación**: desde aquí no hay `gh`
instalado ni credenciales guardadas, así que `git push` pide usuario y
contraseña y no puede responder. Opciones: que lo empujes tú, o darme un
**token de acceso personal** (GitHub → Settings → Developer settings → Personal
access tokens → *Fine-grained*, limitado a este repositorio, permiso
`Contents: Read and write`), que se usa una vez y se revoca después.

---

## 5. Montarlo en Render

El repo ya trae `render.yaml` preparado. Hay dos caminos:

**Camino 1 — Blueprint (recomendado).** Render lee `render.yaml` y crea el
servicio con todo configurado, incluidos los huecos de las variables secretas.

1. Render → **New → Blueprint**.
2. Conecta `set4jeta/JetaDirectaBot` y la rama (`main` o `produccion`).
3. Render pide los valores de las variables marcadas con `sync: false`:
   `RIOT_API_KEY` y `DISCORD_TOKEN`. Se pegan ahí (nunca en el repo).
4. **Apply**. El primer build instala `requirements.txt` y arranca.

**Camino 2 — Web Service a mano.** Render ignora `render.yaml`; hay que
rellenar a mano lo mismo:

| Campo | Valor |
|---|---|
| Runtime | Python |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python main.py` |
| Health Check Path | `/` |
| Region | Frankfurt (la API europea; Oregón añade ~120 ms por petición) |

Y en **Environment → Environment Variables**: `RIOT_API_KEY`, `DISCORD_TOKEN`
(las dos obligatorias) y, cuando las tengas, `BOT_INVITE_URL`, `BOT_DONATE_URL`,
`BOT_SOPORTE_URL`, `BOT_WEB_URL`.

Detalles que importan:

- **La versión de Python la fija `.python-version`** (3.13, la que se ha
  probado). Sin ese fichero, Render usa **3.14.3** por defecto en servicios
  creados a partir del 11-02-2026, y el proyecto no se ha probado ahí.
- **`PORT` no se toca**: Render lo inyecta y `keep_alive.py` lo respeta.
- **`render.yaml` usa `runtime: python`**, que es la clave actual; la que había
  antes (`env: python`) está obsoleta.
- Los valores de `plan` válidos son `free`, `0.5c-512mb`, `1c-2g`… (no existe
  un plan llamado `starter`).
- Un servicio creado a mano **no** lee `render.yaml`: si cambias el fichero y no
  ves efecto, es por eso.

---

## 6. La memoria: qué pasó y qué falta

**Qué se arregló.** La fuga tenía causa raíz identificada y está documentada en
la cabecera de `apis/dpm_api.py`:

1. Cada llamada creaba un `cloudscraper.create_scraper()` nuevo (sesión TLS,
   pool de conexiones y fingerprint completos) y nadie las cerraba.
   `!historial` hacía cientos. → Ahora hay un scraper por hilo, reutilizado.
2. Cada función de `aiohttp` abría su propio `ClientSession`. → Una sola sesión
   con conector limitado.
3. `!historial` lanzaba `asyncio.gather` sobre todos los jugadores y todas sus
   cuentas sin límite. → Semáforo que acota la concurrencia.
4. `print()` volcando respuestas JSON enteras al log. → Logging con niveles.

Además: `DPM_SLIM_HISTORY=1` baja la caché de ~27 MB a ~3 MB, `RANK_DATA_MAX_*`
pone tope al almacén de rangos, y `RANK_FLUSH_INTERVAL` evita reescribir 316 kB
en cada escritura.

**Qué NO está hecho.** No hay instrumentación de memoria ni reinicio automático.
`bugs y mejoras.txt` pide literalmente "reinicia el bot cuando se llena en
Render", y eso no existe todavía: no hay nada que lea el RSS del proceso ni que
lo reinicie al pasar un umbral. Si quieres cerrarlo de verdad, el sitio es una
tarea de fondo en `core/background_tasks.py` que lea `/proc/self/statm` (en
Linux no hace falta `psutil`, que no está en `requirements.txt`) y salga con
código distinto de cero al superar el umbral; Render lo levanta solo.

**Los números del plan gratuito** (leídos de la documentación de Render):

| | Free | Pago mínimo (0.5c-512mb) |
|---|---|---|
| CPU / RAM | **0,1 CPU / 512 MB** | 0,5 CPU / 512 MB |
| Se duerme a los 15 min sin tráfico entrante | **Sí** | No |
| Disco persistente | No | Sí |
| Acceso SSH | No | Sí |
| Horas incluidas | 750/mes (los dormidos no consumen) | — |

---

## 7. Lo que se pierde en cada despliegue (leer antes de pagar nada)

El sistema de ficheros de Render es **efímero**: todo lo que el bot escriba se
borra en cada despliegue, reinicio **y cada vez que se duerme**.

El bot guarda su estado en JSON **dentro de la carpeta del código**
(`tracking/soloq/`):

| Fichero | Qué guarda | ¿Sobrevive a un despliegue? |
|---|---|---|
| `notify_config.json` | Qué servidores/canales reciben avisos | **Sí** — está commiteado, vuelve del repo |
| `accounts.json` / `accounts_from_teams.json` | Cuentas seguidas | Sí, se regeneran solas (el bot las descarga si faltan) |
| `users_config.json` | Suscripciones de avisos por DM | **No** — se pierden |
| `plans_users.json` | Planes de pago asignados a mano | **No** — se pierden |
| `announced_games.json` | Partidas ya anunciadas (anti-duplicados) | **No** |

Consecuencias prácticas:

- Los cambios hechos con `/setchannel` en producción **se pierden** al
  redesplegar; el repo devuelve la versión commiteada (los 2 servidores
  actuales). Para que un canal nuevo sea permanente, hay que commitear el
  `notify_config.json`.
- Un cliente con plan de pago asignado a mano perdería el plan al redesplegar.
- **No se puede añadir un disco de Render tal cual.** El disco se monta como una
  carpeta que *tapa* lo que haya debajo: montarlo en `tracking/soloq` escondería
  también `leagues.py`, `plans.py` y `notifier.py`, y el bot no arrancaría. Para
  tener persistencia de verdad hay que mover esos JSON a una carpeta aparte
  (p. ej. `datos/`) y que las rutas se lean de una variable de entorno. **Está
  sin hacer** y es el trabajo previo a cualquier plan de pago.

---

## 8. La web (GitHub Pages)

- La web es estática y no necesita servidor: Pages la sirve gratis.
- Está en `web/`, y Pages configurado como "deploy from a branch" **sirve la
  raíz del repo, no una subcarpeta** → por eso hoy se ve el README.
- El arreglo ya está escrito en `.github/workflows/publicar-web.yml`: publica
  `web/` como artefacto de Pages, así la raíz del sitio pasa a ser
  `web/index.html` y todos los enlaces internos resuelven. Incluye
  `touch web/.nojekyll`, sin el cual Pages pasa el artefacto por Jekyll y puede
  romper rutas de `img/`.
- **Falta un paso que solo puedes hacer tú**: GitHub → **Settings → Pages →
  Source → GitHub Actions**. Ningún fichero del repo cambia ese ajuste.
- `ads.txt` (requisito de AdSense) tiene que estar en la **raíz del dominio**,
  o sea `https://set4jeta.github.io/ads.txt`, que **no es este repositorio**:
  es el repo `set4jeta.github.io`, que hoy no existe. Sin él AdSense marca
  "earnings at risk". Alternativa: dominio propio (~10 €/año).
- Previsualizar en local: `cd web && python -m http.server 8899 --bind 127.0.0.1`
  → `http://127.0.0.1:8899/`. Es loopback: **no** es accesible desde fuera.
- El feed "en vivo" se llena con `python scripts/bridge_web.py`, que lee
  `avisos.jsonl` y escribe `web/api/live.json`. Hoy **hay que lanzarlo a mano**;
  que el bot lo regenere solo al publicar un aviso sigue pendiente.

---

## 9. Qué necesito de ti

1. **Autenticación para el push**: o lo empujas tú, o me das un token
   fine-grained limitado a este repositorio (`Contents: Read and write`) y lo
   revocas después.
2. **Decisión de rama**: Ruta A (rama nueva `produccion`, no borra nada) o
   Ruta B (sustituir `main`, guardando antes el snapshot en `backup-oct-2025`).
3. **Decisión de plan en Render**: el gratuito se duerme a los 15 minutos y el
   bot deja de avisar. Para que esté siempre despierto hace falta el plan de
   0,5 CPU/512 MB, o poner un monitor externo (UptimeRobot, cron-job.org) que
   haga una petición cada 5–10 minutos — con el aviso de que Render puede
   suspender un servicio gratuito que genera mucho tráfico de salida, y este bot
   hace ~130 llamadas a Riot cada 30 segundos.
4. **Los 4 enlaces del bot** (`BOT_INVITE_URL`, `BOT_DONATE_URL`,
   `BOT_SOPORTE_URL`, `BOT_WEB_URL`): sin `BOT_INVITE_URL` el botón "Añadir a
   Discord" de la web sale apagado. Es el único enlace que convierte.
5. **Riot API key de producción**: la de desarrollo caduca cada 24 h y da
   20 req/s; la de producción da 500 req/10s y es la que hace falta para seguir
   20 ligas.
6. **Ajuste manual en GitHub**: Settings → Pages → Source → GitHub Actions.

---

## 10. Anexo: los 429 que aparecieron en la prueba

Durante los 3 minutos de prueba el log mostró avisos de límite de peticiones de
Riot:

```
WARNING | apis.riot_client | 429 en spectator-v5.active-games (tipo=server).
        Retry-After=18. Esperando 18.0s
WARNING | apis.riot_client | 429 en account-v1.by-riot-id (tipo=method).
        Retry-After=1
```

No rompen nada (el cliente reintenta y respeta `Retry-After`), pero son la señal
de dos cosas: `TRACKER_CONCURRENCY=12` con 129 cuentas cada 30 s aprieta el cupo,
y `spectator-v5` no tiene límites conocidos por el limitador (`app=? método=?`),
así que sus 429 los descubre por las malas. Con la clave de desarrollo
(20 req/s) es peor. Si vuelven a aparecer en producción, bajar
`TRACKER_CONCURRENCY` a 6–8 es el primer botón.

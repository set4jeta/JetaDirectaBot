# DESPLIEGUE.md — Cómo levantar JetaDirectaBot (local, GitHub y Render)

Guía de operación. Todo lo que dice aquí está **medido**, no supuesto.
Última revisión: **22 de septiembre de 2026** (la primera versión era del 21 y
tenía dos cosas mal: daba por hecho que la clave de Riot era de desarrollo, y
explicaba el tema del disco de forma que parecía que el bot no arrancaría. Ambas
están corregidas en §6, §7 y §10).

Resumen en una línea: **el bot funciona y arranca en local sin tocar nada; lo
que está roto es la publicación** — GitHub tiene una copia vieja (octubre de
2025) y el trabajo de septiembre de 2026 nunca se ha subido.

---

## 1. Estado verificado

| Qué | Resultado |
|---|---|
| Arranque en local (`python main.py`) | **Funciona.** Conecta a Discord, registra los 22 comandos |
| Tiempo hasta estar operativo | ~40 s (la descarga de cuentas y la reparación de PUUID van en segundo plano) |
| Barrida de partidas | 129 cuentas, **2,9 s por pasada**, 0 errores |
| Jugadores en memoria | 508 |
| PUUIDs | 537 correctas / 2 no halladas sobre 539 cuentas (`accounts.json`) |
| Clave de Riot del `.env` | **Producción**, verificado: `X-App-Rate-Limit: 500:10,30000:600` |
| Fugas de memoria | **Causa raíz identificada y arreglada** (ver §6) |
| Repositorio GitHub | **Copia obsoleta**: 1 solo commit, del 19-10-2025 |
| Trabajo de sept-2026 subido | **No.** Ahora ya está commiteado en 4 commits, listo para empujar |
| Web pública | `https://set4jeta.github.io/JetaDirectaBot/` sirve el **README**, no la web |

Cómo se comprobó el arranque: se lanzó el bot 3 minutos y 21 segundos con el
`.env` real de esta máquina y se leyó el log.

---

## 2. Encenderlo en tu PC (manual)

Requisitos: el intérprete con las dependencias y el `.env` en la raíz (ya está,
con las 5 claves: Riot, Discord, LoL, Twitch, Firebase).

```bash
cd "C:/jetabot res 8/JetaDirectaBot"
"C:/Users/Chino/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe" main.py
```

Ese es todo el arranque: un solo proceso. Comprueba la configuración, abre el
puerto de salud, arranca las tareas de fondo y conecta con Discord.

- Para pararlo: **Ctrl+C** (cierre ordenado: vuelca los rangos pendientes y
  cierra las sesiones HTTP).
- Si `python` a pelo no es el intérprete correcto, usa la ruta completa.
- El primer arranque en un equipo limpio descarga cuentas y tarda minutos; los
  siguientes arrancan en segundos.
- Variables útiles: `LOG_LEVEL=DEBUG` para ver el detalle del tracker,
  `STARTUP_REFRESH=1` para forzar la descarga antes de conectar.

El `.env` es **solo para local**. En Render no existe (está en `.gitignore`):
allí las claves se ponen en el panel (§5).

---

## 3. El problema real: qué hay en GitHub

```
Tu carpeta (esta máquina)                GitHub (set4jeta/JetaDirectaBot)
─────────────────────────                ───────────────────────────────
6 commits, el último del 29-07-2025      1 commit, del 19-10-2025
   + 4 commits nuevos (sept-2026)          "cambios en background_task"
                                          NO existe `web/`
                                          NO existe `.github/`
                                          NO existe `AGENTS.md`
                                          SÍ existe `copa/` (ya borrado aquí)
```

1. **Las dos historias no tienen nada que ver.** `git merge-base` dice que no
   hay ancestro común: el repo remoto no es un ancestro de tu carpeta. Su
   `main.py` todavía lanza el bot con `subprocess` y `print()` (versión vieja).
   Comparado, el remoto está **392 ficheros por detrás**: +37.555 / −42.249
   líneas de diferencia.
2. **La web nunca se subió.** Los 82 ficheros de `web/` (2,0 MB, 26 páginas) no
   estaban en git, así que Pages sigue publicando el README. Medido: la raíz
   responde **200** (es el README pasado por Jekyll), `ligas.html` responde
   **404** y `api/live.json` responde **404**. El workflow que lo arregla
   (`.github/workflows/publicar-web.yml`) tampoco estaba subido.

---

## 4. El push (esto es lo único que falta para publicar)

Ya está todo commiteado en 4 commits nuevos sobre `9b0f57d`. Como las historias
no están relacionadas, **un `git push` normal se rechaza** ("non-fast-forward").
Hay que hacer una de estas dos:

**Opción 1 — rama nueva, no toca nada de lo que hay (lo más seguro).**

```bash
git push origin HEAD:refs/heads/produccion
```

Después, en GitHub → Settings → Branches, se pone `produccion` como rama por
defecto, o se apunta Render a ella. Pega: el workflow de Pages está configurado
para `main`, así que habría que cambiar esa línea.

**Opción 2 — sustituir `main` por el código actual (lo más limpio).**

Primero se guarda el commit viejo para no perderlo nunca:

```bash
git push origin f7393174b2d21cb66cf8ef537ec9944415f960b1:refs/heads/backup-oct-2025
git push --force-with-lease origin HEAD:main
```

`backup-oct-2025` deja el snapshot antiguo accesible para siempre. Después
`main` pasa a ser el código bueno y todo lo demás (Render, Pages) sigue
apuntando donde apuntaba.

**Credenciales.** GitHub no acepta la contraseña de la cuenta por HTTPS. Si
Windows tiene el *Git Credential Manager*, se abre una ventana del navegador y
se inicia sesión ahí. Si pide usuario y contraseña, la contraseña tiene que ser
un **token de acceso personal** (GitHub → Settings → Developer settings →
Personal access tokens → *Fine-grained*, limitado a este repositorio, permiso
`Contents: Read and write`).

**Aviso.** Si el servicio de Render tiene `autoDeploy` activo (lo normal),
**en cuanto se empuje, Render redespliega solo** con el código nuevo. No hay que
hacer nada más en el panel.

---

## 5. Render

**Lo primero, la duda importante: Render no lee el `.env`.** Ese fichero está en
`.gitignore` y no existe en el repositorio. Las claves se pegan a mano en el
panel del servicio: **Environment → Environment Variables**. Eso es lo que te
pedía Render al montarlo y lo único que hay que configurar a mano.

**Los datos van solos.** Los ficheros que el bot necesita para arrancar
(`accounts.json`, `accounts_from_teams.json`, `Infoplayers/`, `puuid_cache.json`,
`notify_config.json`) **están en el repositorio**, así que Render los tiene al
clonar. No hay que subir nada a mano. Y si faltara alguno, el propio bot lo
descarga al arrancar (`main.py` detecta que está vacío y lo siembra).

**Tu servicio ya existe.** No hay que recrear nada: empuja y Render
redespliega el mismo servicio con las variables que ya tenía puestas. Los
valores de siempre son los mismos (build `pip install -r requirements.txt`,
start `python main.py`, plan free).

Si algún día hay que crearlo desde cero:

| Campo | Valor |
|---|---|
| Runtime | Python |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python main.py` |
| Health Check Path | `/` |
| Región | `frankfurt` (solo se puede elegir al crear; **no se cambia después**) |

Detalles que importan:

- **La versión de Python la fija `.python-version`** (3.13, la que se ha
  probado) → ver §6.
- **`PORT` no se toca**: Render lo inyecta y `keep_alive.py` lo respeta.
- **`render.yaml` usa `runtime: python`**; la clave que había antes
  (`env: python`) está obsoleta.
- Los valores válidos de `plan` son `free`, `0.5c-512mb`, `1c-2g`… (no existe un
  plan llamado `starter`).
- Un servicio creado a mano **no** lee `render.yaml`: si cambias el fichero y no
  ves efecto, es por eso. Y si sincronizas un Blueprint, Render **conserva** las
  variables que ya tengas puestas aunque no estén en el fichero.

---

## 6. Memoria, Python y el plan gratuito

**La fuga de memoria tenía causa raíz y está arreglada.** Está documentada en la
cabecera de `apis/dpm_api.py`:

1. Cada llamada creaba un `cloudscraper.create_scraper()` nuevo (sesión TLS,
   pool de conexiones y fingerprint completos) y nadie las cerraba.
   `!historial` hacía cientos. → Ahora hay un scraper por hilo, reutilizado.
2. Cada función de `aiohttp` abría su propio `ClientSession`. → Una sola sesión
   con conector limitado.
3. `!historial` lanzaba `asyncio.gather` sobre todos los jugadores y todas sus
   cuentas sin límite. → Semáforo que acota la concurrencia.
4. `print()` volcando respuestas JSON enteras al log. → Logging con niveles.

Además: `DPM_SLIM_HISTORY=1` baja la caché de ~27 MB a ~3 MB, `RANK_DATA_MAX_*`
pone tope al almacén de rangos y `RANK_FLUSH_INTERVAL` evita reescribir 316 kB
en cada guardado.

**Lo que NO está hecho:** no hay instrumentación de memoria ni reinicio
automático. `bugs y mejoras.txt` pide literalmente "reinicia el bot cuando se
llena en Render" y eso no existe todavía: nada lee el RSS del proceso ni lo
reinicia al pasar un umbral. Se puede cerrar sin `psutil` (no está en
`requirements.txt`): una tarea de fondo que lea `/proc/self/statm` y salga con
código distinto de cero al superar el umbral; Render lo levanta solo.

**La versión de Python.** Render cambió el valor por defecto: los servicios
creados a partir del **11-02-2026** usan **3.14.3**; los creados antes, 3.13.4
(entre 12-06-2025 y 11-02-2026) o 3.11.x (antes de eso). El bot se ha probado en
3.13, así que se ha añadido **`.python-version` con `3.13`**: Render respeta ese
fichero y usa el último 3.13.x. No hay que hacer nada más, y **no**, el programa
no se rompe por esto: solo había que decirle a Render qué versión usar.

**El plan gratuito** (leído de la documentación de Render):

| | Free | Pago mínimo (0.5c-512mb) |
|---|---|---|
| CPU / RAM | **0,1 CPU / 512 MB** | 0,5 CPU / 512 MB |
| Se duerme a los 15 min sin tráfico entrante | **Sí** | No |
| Disco persistente | No | Sí |
| Acceso SSH | No | Sí |
| Horas incluidas | 750/mes (los dormidos no consumen) | — |

**Lo del UptimeRobot resuelve el sueño**: una petición cada 5–10 minutos a
`https://<servicio>.onrender.com/` cuenta como tráfico entrante y el servicio no
se duerme. Es como ha funcionado hasta ahora y es una solución válida. Lo único
que no cubre el monitor es el otro aviso de la documentación: Render puede
suspender un servicio gratuito que **genera** mucho tráfico de salida, y este
hace ~130 llamadas a Riot cada 30 segundos. Si eso pasara, el log del panel lo
diría.

---

## 7. Lo que se pierde en cada despliegue (y por qué el disco no se puede poner "tal cual")

**El bot funciona perfectamente sin disco persistente.** Así ha estado un año y
no hay nada roto. El disco solo serviría para una cosa: que sobreviva el estado
que el bot escribe en tiempo de ejecución. El sistema de ficheros de Render es
**efímero**: se borra en cada despliegue, en cada reinicio y también cada vez
que el servicio se duerme.

| Fichero (en `tracking/soloq/`) | Qué guarda | ¿Sobrevive? |
|---|---|---|
| `notify_config.json` | Qué servidores/canales reciben avisos | **Sí** — está commiteado, vuelve del repo |
| `accounts.json` / `accounts_from_teams.json` | Cuentas seguidas | Sí, se regeneran solas |
| `users_config.json` | Suscripciones de avisos por DM | **No** — se pierden |
| `plans_users.json` | Planes de pago asignados a mano | **No** — se pierden |
| `announced_games.json` | Partidas ya anunciadas (anti-duplicados) | **No** |

Consecuencias prácticas:

- Los cambios hechos con `/setchannel` en producción se pierden al redesplegar;
  el repo devuelve la versión commiteada (los 2 servidores actuales). Para que
  un canal nuevo sea permanente, hay que commitear el `notify_config.json`.
- Un cliente con plan de pago asignado a mano perdería el plan al redesplegar.

**Y aquí está el detalle del disco**, que la primera versión de esta guía
explicaba fatal: **el bot no arrancaría solo en el caso de que alguien monte un
disco en `tracking/soloq`**. Un disco de Render se monta como una carpeta y
**tapa** lo que hubiera debajo. Montarlo en `tracking/soloq` escondería también
`leagues.py`, `plans.py` y `notifier.py`, y el bot fallaría al importar. Sin
disco, todo esto es irrelevante y el bot arranca igual que siempre. Para tener
persistencia de verdad hay que mover antes esos JSON a una carpeta aparte
(por ejemplo `datos/`) y que las rutas se lean de una variable de entorno.
**Está sin hacer**, y es el trabajo previo a cualquier plan de pago.

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
  `avisos.jsonl` y escribe `web/api/live.json`. Hoy hay que lanzarlo a mano; que
  el bot lo regenere solo al publicar un aviso sigue pendiente.

---

## 9. Qué falta de ti

1. **El push** (§4). Dos comandos; el `git push` a secas se rechaza.
2. **Un clic**: GitHub → Settings → Pages → Source → **GitHub Actions**.
3. **Los 4 enlaces del bot** (`BOT_INVITE_URL`, `BOT_DONATE_URL`,
   `BOT_SOPORTE_URL`, `BOT_WEB_URL`) en Environment del panel. Sin
   `BOT_INVITE_URL` el botón "Añadir a Discord" de la web sale apagado: es el
   único enlace que convierte.
4. **Decidir si algún día quieres persistencia** (§7). No hace falta ahora.

La clave de Riot ya es la de producción, así que de ahí no falta nada.

---

## 10. Anexo: los 429 de la prueba (y por qué no son culpa de la clave)

En la prueba salieron avisos de límite de peticiones de Riot:

```
WARNING | apis.riot_client | 429 en spectator-v5.active-games (tipo=server).
        Retry-After=18. Esperando 18.0s
WARNING | apis.riot_client | 429 en account-v1.by-riot-id (tipo=method).
        Retry-After=1 · app=1:10,1001:600 método=1000:60
```

No rompen nada (el cliente reintenta y respeta `Retry-After`), y **no son
síntoma de clave de desarrollo**. Los números `app=` y `método=` que imprime el
log son los **consumidos** (`X-App-Rate-Limit-Count`), no los límites: 1001
peticiones usadas en la ventana de 600 s, cuando el tope de la clave de
producción es **30.000**. Estaba usando el 3 % de su cupo.

Las dos causas reales son otras: `tipo=server` significa que el 429 lo genera el
propio servicio de Riot (el de espectador suele ir cargado), y `tipo=method` es
límite por endpoint. La explicación más probable de que aparecieran tantos juntos
es que **el bot de Render seguía corriendo con la misma clave mientras yo
arrancaba el de aquí**: dos instancias compartiendo un cupo. Si vuelven a salir
en producción con una sola instancia, el primer botón es bajar
`TRACKER_CONCURRENCY` de 12 a 6–8.

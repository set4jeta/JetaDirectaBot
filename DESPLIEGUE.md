# DESPLIEGUE.md — cómo se publica y se opera LoLProTrackr

Guía de operación. `AGENTS.md` es el documento de continuidad (qué se hizo y por
qué); esto es el **cómo**: arrancar, subir, desplegar, y qué hacer cuando algo se
cae.

> **Estado de este documento (29-09-2026).** Las secciones §1 a §7 recogen lo que
> ya estaba escrito en `render.yaml` y en `AGENTS.md`; se han juntado aquí porque
> `AGENTS.md` las referenciaba y el fichero no existía. La §8 es nueva y es la
> importante: el bot estuvo **caído 3 días** por ancho de banda y ahora mismo es
> la única forma de que eso no se repita sin enterarse.

---

## 1. Qué hay desplegado y dónde

| Entorno | Dónde | Público |
|---|---|---|
| Local | `http://127.0.0.1:8899/` (web) | **No** — loopback |
| Producción (bot) | Render, servicio `discord-bot` | Sí |
| Producción (web) | `https://set4jeta.github.io/JetaDirectaBot/` | Sí — GitHub Pages |

La **web** y el **bot** son dos despliegues distintos y no dependen el uno del
otro:

- La web es estática y la publica **GitHub Pages** desde la rama `main`. No hay
  servidor ni build: son ficheros.
- El bot corre en **Render** como servicio web (necesita un puerto abierto;
  `keep_alive.py` responde `Bot is alive!` en `/`).

---

## 2. Arrancar en local

```bash
# El intérprete del proyecto
PY="C:/Users/Chino/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe"

# El bot
"$PY" main.py

# La web (para verla antes de publicar)
cd web && "$PY" -m http.server 8899 --bind 127.0.0.1
```

Regenerar la web y comprobarla:

```bash
"$PY" scripts/generar_web.py --fecha AAAA-MM-DD
"$PY" scripts/test_web.py          # debe dar 0 fallos
```

---

## 3. Subir el código

```bash
git push origin main
```

El repo es `https://github.com/set4jeta/JetaDirectaBot.git`.

> **El repositorio sigue llamándose `JetaDirectaBot`** aunque el producto sea
> LoLProTrackr. No es un descuido: la URL de GitHub Pages lleva el nombre del
> repo, y **todas las canónicas del sitio apuntan ahí**. Cambiar el nombre del
> repo sin cambiar `BOT_WEB_URL` (y regenerar) rompería el SEO entero. Si algún
> día se renombra: renombrar en GitHub → poner la URL nueva en `BOT_WEB_URL` →
> regenerar. Son tres pasos y ninguno se puede saltar.

---

## 4. Crear el servicio en Render (paso a paso)

Esto es lo que hay que hacer con una **cuenta nueva**:

1. **New → Web Service** y conectar el repositorio de GitHub.
2. Nombre del servicio: **`discord-bot`**. El `render.yaml` dice que Render
   identifica cada servicio por su `name`, así que si se pone otro se crea un
   servicio **nuevo y duplicado** (dos bots conectados, dos facturas).
3. Runtime **Python**, plan **Free**.
4. Build command: `pip install -r requirements.txt`
5. Start command: `python main.py`
6. Health check path: `/`
7. **Environment → Environment Variables**: pegar las de §5. Como mínimo
   `RIOT_API_KEY` y `DISCORD_TOKEN`, o el bot sale con código 1.
8. Poner **UptimeRobot** (o cron-job.org) apuntando a
   `https://<servicio>.onrender.com/` cada 5–10 minutos. Sin eso el bot **se
   duerme a los 15 minutos sin tráfico entrante** y deja de avisar: un bot de
   Discord no recibe tráfico entrante, así que se duerme solo.

La región se puede elegir **solo al crear** el servicio y no se puede cambiar
después. `frankfurt` es mejor que la de por defecto: el bot vive de la API
europea y de dpm.lol, y la latencia se paga en cada una de las miles de
peticiones de cada pasada.

---

## 5. Variables de entorno

Render **no lee el `.env`** (está en `.gitignore`). Las variables van en
**Environment → Environment Variables** del panel.

**Obligatorias** (sin ellas el bot no arranca y lo dice en el log):

| Variable | Qué es |
|---|---|
| `RIOT_API_KEY` | clave de producción (500 req/10 s, 30 000 req/10 min) |
| `DISCORD_TOKEN` | token del bot en el portal de desarrolladores |

**Recomendadas** (salen en `/help`, `/premium` y en la web):

| Variable | Qué es |
|---|---|
| `BOT_NOMBRE` | `LoLProTrackr` |
| `BOT_INVITE_URL` | el botón «Añadir a Discord». Sin esto sale apagado |
| `BOT_WEB_URL` | `https://set4jeta.github.io/JetaDirectaBot/` |
| `BOT_DONATE_URL` | `https://ko-fi.com/lolprotrackr` |
| `BOT_SOPORTE_URL` | servidor de soporte |

**Opcionales:** `LOL_API_KEY`, `FIREBASE_API_KEY`, `TWITTER_OAUTH_TOKEN`,
`LOG_LEVEL`, `GITHUB_TOKEN` (para el estado, ver §7), `EGRESS_PRESUPUESTO_MB`
(ver §8). El listado completo y comentado está en `env.example`.

---

## 6. El plan gratuito: qué implica

- **0,1 CPU / 512 MB.** Es poco: por eso el código evita trabajo por aviso
  (imágenes memorizadas, embed cacheado por idioma en vez de por servidor…).
- **Se duerme a los 15 minutos sin tráfico entrante.** Se resuelve con el
  monitor externo de §4.
- **El sistema de ficheros es efímero.** Lo que el bot escriba se pierde en cada
  despliegue, en cada reinicio y cada vez que se duerme. Ver §7.
- **5 GB de ancho de banda de salida al mes.** Es el límite que tumbó el bot. Ver
  §8, que es la sección que hay que leer.

---

## 7. Persistencia y estado

El disco es efímero, así que el estado que no se puede reconstruir se sube a una
**rama aparte** del repositorio (`estado`), no a `main`: así no dispara el
despliegue automático (sería un bucle: subir estado → redesplegar → reiniciar →
volver a subir). Lo hace `core/estado_remoto.py` cada 5 minutos si algo cambió.

Lo que se guarda: `users_config.json`, `announced_games.json`,
`notify_config.json`, `plans_users.json`, `puuid_cache.json` y `egress.json`
(el contador de §8).

Los ficheros **grandes y reconstruibles** (`accounts_from_teams.json`,
`accounts.json`, `ranked_data.json`) **no** se suben: daría commits enormes cada
5 minutos.

Sin `GITHUB_TOKEN` no se hace nada: el bot funciona igual, solo que el estado se
pierde al reiniciar.

---

## 8. Ancho de banda: el incidente del 29-09-2026

**Lo que pasó.** Render suspendió el workspace y el bot estuvo **caído 3 días
40 minutos**. El aviso era:

> *You've used the 5 GB of free bandwidth in your Hobby workspace.*

**La causa no fue un fallo del código.** En **abril de 2026 Render bajó el ancho
de banda incluido en el plan Hobby de 100 GB a 5 GB** —un recorte de 20 veces—.
El bot no cambió; cambió el límite, y el consumo que llevaba un año siendo
inofensivo pasó a ser excesivo.

**Qué gastaba ese ancho de banda.** Render cuenta solo la **salida**, y en el bot
la salida eran los adjuntos: en **cada aviso** subía a Discord la foto del
jugador, el logo del equipo y el `spectate_lol.bat`. Y lo hacía **una vez por
destinatario**, porque el mismo embed se reenvía a cada servidor y a cada canal
y Discord no deduplica nada. Un aviso a tres servidores con dos canales cada uno
son seis subidas de los mismos ~35 kB. Con eso, 5 GB se van antes de lo que
parece.

### El arreglo

Las dos imágenes pasaron a ser **URLs** en vez de adjuntos:

- La foto: `https://dpm.lol/esport/players/<nombre>.webp`
- El logo: `https://dpm.lol/esport/teams/<tricode>.webp`

**No cambia nada de lo que se ve**, y es verificable: esas URLs son exactamente
de donde el bot **descargaba** el fichero para adjuntarlo
(`ui/player_image_utils.py`), así que son los mismos bytes. Los logos incluso
salen más nítidos, porque el fichero local estaba reducido a 200 px y el remoto
es el original.

El `.bat` **sigue adjunto** y no puede dejar de estarlo: lleva la clave de cifrado
de esa partida concreta, así que es distinto cada vez y no puede ser un enlace.
Son 1,1 kB, o sea nada al lado de los ~35 kB de antes.

El resultado: el consumo baja a alrededor del **15 %** de lo que era.

### La cadencia: el gasto que quedaba

Con las imágenes fuera, lo que quedaba gastando era **el sondeo de Riot**, no los
avisos. Medido el 18-10-2026 con 289 cuentas barridas cada 30 s: **~64 MB/h**
(~1,5 GB/día), o sea el cupo entero en 3-4 días. Los avisos de todo septiembre
habían sido 5 MB.

Se subió `CHECK_GAMES_INTERVAL` de **30 s a 240 s** (variable de entorno de
Render, sin tocar código). Ocho veces menos peticiones para el mismo dato:

- la pasada sigue tardando lo mismo (~20 s con las cachés calientes), así que
  **sobra margen**: antes ocupaba el 97 % del intervalo y el bot ya avisaba de
  que con una liga más no cabría;
- el precio es la **latencia**: un aviso puede llegar hasta 4 minutos más tarde.
  Para un aviso de «ha entrado a SoloQ» es asumible, y es el trato que eligió el
  dueño.

Al desplegarlo se comprobó en el log:

```
Tareas iniciadas | partidas cada 240s
🟢 Partidas SoloQ en curso  cada 240s
```

Con la cadencia nueva las imágenes **no cambian de nada**: van por URL desde
dpm.lol y las sirve Discord, así que no dependen de cuándo se barre. Que siguen
bien lo vigila `scripts/test_embeds_imagenes.py`, que construye el aviso de SoloQ
de verdad y exige foto y logo en `https` y **ningún adjunto**.

### El segundo corte: 29-10-2026, y por qué una cifra fija no sirve

Con 240 s el bot aguantó del 18 al 29 de octubre y **volvió a caer**: 59 horas
suspendido por cuota, con octubre cerrado en **5 445 MB de 5 000** (un 9 % de
más). Desde el corte el consumo fue 0, así que la serie de siete días solo
reflejaba el ritmo previo: **1 743 MB en 109 h = 16 MB/h ≈ 384 MB/día**. Con esa
cadencia, noviembre se habría agotado en **13 días**.

La causa seguía siendo el sondeo, no los avisos — y aquí está la parte que
importa: **el contador de `/health` llevaba congelado en 417 mensajes (1,4 MB)
desde el 20 de octubre**, porque `utils/egress.py` solo contaba lo que se manda a
Discord. La partida grande, las peticiones a la API de Riot, no la contaba nadie.
De ahí que `EGRESS_PRESUPUESTO_MB` no disparara nunca: estaba vigilando el 0,03 %
del gasto.

**La decisión de fondo: la cadencia deja de ser un número.** Un valor fijo
siempre está mal en algún momento del mes:

| cadencia | qué pasa |
|---|---|
| 240 s | agota los 5 GB hacia el día 13 y el proveedor suspende el bot |
| 1 800 s | no se agota nunca, pero el aviso llega con **media hora** de retraso todos los días, también los que sobraban |

Lo que hacía falta no era un número más alto, era **repartir el presupuesto a lo
largo del mes**. Eso es `tracking/soloq/cadencia.py`:

```
coste de una pasada = cuentas sondeadas × bytes por cuenta
margen por hora     = (presupuesto − gastado) ÷ horas hasta fin de mes
intervalo           = 3600 ÷ (margen por hora ÷ coste de una pasada)
```

- Al empezar el ciclo va **rápido**, porque hay margen de sobra.
- Según se gasta, se **estira sola**.
- El último día llega con el presupuesto **justo agotándose**, ni antes ni
  después.
- `bytes_por_cuenta` **se mide**: cada pasada anota lo que gastó de verdad y
  cuántas cuentas miró, y de ahí sale una media móvil. Si el censo crece o Riot
  cambia el tamaño de las respuestas, se entera sola.

Medido con los números de octubre (≈1,16 kB por cuenta), a principio de mes sale:

| cuentas barridas | intervalo |
|---|---|
| 300 | ~3 min |
| 400 | ~4 min |
| 919 (censo entero) | ~9 min |

Y a mitad de mes, con el mismo censo, el doble. Los topes
(`CHECK_GAMES_INTERVAL_MIN` 120 s, `CHECK_GAMES_INTERVAL_MAX` 1 800 s) existen
para que la corrección no se vuelva absurda. Si el presupuesto se agota antes de
fin de mes se pasa a `CHECK_GAMES_INTERVAL_AGOTADO` (3 600 s): **no se apaga**,
porque apagarse es peor que ir despacio.

El cambio va acompañado de lo que lo hace posible: **el sondeo ahora se cuenta**.
`apis/riot_client._request` suma los bytes de cada respuesta al contador del mes
(`egress.registrar_sondeo`), y `/health` enseña el **total** con el desglose. Sin
eso, la cadencia estaría decidiendo a ciegas y el contador seguiría mintiendo.

La prueba que lo vigila es `scripts/test_cadencia.py` (reparto, agotado, topes,
aprendizaje del coste, duración de la pasada y las horas hasta fin de mes en
UTC). El total se ve en `/health`:

```
Salida de red (mes)
2 140 de 4 800 MB (45 %) · 2 130 MB son sondeo de la API · 418 mensajes
```

### dpm.lol bloquea la IP de Render (01-11-2026)

El servicio se reanudó el 01-11 a las 01:31 UTC y el bot estaba **ciego**: 0
cuentas barridas. No era un fallo del código ni de dpm.lol — dpm responde
perfectamente desde una IP doméstica. Era **Cloudflare contestando 403 a la IP
del datacenter**, con los dos transportes:

```
ERROR | apis.transporte_dpm | dpm.lol está BLOQUEANDO esta IP (estados 403/403)
ERROR | accounts_from_leaderboard | euw1: HTTP 403 en la página 1
```

`curl_cffi` (que imita la huella TLS de Chrome) **sí** pasa desde casa; desde
Render ya no. No hay arreglo por código: es la reputación de la IP.

Lo que sí se arregló:

1. **El síntoma deja de ser mudo.** `transporte_dpm` distingue «Cloudflare nos
   cierra la puerta» de «el cliente está mal» y lo dice en ERROR una vez, no
   veinticinco. Y `accounts_from_leaderboard` **corta en la primera plataforma**
   bloqueada en vez de encadenar ocho 403 idénticos que parecían ocho fallos.
2. **El bot no arranca sin censo.** `tracking/soloq/censo.py` guarda una copia
   **compacta** del censo —274 KB frente a 1,7 MB, solo lo que el barrido
   necesita— y viaja en la rama de estado. Si `accounts_from_teams.json` no está,
   `load_tracked_accounts` la lee y el barrido funciona con lo último que se
   supo. Antes, sin censo, el bot se quedaba «encendido» (`/health` 200,
   `/live-games` 200) sin avisar de nada.

Con la copia restaurada, el barrido vuelve en el primer arranque.

**El censo se refresca desde GitHub.** La copia arregla el arranque pero no el
envejecimiento: si nadie puede scrapear dpm.lol desde Render, el censo se queda
congelado. La IP de salida de Render no se puede cambiar, así que el scraping lo
hace un runner de GitHub —que sale por otra IP— y deja el resultado en la rama
`estado`:

| Pieza | Qué hace |
|---|---|
| `.github/workflows/refrescar-rosters.yml` | cron cada hora, `workflow_dispatch` y `push` sobre el scraper; 3 intentos por vuelta |
| `scripts/refrescar_rosters.py` | siembra el censo de la rama, refresca liga por liga, repara PUUID y publica |
| `background_tasks.sincronizar_censo_remoto` | el bot se vuelve a bajar el censo cada `CENSO_SINCRONIZAR_HORAS` |

La IP del runner **no** está limpia: medido el 01-11-2026, de nueve ejecuciones
seguidas una pasó y ocho se comieron un 403 desde la primera petición. Es una
lotería entre ejecuciones, así que el workflow echa muchos números (24 vueltas ×
3 intentos al día) y las vueltas que no hacen falta se saltan solas con
`--si-mas-de-minutos`.

Se publica **solo** el censo compacto (`guardar(solo=estado_remoto.CENSO)`): los
demás ficheros de la rama son contadores vivos del bot y la copia del runner, con
horas de retraso, los haría retroceder. `RIOT_API_KEY` en el workflow es opcional
—sin ella el bot repara los PUUID él solo cada 6 h, porque Riot **no** está
bloqueado—; el `GITHUB_TOKEN` de serie basta.

Para comprobarlo: pestaña Actions → «Refrescar rosters» → Run workflow, o
`git log` de la rama `estado` (un commit «Estado del bot:
tracking/soloq/censo_compacto.json» por publicación).

### La vía que no es lotería: el PC del dueño

Ni Render ni un runner ni un Worker de Cloudflare entran en dpm.lol: los tres
salen por IPs de datacenter. La única que entra siempre es la de casa (200 en el
100 % de las peticiones, medido el 01-11-2026). Así que el refresco que de verdad
funciona es el que se ejecuta en el PC:

| Pieza | Qué hace |
|---|---|
| `scripts/tarea_rosters.py` | envuelve a `refrescar_rosters.py`: candado, log a `logs/tarea_rosters.log` y freno de 5 h |
| tarea programada de Windows | lo lanza cada 6 h con `pythonw.exe` (sin ventana) |

El freno de 5 h tiene que ser **menor** que el intervalo de 6 h o la tarea no
haría nada nunca: es el mismo error que tuvo el workflow de GitHub durante un día
(cron cada 3 h con un freno de 5 h).

Se crea una sola vez, en una consola del usuario (no hace falta administrador):

```powershell
schtasks /Create /TN "LoLProTrackr rosters" /SC HOURLY /MO 6 /ST 20:30 `
  /TR "\"C:\Users\Chino\.workbuddy-ai\binaries\python\envs\default\Scripts\pythonw.exe\" \"C:\jetabot res 8\JetaDirectaBot\scripts\tarea_rosters.py\"" /F
```

Comprobar y borrar:

```powershell
schtasks /Query /TN "LoLProTrackr rosters" /FO LIST /V
schtasks /Delete /TN "LoLProTrackr rosters" /F
```

Si el PC está apagado a la hora de la tarea, esa vuelta se pierde y no pasa
nada: la siguiente intenta igual. Con el workflow de GitHub detrás, la suma de
las dos vías deja el censo al día casi siempre. El resultado de cada vuelta queda
en `logs/tarea_rosters.log` (rotado a 1 MB, 3 copias).

### La red de seguridad

`utils/egress.py` lleva la cuenta del gasto del mes y la publica en `/health`. El
motivo de que exista es que el dueño **se enteró cuando ya estaba suspendido**:
no había ningún sitio donde ver cuánto llevaba consumido.

- Cuenta **las dos cosas**: lo que se manda a Discord y lo que se descarga de la
  API de Riot. El total es lo que se compara con el presupuesto; lo de Discord
  por separado es lo que decide si se puede seguir adjuntando el `.bat`.
- El presupuesto por defecto es **4 800 MB**, por debajo de los 5 GB del
  proveedor. Ya no es un umbral de alarma sino **el objetivo que la cadencia
  reparte**: con 4 000 se dejaba 1 GB sin usar, o sea avisos más lentos de lo
  necesario. Se cambia con `EGRESS_PRESUPUESTO_MB`.
- Avisa en el log al **50 %** y al **80 %**, y esos porcentajes se calculan sobre
  el total.
- Si se agota, **no se deja de avisar**: los avisos salen enteros, solo se deja
  de adjuntar el `.bat` de espectar y el barrido se estira a
  `CHECK_GAMES_INTERVAL_AGOTADO`. Es una degradación, no una caída — que es
  exactamente lo que no supo hacer el proveedor.
- El contador sobrevive a los reinicios porque está en la lista de
  `core/estado_remoto.ARCHIVOS` (§7). Sin eso volvería a cero en cada despliegue
  y no avisaría nunca.

### Qué hacer si vuelve a pasar

1. Mirar `/health` en Discord: dice los MB del mes, el porcentaje **y cuánto es
   sondeo**, que es la partida que se descontrola.
2. Mirar el panel de Render → **Metrics → Bandwidth**, que es la cifra oficial
   (la del bot es una estimación y sirve para la tendencia, no para cuadrar).
3. Si el aviso es por ancho de banda, hay tres salidas: bajar
   `EGRESS_PRESUPUESTO_MB` (o `CHECK_GAMES_INTERVAL_MAX`), **añadir una tarjeta**
   y pagar el exceso (~0,15 $/GB, o sea menos de un dólar por pasarse 5 GB), o
   migrar a otro hosting.
4. Si el aviso es `dpm.lol está BLOQUEANDO esta IP`, mirar primero si
   `DPM_RELAY_URL` está puesta en Render. El relay de Cloudflare
   (`infra/relay-dpm/`, §8) es lo que hace que esa IP deje de importar: desde el
   01-11-2026 entra en dpm.lol donde Render recibe 403. Si el relay está puesto y
   aun así hay 403, es que dpm.lol bloqueó también a Cloudflare; entonces quedan
   la copia del censo (el bot sigue barriendo) y el workflow de GitHub.
   Para comprobarlo sin tocar el bot:
   `CF_API_TOKEN=… python scripts/desplegar_relay.py` termina diciendo si el
   relay responde `200` con `upstream=200` o si dpm.lol le contesta 403.

### Las pruebas que lo vigilan

`scripts/test_salida_red.py` comprueba las dos mitades: que **no se adjunte
ninguna imagen** en un aviso real (es un fallo que no da ningún error y solo se
ve en la factura, tres semanas después) y que el contador funcione.

`scripts/test_cadencia.py` comprueba que el reparto del presupuesto hace lo que
dice: que se estira según se gasta, que respeta los topes, que aprende el coste
real por cuenta, que con el presupuesto agotado sigue barriendo y que las horas
hasta fin de mes se calculan en UTC (el día que importa).

`scripts/test_censo.py` comprueba que el bot puede arrancar sin dpm.lol: que la
copia compacta conserva PUUID y plataforma, que pesa menos de la mitad, que
`load_tracked_accounts` cae en ella y que el censo grande manda cuando existe.

```bash
"$PY" scripts/test_salida_red.py
"$PY" scripts/test_cadencia.py
"$PY" scripts/test_censo.py
```

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

### La red de seguridad

`utils/egress.py` lleva la cuenta de la salida del mes y la publica en
`/health`. El motivo de que exista es que el dueño **se enteró cuando ya estaba
suspendido**: no había ningún sitio donde ver cuánto llevaba consumido.

- El presupuesto por defecto es **4 000 MB**, por debajo de los 5 GB del
  proveedor. El margen es lo que evita la suspensión. Se cambia con
  `EGRESS_PRESUPUESTO_MB`.
- Avisa en el log al **50 %** y al **80 %**.
- Si se agota, **no se deja de avisar**: los avisos salen enteros, solo se deja
  de adjuntar el `.bat` de espectar, y se dice en `/health` y en el log. Es una
  degradación, no una caída — que es exactamente lo que no supo hacer el
  proveedor.
- El contador sobrevive a los reinicios porque está en la lista de
  `core/estado_remoto.ARCHIVOS` (§7). Sin eso volvería a cero en cada despliegue
  y no avisaría nunca.

### Qué hacer si vuelve a pasar

1. Mirar `/health` en Discord: dice los MB del mes y el porcentaje.
2. Mirar el panel de Render → **Metrics → Bandwidth**, que es la cifra oficial
   (la del bot es una estimación y sirve para la tendencia, no para cuadrar).
3. Si el aviso es por ancho de banda, hay tres salidas: bajar
   `EGRESS_PRESUPUESTO_MB`, **añadir una tarjeta** y pagar el exceso
   (~0,15 $/GB, o sea menos de un dólar por pasarse 5 GB), o migrar a otro
   hosting.

### La prueba que lo vigila

`scripts/test_salida_red.py` comprueba las dos mitades: que **no se adjunte
ninguna imagen** en un aviso real (es un fallo que no da ningún error y solo se
ve en la factura, tres semanas después) y que el contador funcione.

```bash
"$PY" scripts/test_salida_red.py
```

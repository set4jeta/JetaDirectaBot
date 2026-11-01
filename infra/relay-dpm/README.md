# Relay de dpm.lol

Un Worker de Cloudflare que pide a `dpm.lol` **desde la red de Cloudflare** y
devuelve la respuesta tal cual. El bot lo usa cuando las peticiones directas
reciben 403.

## Por qué hace falta

dpm.lol está detrás de Cloudflare y contesta **403 a las IPs de datacenter**.
Medido el 01-11-2026, con el mismo código y el mismo cliente:

| Desde | Resultado |
|---|---|
| IP doméstica (curl_cffi) | **200** siempre |
| Render (Frankfurt) | **403** en el 100 % de las peticiones, con los dos transportes |
| Runner de GitHub (Azure) | **403** en todo en 5 de cada 6 ejecuciones |
| **Worker de Cloudflare** | **200**, comprobado con `upstream=200` |

No es un fallo del cliente ni del scraper — es la reputación de la IP, y ni la de
Render ni la de un runner se puede cambiar. La red de Cloudflare es la única que
está *dentro* de la protección, y por eso es la que sirve.

## Estado: desplegado, pero dpm.lol lo desafía

| Dato | Valor |
|---|---|
| Cuenta | `Sebastian.sep1994@gmail.com's Account` (`b81b2776edbfb409bb872fd78ecd816c`) |
| Worker | `jeta-dpm-relay` |
| URL | `https://jeta-dpm-relay.jeta-dpm-relay.workers.dev` |
| Secreto | `RELAY_KEY` (solo en Cloudflare y en Render; **no** en el repo) |

El subdominio `jeta-dpm-relay.workers.dev` es de la cuenta: no hay dominio propio
ni tarjeta de por medio, y el plan es el gratuito (100 000 peticiones al día).

**Lo que pasó de verdad, medido el 01-11-2026.** La primera petición volvió con
`upstream=200` y el JSON real de la ficha de un jugador: el camino existe. Un
rato después, y de forma sostenida, dpm.lol contesta al Worker la página de
desafío de Cloudflare («Just a moment…») en el **100 %** de las peticiones — 25
de 25, y también 3 de 3 reintentos por petición, y en todas las rutas (`/v1/pros`,
`/tierlist`, leaderboards). Las subpeticiones de un Worker salen por un **pool de
IPs compartido** entre todos los clientes de Cloudflare, y ese pool también tiene
mala reputación. Ser Cloudflare no da buena reputación: da una IP compartida.

De ahí que el Worker reintente (la IP cambia entre subpeticiones, así que
reintentar aquí sí puede cambiar el resultado, a diferencia de Render, donde la
IP es fija) y de ahí la **cuarentena** del lado del bot: a los 3 fallos seguidos
deja de intentarlo 30 minutos, para que un relay inútil no encarezca cada ficha
del scraping. Vuelve solo: si dpm afloja, la primera petición tras la cuarentena
entra sin tocar nada.

**Conclusión honesta:** hoy el relay no sustituye al workflow de GitHub. Se deja
montado porque cuesta cero mantenerlo y porque la reputación de ese pool cambia
con los días; si vuelve a servir, el bot lo aprovecha sin que nadie haga nada.

## Probarlo

```bash
curl -s -o /dev/null -w "%{http_code}\n" -D - \
  -H "x-relay-key: LA_CLAVE" \
  "https://jeta-dpm-relay.jeta-dpm-relay.workers.dev/?u=https%3A%2F%2Fdpm.lol%2Fv1%2Fpros%2FFaker"
```

- `200` con `x-relay-upstream: 200` → el relay entra en dpm.lol.
- `403` con cuerpo `forbidden` → falta la clave o no coincide.
- `403` con `x-relay-upstream: 403` → dpm.lol también bloquea a Cloudflare; este
  camino se acabó y hay que volver al workflow de GitHub.

La clave vive fuera del repo (el repo es público). En local está en
`~/relay_key.txt` y en Render en la variable `DPM_RELAY_SECRET`.

## Redesplegar tras tocar `worker.js`

La API de Cloudflare exige el envío **multipart con `main_module`**; si se manda
el fichero a pelo con `Content-Type: application/javascript` lo trata como script
clásico y falla con `Unexpected token 'export'`.

```bash
# con wrangler (lo normal)
cd infra/relay-dpm
npx wrangler deploy

# o por API, sin instalar nada
python scripts/desplegar_relay.py     # pide CF_API_TOKEN por entorno
```

`scripts/desplegar_relay.py` hace lo mismo que el `wrangler deploy` pero sin npm:
sube el módulo, (re)fija `RELAY_KEY` si se le pasa una y activa la ruta
`workers.dev`.

## Conectarlo al bot

En Render, dos variables de entorno:

```
DPM_RELAY_URL=https://jeta-dpm-relay.jeta-dpm-relay.workers.dev
DPM_RELAY_SECRET=la-misma-clave-del-secret-RELAY_KEY
```

Con eso, `apis/transporte_dpm.pedir()` prueba **primero** el relay y solo cae a
curl_cffi y cloudscraper si el relay falla. No hay que tocar código: el bot vuelve
a su rotación horaria de rosters y a bajar los leaderboards de las ocho
plataformas.

En el workflow de GitHub (`refrescar-rosters.yml`) la URL ya va escrita y la clave
se lee de `secrets.DPM_RELAY_SECRET`. Añadirla en *Settings → Secrets and
variables → Actions* convierte el respaldo de «1 de cada 6 ejecuciones» en «a la
primera». Sin el secreto el workflow sigue funcionando como antes.

## Límites y letra pequeña

- Plan free: **100 000 peticiones al día**. El bot hace del orden de 1 500 (una
  pasada de rosters son ~50 fichas por liga, y las ligas van de una en una).
- El Worker **no es un proxy abierto**: sin la clave no responde, y con la clave
  solo habla con `https://dpm.lol` en las rutas `/v1/…` y `/esport/…`. Un proxy
  abierto lo acaba usando cualquiera, y entonces nos bloquean también el relay.
- Esto no es magia: si dpm.lol decide bloquear también a Cloudflare, se acaba el
  atajo. Por eso el workflow de GitHub y la copia del censo siguen ahí.

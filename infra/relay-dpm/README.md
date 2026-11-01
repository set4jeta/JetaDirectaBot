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

No es un fallo del cliente ni del scraper — es la reputación de la IP, y ni la de
Render ni la de un runner se puede cambiar. La red de Cloudflare es la única que
está *dentro* de la protección.

## Despliegue (una vez, 2 minutos)

Hace falta una cuenta gratis de Cloudflare. **No** hace falta dominio propio ni
tarjeta: el Worker sale en `dpm-relay.<algo>.workers.dev`.

```bash
cd infra/relay-dpm
npx wrangler login          # abre el navegador, autoriza
npx wrangler secret put RELAY_KEY   # pega una clave larga y aleatoria
npx wrangler deploy
```

`wrangler deploy` imprime la URL, algo como
`https://dpm-relay.tu-subdominio.workers.dev`.

Para generar la clave:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Probarlo

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "x-relay-key: TU_CLAVE" \
  "https://dpm-relay.tu-subdominio.workers.dev/?u=https%3A%2F%2Fdpm.lol%2Fv1%2Fpros%2FFaker"
```

- `200` → el relay funciona y el bot puede volver a refrescar rosters solo.
- `403` → dpm.lol también bloquea a Cloudflare; entonces este camino no vale y
  hay que quedarse con el workflow de GitHub (o publicar desde un PC).
- `403` con cuerpo `forbidden` → la clave no coincide.

## Conectarlo al bot

En Render, dos variables de entorno:

```
DPM_RELAY_URL=https://dpm-relay.tu-subdominio.workers.dev
DPM_RELAY_SECRET=la-misma-clave-del-secret-RELAY_KEY
```

Con eso, `apis/transporte_dpm.pedir()` prueba **primero** el relay y solo cae a
curl_cffi y cloudscraper si el relay falla. No hay que tocar código ni
redesplegar nada más: el bot vuelve a su rotación horaria de rosters y a bajar
los leaderboards de las ocho plataformas.

## Límites y letra pequeña

- Plan free: **100 000 peticiones al día**. El bot hace del orden de 1 500 (una
  pasada de rosters son ~50 fichas por liga, y las ligas van de una en una).
- El Worker **no es un proxy abierto**: sin la clave no responde, y con la clave
  solo habla con `https://dpm.lol` en las rutas `/v1/…` y `/esport/…`. Un proxy
  abierto lo acaba usando cualquiera, y entonces nos bloquean también el relay.
- Esto no es magia: si dpm.lol decide bloquear también a Cloudflare, se acaba el
  atajo. Por eso el workflow de GitHub y la copia del censo siguen ahí.

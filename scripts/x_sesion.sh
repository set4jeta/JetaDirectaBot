#!/usr/bin/env bash
# Deja twitter-cli autenticado con la sesion de X que el dueno tiene en Opera GX.
#
# Por que hace falta
# ------------------
# twitter-cli busca las cookies solo en Chrome/Edge/Firefox, y el dueno usa
# Opera GX: `twitter status` a secas responde `not_authenticated` (HTTP 401).
# Ademas browser_cookie3.opera_gx() *tampoco* las encuentra por si sola —
# "Failed to find cookies for Opera GX browser" — porque genera la ruta
# `Opera GX Stable\Network\Cookies` y en esta maquina el fichero esta un nivel
# mas abajo, en `Opera GX Stable\Default\Network\Cookies`. Hay que pasarle
# `cookie_file` y `key_file` a mano.
#
# El otro camino, arrancar Opera GX en headless con una copia del perfil y
# hablarle por CDP, esta descartado y medido: el proceso muere en 540 ms y el
# puerto 9333 nunca escucha.
#
# Uso (hay que usar `source`, no ejecutarlo, para que las variables queden):
#     source scripts/x_sesion.sh
#     twitter search "SEO" --limit 30
#
# Las dos variables solo viven en el proceso actual. No se escriben en disco.

VENV="C:/Users/Chino/.workbuddy-ai/binaries/python/envs/default"

_x_cookie() {
  "$VENV/Scripts/python.exe" -c "
import os, sys, browser_cookie3 as b
P = os.path.join(os.environ['APPDATA'], 'Opera Software', 'Opera GX Stable')
cj = b.opera_gx(
    cookie_file=os.path.join(P, 'Default', 'Network', 'Cookies'),
    key_file=os.path.join(P, 'Local State'),
    domain_name='x.com',
)
print({c.name: c.value for c in cj}[sys.argv[1]])
" "$1"
}

export TWITTER_AUTH_TOKEN="$(_x_cookie auth_token)"
export TWITTER_CT0="$(_x_cookie ct0)"
export PATH="$VENV/Scripts:$PATH"

if [ -n "$TWITTER_AUTH_TOKEN" ] && [ -n "$TWITTER_CT0" ]; then
  echo "sesion de X cargada desde Opera GX (auth_token ${#TWITTER_AUTH_TOKEN} car., ct0 ${#TWITTER_CT0} car.)"
else
  echo "ERROR: no se pudieron leer las cookies. ¿Sigue la sesion abierta en Opera GX?" >&2
fi

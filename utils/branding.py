"""Marca y enlaces del producto.

Histórico del descargo de Riot
------------------------------
Aquí vivían `descargo_riot()`, `descargo_corto()` y `sellar_embed()`, que
publicaban el aviso «[producto] no está avalado por Riot Games…» en el pie de
cada embed y en `/help`, porque la política del portal de desarrolladores de Riot
lo pide como texto obligatorio para productos de terceros.

El **22-09-2026 se quitaron por instrucción expresa del dueño**. Leyó el aviso
como un rechazo («¿cómo que no me avala, si me dieron una key donde postulé
esperando meses?») y ordenó eliminarlo. Es su producto y su decisión: la clave de
la API es un permiso de acceso, no un aval, y quien asume el riesgo de dejar de
publicar el aviso es él. No reintroducir estas funciones sin que lo pida.

Lo que sigue haciendo falta de este módulo: el nombre del producto y los enlaces
reales, que es lo que usan `/help`, `/premium` y la web.
"""

from __future__ import annotations

import os

# El `.env` se carga aquí y no solo en `config.py` porque este módulo lo usan
# también los **scripts** —`generar_web.py` sobre todo—, y esos no pasan por
# `config`. Sin esto, generar la web desde la consola veía `BOT_INVITE_URL`
# vacía y publicaba los botones apagados aunque el `.env` estuviera bien: el
# síntoma era una web sin el botón de invitar y un aviso de «enlaces sin
# configurar» que parecía un fallo del `.env`. Con la carga aquí, el valor es el
# mismo lo importe quien lo importe.
try:
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
        )
    )
except ImportError:  # sin dotenv instalado, se usan las variables del entorno
    pass

#: Nombre del producto. Configurable con `BOT_NOMBRE`.
#:
#: Se llamó **JetaDirectaBot** hasta el 22-09-2026. El dueño lo renombró a
#: **LoLProTrackr** —«así mejor le vamos a llamar al programa»— para que el
#: nombre diga qué hace y para que case con el dominio de donaciones
#: (`ko-fi.com/lolprotrackr`).
#:
#: Ojo al buscar el nombre viejo en el repositorio: **el repositorio y la URL de
#: GitHub Pages siguen llamándose `JetaDirectaBot`** (`set4jeta.github.io/
#: JetaDirectaBot/`, y `GITHUB_REPO` en `config.py`). No es un descuido: la URL
#: del canónico tiene que ser la que existe de verdad, así que se cambia el día
#: que se renombre el repositorio, no antes.
BOT_NOMBRE = os.getenv("BOT_NOMBRE", "LoLProTrackr")

#: URL pública del bot. Se usa en `/help`, en `/premium` y en el pie de la web.
WEB_URL = os.getenv("BOT_WEB_URL", "")

#: Enlace de invitación. Vacío por defecto: mejor no enseñar un enlace roto que
#: enseñar uno inventado.
INVITE_URL = os.getenv("BOT_INVITE_URL", "")

#: Donde se aceptan donaciones.
DONATE_URL = os.getenv("BOT_DONATE_URL", "")

#: Servidor de soporte.
SOPORTE_URL = os.getenv("BOT_SOPORTE_URL", "")


#: El oro de la marca, para los embeds que no llevan un color semántico.
#:
#: Es el `--oro` de `web/styles-esports.css` (#e6c76a), el del logotipo. Se usa
#: en `/help` y `/premium`, que son los dos comandos que hablan **del producto**
#: y por eso llevan el color del producto.
#:
#: Los que **no** lo usan, y por qué: el aviso de partida en vivo
#: (`ui/active_match_embed`) va en rojo y `/health` en rojo o verde. Ahí el color
#: es información —«esto está pasando ahora», «esto está roto»—, no marca, y
#: pintarlos de oro borraría la señal para ganar coherencia visual, que es un
#: mal cambio.
COLOR_MARCA = 0xE6C76A


#: La cuota de la API de Riot en producción, en crudo.
#:
#: Va aquí y no escrita dentro del texto porque **es el argumento entero del
#: discurso de apoyo** y aparece en la web, en `/premium` y en los mensajes de
#: cupo agotado: si Riot la cambia, se cambia en un sitio. El número que se
#: publica es el que da el portal de desarrolladores (`X-App-Rate-Limit:
#: 500:10,30000:600`), y de él sale `MAX_LIGAS_POR_SERVIDOR` en `leagues.py`.
#:
#: Se publica porque la especificidad es lo que hace creíble una petición: «nos
#: limita Riot» no convence a nadie, «Riot nos da 500 peticiones cada 10
#: segundos y ya las gastamos» sí.
RIOT_CUOTA_PETICIONES = 500
RIOT_CUOTA_SEGUNDOS = 10


def enlaces(idioma: str | None = None) -> list[str]:
    """Líneas de enlaces que existen de verdad, ya formateadas.

    Devuelve solo los que están configurados: un `/premium` que enseña
    "Donar: (vacío)" es peor que uno que no lo menciona.
    """
    es = idioma != "en"
    salida: list[str] = []
    if WEB_URL:
        salida.append(f"🌐 {'Web' if es else 'Website'}: {WEB_URL}")
    if INVITE_URL:
        salida.append(
            f"➕ {'Añadir a tu servidor' if es else 'Add to your server'}: {INVITE_URL}"
        )
    if DONATE_URL:
        salida.append(f"💛 {'Apoyar el proyecto' if es else 'Support the project'}: {DONATE_URL}")
    if SOPORTE_URL:
        salida.append(f"🛠 {'Soporte' if es else 'Support'}: {SOPORTE_URL}")
    return salida

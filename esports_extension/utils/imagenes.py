"""URLs de imagen listas para meterlas en un embed.

Por qué existe
--------------
La API de lolesports devuelve los logos de equipo por **`http://`**. Un enlace
`http` dentro de un embed no lo carga el proxy de imágenes de Discord: el
servidor de lolesports responde **301 hacia `https`**, el proxy no sigue esa
redirección y deja el hueco con el marcador de «cargando» —el recuadro
difuminado—. Y no hay ningún error en ninguna parte: el embed se envía bien, el
usuario ve una mancha gris y el log no dice nada.

Se vio el 29-09-2026 en el embed de un partido (Asian Games, Chinese Taipei vs
Republic of Korea): la miniatura y la imagen grande salían las dos difuminadas
mientras el texto estaba perfecto.

Esto es lo mismo que ya hacía `scripts/refrescar_partidos._https()` para la web
—ahí el `http` es contenido mixto y el navegador lo bloquea en silencio—, pero
los embeds no pasaban por ahí. La función se repite en vez de importarse porque
el script es independiente del paquete: se ejecuta solo, sin nextcord.
"""

from __future__ import annotations

_HTTPS = "https://"
_HTTP = "http://"


def url_imagen(url: str | None) -> str:
    """La misma URL, pero en `https`. Devuelve `""` si no había URL.

    Devolver cadena vacía y no `None` es a propósito: los llamantes meten el
    resultado directamente en `set_image`/`set_thumbnail`, y ahí `""` es la forma
    de decir «no pongas imagen». Lo que no puede llegar nunca es un `http://`,
    que es lo que deja el recuadro difuminado.

    Solo se toca el esquema. Una URL sin esquema, o ya en `https`, se devuelve
    tal cual: adivinar más sería romper casos que hoy funcionan.
    """
    limpio = (url or "").strip()
    if limpio.startswith(_HTTP):
        return _HTTPS + limpio[len(_HTTP):]
    return limpio

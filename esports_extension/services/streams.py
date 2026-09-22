# services/streams.py
"""Dónde ver el partido: retransmisión oficial y co-retransmisiones.

De dónde sale cada cosa
-----------------------
**La oficial la da la propia API de lolesports.** En `event.streams` cada
entrada trae `provider` (twitch, youtube, afreecatv), `parameter` (el canal o el
id del vídeo) y `locale`. Eso **ya se estaba descargando** en `getEventDetails`
—`EventDetails.streamsEventDetails` se llenaba— y se estaba tirando a la basura:
nadie lo leía para pintarlo. Es la única fuente que no se queda vieja sola,
porque la mantiene Riot y viene por partido y por idioma.

**Las co-retransmisiones no las da nadie**: son canales de terceros (la versión
española de una liga, co-streamers conocidos) y hay que mantenerlas a mano. Están
en `CORETRANSMISIONES`, indexadas por el `slug` de liga que trae la API —el mismo
código que usa `tracking/soloq/leagues.py`— y si alguna cambia se edita ahí.

Por qué está contemplado `afreecatv`
------------------------------------
La LCK no se emite en Twitch: se emite en AfreecaTV. Sin ese proveedor, los
partidos de la liga coreana se quedaban sin enlace justo de madrugada, que es
cuando los ve la gente de Europa.

Por qué el idioma del enlace no es el del usuario
-------------------------------------------------
`locale` viene por stream y aquí se prefiere el español, luego el inglés, luego
el resto. No se elige por el idioma del destinatario a propósito: el embed de
esports es el mismo para todo el canal (no hay versión por persona como en los
avisos de SoloQ) y un enlace en español sirve a quien entiende español, mientras
que un enlace en coreano no le sirve a nadie del servidor. El idioma del stream
va **etiquetado** en el texto para que se vea qué se está abriendo.
"""

from __future__ import annotations

from typing import Any, Optional

from utils.logger import get_logger

log = get_logger("esports.streams")

#: Plantilla de URL por proveedor. `{p}` es el `parameter` del stream.
_PROVEEDORES: dict[str, str] = {
    "twitch": "https://www.twitch.tv/{p}",
    "youtube": "https://www.youtube.com/watch?v={p}",
    # AfreecaTV (LCK). El `parameter` es el id del canal.
    "afreecatv": "https://play.afreecatv.com/{p}",
}

#: Orden de preferencia de idioma para el enlace que se enseña como oficial.
#: `es` primero porque es el idioma del bot y de su público principal.
_PREFERENCIA = ("es", "en")

#: Nombre del campo del embed. Va con emoji porque es lo que hace que se vea de
#: un vistazo en un embed que ya tiene tres o cuatro campos.
NOMBRE_CAMPO = "📺 Disponible en"

#: Co-retransmisiones por `slug` de liga. **Mantenimiento a mano**: la oficial
#: siempre sale de la API, esto es solo lo que se añade detrás.
#:
#: Se indexa por el slug de lolesports, que coincide con el código del catálogo
#: de `leagues.py` (lec, lck, lcs, cblol, lpl, les, lfl, nlc, prm...).
CORETRANSMISIONES: dict[str, list[tuple[str, str]]] = {
    "lec": [("LVPes (español)", "https://www.twitch.tv/lvpes")],
    "les": [("LES (español)", "https://www.twitch.tv/les")],
    "lcs": [("LLA (español)", "https://www.twitch.tv/lla")],
    "cblol": [("CBLOL (portugués)", "https://www.twitch.tv/cblol")],
    "lck": [("LCK en inglés", "https://www.twitch.tv/lck")],
    "lpl": [("LPL en inglés", "https://www.twitch.tv/lpl")],
    "lfl": [("LFL (francés)", "https://www.twitch.tv/lfl")],
    "prm": [("Prime League (alemán)", "https://www.twitch.tv/primeleague")],
    "nlc": [("NLC (inglés)", "https://www.twitch.tv/nlclol")],
    "hm": [("Hitpoint Masters (checo)", "https://www.twitch.tv/hitpointcz")],
    "rol": [("Road of Legends (neerlandés)", "https://www.twitch.tv/road_of_legends")],
    "hll": [("Hellenic Legends (griego)", "https://www.twitch.tv/helleniclegends")],
    "rl": [("Nervarien (polaco)", "https://www.twitch.tv/nervarien")],
    "lit": [("PG Esports (italiano)", "https://www.twitch.tv/pg_esports")],
    "msi": [("Riot Games (inglés)", "https://www.twitch.tv/riotgames")],
    "worlds": [("Riot Games (inglés)", "https://www.twitch.tv/riotgames")],
}

#: Tope de co-retransmisiones que se listan. El valor de un campo de embed es de
#: 1024 caracteres; con dos o tres enlaces ya se pasa de la mitad, y una lista
#: larga deja de leerse.
MAX_CO = 3


def url_de(provider: str, parameter: str) -> Optional[str]:
    """URL del stream, o `None` si no se sabe construir.

    Un proveedor desconocido (mañana Riot emite en otra plataforma) no puede
    romper el embed: se descarta ese enlace y se sigue con los demás.
    """
    plantilla = _PROVEEDORES.get((provider or "").strip().lower())
    valor = (parameter or "").strip()
    if not plantilla or not valor:
        return None
    # YouTube a veces manda la URL entera o el parámetro `v=...` en vez del id.
    if "youtube" in plantilla and "v=" in valor:
        valor = valor.split("v=")[-1]
    return plantilla.format(p=valor)


def _orden_idioma(locale: str) -> tuple[int, str]:
    """Clave de orden: primero español, luego inglés, luego el resto."""
    loc = (locale or "").strip().lower()
    for i, pref in enumerate(_PREFERENCIA):
        if loc.startswith(pref):
            return (i, loc)
    return (len(_PREFERENCIA), loc)


def oficial(match: Any) -> Optional[tuple[str, str]]:
    """La retransmisión oficial del partido: `(etiqueta, url)`.

    `match` es un `TrackedMatch`; se lee `streamsEventDetails`, que se rellena en
    `enrich_from_event_details`. Si el partido todavía no se ha enriquecido (o la
    API no manda streams) devuelve `None` y el campo no se pinta: mejor no poner
    nada que poner un enlace inventado.
    """
    streams = getattr(match, "streamsEventDetails", None) or []
    candidatos: list[tuple[tuple[int, str], str, str]] = []
    for s in streams:
        url = url_de(getattr(s, "provider", ""), getattr(s, "parameter", ""))
        if not url:
            continue
        candidatos.append((_orden_idioma(getattr(s, "locale", "")), getattr(s, "provider", ""), url))
    if not candidatos:
        return None

    _, provider, url = min(candidatos, key=lambda c: c[0])
    locale = next(
        (getattr(s, "locale", "") for s in streams
         if url_de(getattr(s, "provider", ""), getattr(s, "parameter", "")) == url),
        "",
    )
    etiqueta = "Oficial · " + provider.capitalize()
    if locale:
        etiqueta += f" ({locale})"
    return (etiqueta, url)


def co_retransmisiones(match: Any) -> list[tuple[str, str]]:
    """Canales de terceros para este partido, según el slug de su liga."""
    slug = (getattr(match, "slug", "") or "").strip().lower()
    if not slug:
        return []
    return list(CORETRANSMISIONES.get(slug, []))[:MAX_CO]


def campo(match: Any) -> Optional[tuple[str, str]]:
    """El campo listo para el embed: `(nombre, valor)`, o `None` si no hay nada.

    Orden: **primero la oficial y después las co-retransmisiones**, que es como
    se busca un partido de verdad — primero el canal de la liga y, si no te vale
    el idioma o quieres verlo comentado, los demás.
    """
    lineas: list[str] = []

    retransmision = oficial(match)
    if retransmision:
        lineas.append(f"**{retransmision[0]}**: [ver]({retransmision[1]})")

    for etiqueta, url in co_retransmisiones(match):
        lineas.append(f"[{etiqueta}]({url})")

    if not lineas:
        return None
    return (NOMBRE_CAMPO, "\n".join(lineas))

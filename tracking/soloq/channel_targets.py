"""Qué avisos quiere cada canal, cuando no quiere todos.

Por qué existe
--------------
Hasta el 22-09-2026 un canal recibía **todo** lo que siguiera su servidor: si el
servidor seguía la LEC y la LCK, los dos canales recibían las dos. No había forma
de tener un canal para la LEC y otro para la LCK, ni un canal solo de partidos de
esports. El dueño lo pidió así: *«así la gente fácilmente puede crear un canal de
por ejemplo esports, y ahí suscribirse a esports… `/subscribe esports lck`, solo
lck»*, y con la misma semántica que `/track` pero a nivel de canal.

La regla, que es la misma que en `/track`: **lo que pides es lo que llega**.
`/subscribe esports lck` no significa «la LCK además de lo de siempre», significa
**solo** la LCK.

Cómo se guarda
--------------
    {"<guild_id>": {"<channel_id>": {"soloq": ["lec", "Elyoya"],
                                      "esports": ["*"]}}}

Un objetivo es el código de una liga (`lec`), el nombre de un pro (`Elyoya`), el
tricode de un equipo (`T1`) o un Riot ID (`Caps#EUW`). `"*"` es «todas las
ligas», que es lo que hace `/subscribe esports` sin decir cuál.

**Un canal sin entrada en el fichero no es un canal vacío**: es un canal con el
comportamiento de siempre —todas las ligas del servidor—. Esa distinción importa:
si «sin entrada» y «entrada vacía» significaran lo mismo, cualquier fallo de
lectura dejaría a los servidores que ya funcionaban sin recibir nada, y sin
ningún error. Es el fallo que hay que hacer imposible.

Fichero aparte de `notify_config.json` a propósito: aquel guarda **qué canales**
reciben, que es lo que lee el reparto de siempre; este guarda **qué quiere cada
canal**, que es lo nuevo. Si se mezclaran, un fichero ilegible de objetivos
tumbaría también los canales, y eso es perder lo que ya funcionaba por una
función nueva.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from utils.logger import get_logger

log = get_logger("tracking.channel_targets")

RUTA = Path(os.path.dirname(__file__)) / "channel_targets.json"

#: «Todas las ligas». Se guarda como objetivo porque `/subscribe esports` sin
#: decir cuál es una petición legítima: quiero los partidos, de donde sean.
TODAS = "*"

#: Los dos tipos de aviso. Son los mismos valores que acepta `/subscribe`.
SOLOQ = "soloq"
ESPORTS = "esports"
TIPOS = (SOLOQ, ESPORTS)


def _leer() -> dict:
    if not RUTA.exists():
        return {}
    try:
        with RUTA.open(encoding="utf-8") as fh:
            datos = json.load(fh)
    except (OSError, ValueError) as exc:
        # Se devuelve vacío y se avisa: un fichero roto deja a los canales con el
        # comportamiento de siempre, que es degradar y no romper.
        log.error("No se pudo leer %s: %s. Se usa el reparto de siempre.", RUTA.name, exc)
        return {}
    return datos if isinstance(datos, dict) else {}


def _escribir(datos: dict) -> None:
    tmp = RUTA.with_name(RUTA.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, RUTA)
    except OSError as exc:
        log.error("No se pudo guardar %s: %s.", RUTA.name, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def objetivos_de(guild_id, channel_id) -> dict[str, list[str]]:
    """`{"soloq": [...], "esports": [...]}`. Vacío si el canal no tiene entrada.

    **Vacío significa «como siempre»**, no «nada»: ver el docstring del módulo.
    """
    guild = _leer().get(str(guild_id))
    if not isinstance(guild, dict):
        return {}
    entrada = guild.get(str(channel_id))
    if not isinstance(entrada, dict):
        return {}
    return {
        tipo: [str(v) for v in entrada.get(tipo) or []]
        for tipo in TIPOS
        if entrada.get(tipo)
    }


def poner(guild_id, channel_id, tipo: str, objetivo: str) -> None:
    """Añade un objetivo al canal. `tipo` es `soloq` o `esports`."""
    datos = _leer()
    guild = datos.setdefault(str(guild_id), {})
    entrada = guild.setdefault(str(channel_id), {})
    lista = [str(v) for v in entrada.get(tipo) or []]
    if objetivo not in lista:
        lista.append(objetivo)
    entrada[tipo] = lista
    _escribir(datos)


def limpiar(guild_id, channel_id) -> bool:
    """Quita los objetivos del canal: vuelve al reparto de siempre. True si había."""
    datos = _leer()
    guild = datos.get(str(guild_id))
    if not isinstance(guild, dict) or str(channel_id) not in guild:
        return False
    del guild[str(channel_id)]
    if not guild:
        del datos[str(guild_id)]
    _escribir(datos)
    return True


def todos(guild_id) -> dict[str, dict[str, list[str]]]:
    """`{channel_id: {tipo: [objetivos]}}` de un servidor, para poder enseñarlo."""
    guild = _leer().get(str(guild_id))
    return dict(guild) if isinstance(guild, dict) else {}


def _coincide(objetivo: str, candidatos: tuple[str, ...]) -> bool:
    """Compara sin distinguir mayúsculas ni espacios sobrantes.

    `casefold` y no `lower` porque el nombre de un pro puede traer cosas raras, y
    aquí lo único que se busca es que `Elyoya` y `elyoya ` sean lo mismo.
    """
    limpio = objetivo.strip().casefold()
    return any(limpio == c.strip().casefold() for c in candidatos if c)


def acepta_soloq(
    lista: list[str] | None,
    *,
    liga: str = "",
    jugador: str = "",
    equipo: str = "",
    cuenta: str = "",
) -> bool:
    """¿Este canal quiere la partida de este jugador?

    `lista` es la de `soloq`. `None` o vacía significa que el canal **no** pidió
    SoloQ, así que no le toca nada de este tipo: es la semántica «solo» que pidió
    el dueño. Quien no quiere filtrar no llama a esto (ver el reparto).
    """
    if not lista:
        return False
    if any(o.strip() == TODAS for o in lista):
        return True
    return any(_coincide(o, (liga, jugador, equipo, cuenta)) for o in lista)


def acepta_esports(
    lista: list[str] | None,
    *,
    liga: str = "",
    equipos: tuple[str, ...] = (),
) -> bool:
    """¿Este canal quiere este partido oficial?

    Un partido lo determina su liga y los dos equipos que juegan: seguir a `T1`
    es querer los partidos donde juegue T1, sea la liga que sea.
    """
    if not lista:
        return False
    if any(o.strip() == TODAS for o in lista):
        return True
    return any(_coincide(o, (liga, *equipos)) for o in lista)

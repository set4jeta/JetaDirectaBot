"""Buscar un pro o un equipo en el roster ya descargado.

Por qué existe
--------------
Estas dos funciones vivían dentro de `core/user_alerts_commands.py`, que las usaba
`/track`. Cuando `/subscribe` necesitó lo mismo —resolver «Elyoya» o «T1» para
saber a qué liga pertenecen y poder añadirla al barrido— importarlas de allí habría
sido importar funciones privadas de otro comando. Viven aquí y las usan los dos.

Se busca en el **roster descargado** (`accounts_from_teams.json`) y no contra
dpm.lol, por dos motivos medidos:

* `/v1/pros/<nombre>` va por cloudscraper con 20 s de timeout y hasta 3 reintentos
  con `sleep(2)`; bloquea o tarda, y un comando no puede hacer eso.
* y aunque respondiera, **no trae la liga**. Lo que hay en disco sí contesta la
  pregunta que importa: si el nick está ahí, sus cuentas se consultan en cada
  pasada, así que los avisos van a llegar.
"""

from __future__ import annotations

from utils.logger import get_logger

log = get_logger("tracking.roster_lookup")


def pro_rastreado(nombre: str):
    """El jugador del roster que coincide con este nombre, o `None`.

    Se compara con `name` y con `display_name` porque el usuario puede escribir
    cualquiera de los dos, pero lo que se guarda es siempre `name`: es el valor con
    el que `dm_notifier.destinatarios` compara (viene de la pasada), y guardar el
    otro dejaría una suscripción que nunca coincide.
    """
    from tracking.soloq.accounts_io import load_tracked_accounts

    objetivo = (nombre or "").strip().casefold()
    if not objetivo:
        return None
    try:
        for jugador in load_tracked_accounts():
            nombres = {
                (getattr(jugador, "name", "") or "").casefold(),
                (getattr(jugador, "display_name", "") or "").casefold(),
            }
            if objetivo in nombres - {""}:
                return jugador
    except Exception:
        # Un JSON a medio escribir no puede impedir que alguien se suscriba: se
        # guarda igual y quien llama le avisa de que no se ha podido comprobar.
        log.exception("No se pudo leer accounts_from_teams.json para validar %r", nombre)
    return None


def equipo_rastreado(nombre: str) -> tuple[str, str, str] | None:
    """El equipo que coincide con lo escrito: `(tricode, nombre, liga)`.

    Se compara **el tricode y el nombre completo** (`T1` y `T1`, `FNC` y `Fnatic`):
    la gente escribe las dos cosas y ninguna es más correcta.

    Lo que se devuelve como clave es el tricode, porque es lo que trae la pasada en
    `player.team` y con lo que compara `dm_notifier.destinatarios`. Guardar el
    nombre completo dejaría una suscripción que no coincide nunca.

    `None` si no hay ningún equipo así, y entonces quien llama trata el valor como
    un nick.
    """
    from tracking.soloq.accounts_io import load_tracked_accounts

    objetivo = (nombre or "").strip().casefold()
    if not objetivo:
        return None
    try:
        for jugador in load_tracked_accounts():
            tricode = (getattr(jugador, "team", "") or "").strip()
            completo = (getattr(jugador, "team_name", "") or "").strip()
            if objetivo in {tricode.casefold(), completo.casefold()} - {""}:
                return (
                    tricode,
                    completo or tricode,
                    (getattr(jugador, "league", "") or "").strip(),
                )
    except Exception:
        log.exception("No se pudo leer el roster para validar el equipo %r", nombre)
    return None


def liga_principal_de_equipo(tricode: str) -> str:
    """La liga en la que más juega ese equipo, o `""`.

    Un equipo aparece en el roster **varias veces**: su liga doméstica y los
    eventos internacionales (MSI, Worlds). `equipo_rastreado` devuelve la primera
    coincidencia que encuentra, y con `T1` eso daba `msi` — con lo que
    `/subscribe soloq T1` metía el MSI en el barrido y los partidos de LCK de T1
    seguían sin llegar. Se cuenta cuántos jugadores tiene el equipo en cada liga y
    gana la que más tiene, que es la doméstica.
    """
    from tracking.soloq.accounts_io import load_tracked_accounts

    objetivo = (tricode or "").strip().casefold()
    if not objetivo:
        return ""
    cuenta: dict[str, int] = {}
    try:
        for jugador in load_tracked_accounts():
            if (getattr(jugador, "team", "") or "").strip().casefold() != objetivo:
                continue
            liga = (getattr(jugador, "league", "") or "").strip().lower()
            if liga:
                cuenta[liga] = cuenta.get(liga, 0) + 1
    except Exception:
        log.exception("No se pudo leer el roster para contar las ligas de %r", tricode)
        return ""
    if not cuenta:
        return ""
    # Un evento internacional (el MSI) no es la liga del equipo: ahí aparece de
    # visita, y seguir el MSI en vez de la LCK dejaba a T1 sin avisos. La región
    # la dice el catálogo de ligas, así que no hay lista a mano que mantener.
    from tracking.soloq.leagues import LIGAS

    def _es_evento(liga: str) -> bool:
        entrada = LIGAS.get(liga)
        return bool(entrada) and (entrada.region or "").lower() == "internacional"

    return min(cuenta, key=lambda liga: (_es_evento(liga), -cuenta[liga], liga))

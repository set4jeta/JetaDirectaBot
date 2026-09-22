"""Catálogo de ligas y de qué equipos sigue el bot.

Por qué existe este módulo
--------------------------
El bot solo seguía la LEC porque había un set escrito a mano:

    TRACKED_TEAMS = {"G2", "FNC", "VIT", "TH", "KC", "NAVI",
                     "GX", "BDS", "SK", "MKOI", "KOI", "LR"}

Eso tiene dos problemas, y los dos se vieron en el arranque real:

1. **Se queda obsoleto sin avisar.** En el leaderboard actual de la LEC ya no
   están `BDS`, `KOI` ni `LR` — aparece `SHFT`. El bot sigue intentando
   scrapear tres equipos que no existen y se pierde al que sí existe.
2. **No se puede ampliar.** Para seguir otra liga hay que editar código.

Aquí la lista de equipos se **deriva del leaderboard de la liga**, que dpm.lol
mantiene al día. Seguir una liga cuesta exactamente una petición y la alineación
se actualiza sola cuando un equipo se renombra o entra en la liga.

Qué ligas hay disponibles
-------------------------
Comprobado contra `/v1/esport/soloq/leagues/<codigo>/leaderboard` midiendo
cuántos jugadores y equipos devuelve cada código. **Un código que no existe no
da 404**: devuelve un leaderboard comodín de 1684 jugadores y 212 equipos, así
que la única forma de saberlo es mirar el contenido. Resultado:

    lec 82 jug.  10 eq.      lfl  95 jug. 10 eq.     tcl  61 jug.  8 eq.
    lck 81 jug.  10 eq.      nlc 103 jug. 15 eq.     hll  64 jug.  8 eq.
    lpl 81 jug.  12 eq.      prm 107 jug. 10 eq.    cblol 62 jug.  8 eq.
    lcs 61 jug.   8 eq.      msi 121 jug. 11 eq.     lcp  57 jug.  8 eq.

Las ocho que se añadieron después (2026-09-02) estaban ahí desde el principio,
pero **con un código que no es el slug oficial de lolesports**, y por eso se
habían dado por inexistentes. Buscar por el nombre de la liga no las encuentra:

    les 64 jug.  8 eq. (no `superliga`)   ebl 37 jug. 6 eq.
    lit 53 jug.  8 eq.                    rl  59 jug. 7 eq. (no `rift_legends`)
    hm  57 jug.  8 eq. (no `hitpoint`)    rol 61 jug. 8 eq.
    al  62 jug.  8 eq. (no `arabian`)     cd  68 jug. 10 eq. (no `circuito`)

Sobre LLA y NACL en concreto
---------------------------
Son las dos que el usuario pidió por su nombre, y **no se pueden seguir**. No es
que falte añadirlas: dpm.lol no tiene leaderboard de ninguna de las dos. Se
probaron todas las variantes razonables del código (`lla`, `latam`, `ll`,
`nacl`, `nal`, `na_cl`) y todas devuelven el comodín o un 500.

Se buscó la vía alternativa y también se midió: el API público de esports de
Riot (`esports-api.lolesports.com`) sí tiene sus plantillas, así que se sacaron
los nombres de ahí y se intentó resolver cada jugador contra
`dpm.lol/v1/pros/<nombre>`, que es quien mapea nombre de pro -> cuentas de
SoloQ. El resultado deja claro por qué no se promete:

    LLA               13 jugadores ->  1 resuelto  (8 %)
    NACL              79 jugadores -> 32 resueltos (41 %)

Y el único que resuelve de la LLA es una **colisión de nombres**: "Summit" de
Movistar R7 devuelve la ficha del Summit coreano (Park Woo-tae, Estral Esports).
Es decir, no es cobertura, es un dato equivocado. Con eso, una liga LLA
"soportada" avisaría de las partidas de otra persona, que es peor que no
tenerla.

Las mismas mediciones descartan LJL (4,5 %), LCO (6,8 %), PCS (13 %) y VCS
(14 %). Las que sí dan cobertura por esta vía —LCK Challengers 100 %, Circuito
Desafiante 82 %— resultaron tener leaderboard propio en dpm con otro código, así
que se añadieron por la vía normal.

Sobre la plataforma
-------------------
`spectator-v5` necesita saber en qué servidor juega cada cuenta. La mayoría de
las ligas están completas en uno (`euw1` para LEC/LFL/NLC/PRM y para todas las
regionales europeas nuevas, `kr` para LCK, `br1` para CBLOL y Circuito
Desafiante, `tr1` para TCL). Otras son mixtas (LCP reparte por JP1, TW2, VN2,
SG2 y PH2) y LPL está en los servidores chinos, que la API de Riot no cubre: de
esas se pueden mostrar rangos pero no detectar partida en vivo.

El leaderboard **no trae plataforma** (medido: el campo no existe en ninguna de
las 20 ligas), así que la plataforma real de cada cuenta sale de
`/v1/pros/<nombre>`, y lo que hay aquí es solo la etiqueta para el usuario.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from utils.logger import get_logger

log = get_logger("tracking.leagues")

# Dónde se guarda qué ligas sigue cada servidor.
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "leagues_config.json")

# Ligas con las que arranca un servidor si no ha elegido ninguna. Es la LEC
# porque es lo que el bot hacía siempre; cambiarlo aquí no rompe a nadie.
LIGA_POR_DEFECTO = "lec"

# Máximo de ligas que puede seguir **un servidor**. Recalculado el 2026-09-02
# con datos, no con la estimación vieja ("12 ligas de ~90 cuentas"):
# `scripts/_coste_ligas.py` pide el leaderboard de las 20 y cuenta personas
# distintas; el multiplicador de cuentas por persona (3,44) sale de la LEC ya
# poblada, 50 personas -> 172 cuentas en `accounts_from_teams.json`.
#
#     las 20 ligas       917 personas  -> ~3154 cuentas -> ~63 s de pasada
#     las 6 más caras                     ~1221 cuentas -> ~24 s
#     las 4 más caras                      ~853 cuentas -> ~17 s
#     una sola (la peor, NLC 74 pers.)      ~255 cuentas ->  ~5 s
#
# Los segundos son el suelo que impone el cupo de Riot (500 req/10 s = 50/s) y
# se comparan contra `CHECK_GAMES_INTERVAL` (30 s). Con 4 ligas la peor
# combinación posible tarda 17 s y cabe; con 6 ya raspa; con las 20 no cabe.
# Así que 4 sigue siendo el número correcto, ahora por medición.
#
# Ojo con lo que este tope **no** acota: la pasada del tracker es la unión de
# las ligas de todos los servidores (`ligas_en_uso`), así que 20 servidores con
# 4 ligas distintas cada uno cuestan las 20 ligas. Eso se vigila en la pasada
# (ver el aviso de duración en `active_game_checker`), no aquí.
MAX_LIGAS_POR_SERVIDOR = 4


@dataclass(frozen=True)
class Liga:
    """Una liga que el bot sabe seguir."""

    codigo: str  # el que usa dpm.lol
    nombre: str  # "LEC"
    region: str  # "Europa", para el texto que ve el usuario
    plataforma: str  # servidor de Riot, o "" si es mixta
    #: False si la API de Riot no cubre los servidores de esta liga (LPL): se
    # pueden mostrar rangos, pero no detectar partida en vivo.
    rastreable: bool = True
    #: True si los jugadores juegan en servidores distintos dentro de la liga,
    # así que hay que resolver la plataforma cuenta por cuenta.
    plataforma_mixta: bool = False

    @property
    def etiqueta(self) -> str:
        return f"{self.nombre} · {self.region}"

    @property
    def seguible(self) -> bool:
        """¿Se pueden detectar partidas en vivo de esta liga?"""
        return self.rastreable


#: Catálogo. El número de equipos se recalcula en cada refresco, así que aquí
#: solo va lo que no cambia: cómo se llama y dónde juega.
LIGAS: dict[str, Liga] = {
    l.codigo: l
    for l in (
        # --- Ligas principales ---
        Liga("lec", "LEC", "Europa", "euw1"),
        Liga("lck", "LCK", "Corea", "kr"),
        Liga("lcs", "LCS", "Norteamérica", "na1"),
        Liga("cblol", "CBLOL", "Brasil", "br1"),
        Liga("lcp", "LCP", "Asia-Pacífico", "", plataforma_mixta=True),
        Liga("msi", "MSI", "Internacional", "", plataforma_mixta=True),
        # China juega en servidores que la API de Riot no expone: sirven los
        # rangos, pero `spectator-v5` no va a contestar. Se marca para no
        # prometer detección de partidas que no va a ocurrir.
        Liga("lpl", "LPL", "China", "", rastreable=False),

        # --- Regionales europeas ---
        # Todas medidas en euw1 salvo alguna cuenta suelta en eun1, que se
        # resuelve por cuenta con la plataforma de `/v1/pros`.
        Liga("lfl", "LFL", "Francia", "euw1"),
        Liga("nlc", "NLC", "Norte de Europa", "euw1"),
        Liga("prm", "Prime League", "Alemania", "euw1"),
        Liga("hll", "HLL", "Grecia", "euw1"),
        Liga("les", "LES", "España", "euw1"),
        Liga("lit", "LIT", "Italia", "euw1"),
        Liga("rl", "Rift Legends", "Polonia", "euw1"),
        Liga("rol", "Road of Legends", "Benelux", "euw1"),
        Liga("hm", "Hitpoint Masters", "Chequia y Eslovaquia", "euw1"),
        Liga("ebl", "EBL", "Balcanes", "euw1"),
        Liga("tcl", "TCL", "Turquía", "tr1"),
        Liga("al", "Arabian League", "Oriente Medio", "euw1"),

        # --- Segundas divisiones ---
        Liga("cd", "Circuito Desafiante", "Brasil", "br1"),
    )
}

#: Alias para que la gente escriba lo que le suene.
#:
#: Aquí también viven los slugs oficiales de lolesports, que **no** coinciden con
#: el código de dpm: quien busque `superliga`, `hitpoint` o `arabian` —los
#: nombres que salen en la web de Riot— tiene que encontrar la liga igual. Esa
#: discrepancia es la razón por la que estas ocho ligas se habían dado por
#: inexistentes.
ALIAS: dict[str, str] = {
    "eu": "lec", "europe": "lec", "europa": "lec",
    "kr": "lck", "korea": "lck", "corea": "lck",
    "na": "lcs", "northamerica": "lcs", "america": "lcs",
    "fr": "lfl", "francia": "lfl", "france": "lfl",
    "de": "prm", "alemania": "prm", "germany": "prm",
    "primeleague": "prm", "prime": "prm",
    "tr": "tcl", "turquia": "tcl", "turkey": "tcl",
    "turkiye-sampiyonluk-ligi": "tcl",
    "br": "cblol", "brasil": "cblol", "brazil": "cblol",
    "cblol-brazil": "cblol",
    "cn": "lpl", "china": "lpl",
    "gr": "hll", "grecia": "hll", "greece": "hll",
    "hellenic_legends_league": "hll",
    "pacific": "lcp", "pacifico": "lcp",
    # Las nuevas, por nombre y por slug oficial.
    "es": "les", "espana": "les", "españa": "les", "spain": "les",
    "superliga": "les", "ligaespanola": "les",
    "it": "lit", "italia": "lit", "italy": "lit",
    "pl": "rl", "polonia": "rl", "poland": "rl", "rift_legends": "rl",
    "riftlegends": "rl", "ultraliga": "rl",
    "benelux": "rol", "nl": "rol", "road_of_legends": "rol",
    "roadoflegends": "rol",
    "cz": "hm", "chequia": "hm", "czech": "hm", "hitpoint": "hm",
    "hitpoint_masters": "hm", "hpm": "hm",
    "balcanes": "ebl", "balkan": "ebl", "esports_balkan_league": "ebl",
    "arabia": "al", "arabian": "al", "arabian_league": "al",
    "mena": "al",
    "circuito": "cd", "desafiante": "cd", "cblol_academy": "cd",
}


def normalizar(texto: str) -> str:
    """`"  LEC "` -> `"lec"`. Pasa por los alias."""
    limpio = (texto or "").strip().lower()
    if not limpio:
        return ""
    if limpio in LIGAS:
        return limpio
    return ALIAS.get(limpio, limpio)


def resolver(texto: str) -> Liga | None:
    """Devuelve la liga de un texto, o None si no existe."""
    return LIGAS.get(normalizar(texto))


# ---------------------------------------------------------------------- #
# Rostros de cada liga (scrapeados del leaderboard)
# ---------------------------------------------------------------------- #

@dataclass
class RostersLiga:
    """Equipos y jugadores de una liga, tal como los reporta dpm.lol."""

    codigo: str
    equipos: list[str] = field(default_factory=list)
    #: (displayName, team) tal como los da el leaderboard. `displayName` es lo
    #: que resuelve contra `/v1/pros/<nombre>`: comprobado en las cuatro ligas
    #: de regiones distintas (LEC, LCK, LCS, CBLOL) y funciona en todas.
    jugadores: list[tuple[str, str]] = field(default_factory=list)

    @property
    def vacio(self) -> bool:
        return not self.equipos


def roster_de_liga(codigo: str) -> RostersLiga:
    """Equipos y jugadores de una liga, desde el leaderboard de dpm.lol.

    Una sola petición trae puuid, nombre, equipo, carril y rango de cada
    jugador, así que no hace falta scrapear una ficha por equipo.

    Es síncrona a propósito: `accounts_from_teams.main()` también lo es y se
    ejecuta en un hilo, donde no se puede usar la versión `async` sin crear un
    event loop nuevo (ver la nota en `fetch_league_leaderboard_sync`).
    """
    from apis.dpm_api import fetch_league_leaderboard_sync

    liga = resolver(codigo)
    if liga is None:
        log.warning("Liga desconocida: %s", codigo)
        return RostersLiga(codigo=normalizar(codigo))

    datos = fetch_league_leaderboard_sync(liga.codigo)
    if not datos:
        log.error(
            "La liga '%s' no devolvió leaderboard. No se actualizará su roster.",
            liga.codigo,
        )
        return RostersLiga(codigo=liga.codigo)

    equipos = sorted({
        (p.get("team") or "").strip()
        for p in datos
        if isinstance(p, dict) and (p.get("team") or "").strip()
    })
    jugadores = [
        ((p.get("displayName") or "").strip(), (p.get("team") or "").strip())
        for p in datos
        if isinstance(p, dict) and (p.get("displayName") or "").strip()
    ]
    log.info(
        "Liga %s: %d jugadores en %d equipos (%s)",
        liga.codigo, len(jugadores), len(equipos), ", ".join(equipos),
    )
    return RostersLiga(codigo=liga.codigo, equipos=equipos, jugadores=jugadores)


# ---------------------------------------------------------------------- #
# Qué ligas sigue cada servidor
# ---------------------------------------------------------------------- #

def _cargar() -> dict[str, Any]:
    if not os.path.exists(_CONFIG_PATH):
        return {}
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("leagues_config.json ilegible (%s): se empieza vacío", exc)
        return {}


def _guardar(datos: dict[str, Any]) -> None:
    tmp = _CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _CONFIG_PATH)


def tope_de_ligas(guild_id: int | str | None) -> int:
    """Cuántas ligas puede seguir este servidor de verdad.

    Es el menor de dos números que no significan lo mismo:

    * el cupo de su plan (`plans.limite`), que es una decisión comercial;
    * `MAX_LIGAS_POR_SERVIDOR`, que es física — sale del cupo de peticiones de
      Riot y ningún plan puede saltárselo.

    Se resuelve aquí y no en cada llamada para que `/ligas`, `/premium` y el
    guardado usen el mismo número; que el comando enseñe un tope y el guardado
    aplique otro es el fallo que esto evita.
    """
    from tracking.soloq.plans import limite

    del_plan = limite(guild_id, "ligas")
    if del_plan <= 0:
        del_plan = 1  # sin plan legible, el gratuito: una liga
    return min(del_plan, MAX_LIGAS_POR_SERVIDOR)


def ligas_de(guild_id: int | str | None) -> list[str]:
    """Códigos de las ligas que sigue un servidor, recortados a su cupo.

    Si nunca eligió, devuelve la LEC: es el comportamiento de siempre, para que
    quien ya tenía el bot configurado no note el cambio.

    El recorte se hace **al leer** y no al guardar. Un servidor que baja de plan
    con 4 ligas configuradas sigue teniendo las 4 en disco y solo se le usan las
    que le tocan; si vuelve a subir, aparecen otra vez. Borrarlas al bajar de
    plan sería irreversible.
    """
    datos = _cargar()
    clave = str(guild_id) if guild_id is not None else "_global"
    elegidas = datos.get(clave, {}).get("ligas")
    if not elegidas:
        return [LIGA_POR_DEFECTO]
    validas = [c for c in elegidas if c in LIGAS]
    if not validas:
        return [LIGA_POR_DEFECTO]
    return validas[:tope_de_ligas(guild_id)]


def ligas_guardadas(guild_id: int | str | None) -> list[str]:
    """Lo que el servidor tiene elegido, sin aplicar el cupo.

    Hace falta para poder decir "tienes 4 elegidas y tu plan usa 1": si `/ligas`
    solo viera la lista recortada, las otras parecerían borradas.
    """
    datos = _cargar()
    clave = str(guild_id) if guild_id is not None else "_global"
    elegidas = datos.get(clave, {}).get("ligas") or []
    return [c for c in elegidas if c in LIGAS]


def establecer_ligas(guild_id: int | str | None, codigos: list[str]) -> list[str]:
    """Guarda la selección de un servidor. Devuelve lo que queda **en uso**.

    Se guarda hasta el límite físico y se devuelve hasta el cupo del plan, que
    son cosas distintas: así, quien pague después no tiene que volver a escribir
    su selección.
    """
    limpios: list[str] = []
    for c in codigos:
        liga = resolver(c)
        if liga and liga.codigo not in limpios:
            limpios.append(liga.codigo)

    if not limpios:
        limpios = [LIGA_POR_DEFECTO]
    if len(limpios) > MAX_LIGAS_POR_SERVIDOR:
        limpios = limpios[:MAX_LIGAS_POR_SERVIDOR]

    datos = _cargar()
    clave = str(guild_id) if guild_id is not None else "_global"
    datos.setdefault(clave, {})["ligas"] = limpios
    _guardar(datos)

    en_uso = limpios[:tope_de_ligas(guild_id)]
    if len(en_uso) < len(limpios):
        log.info(
            "Ligas de %s: %s (en uso %s, el resto fuera del cupo del plan)",
            clave, ", ".join(limpios), ", ".join(en_uso),
        )
    else:
        log.info("Ligas de %s: %s", clave, ", ".join(en_uso))
    return en_uso


def ligas_de_seguidos() -> set[str]:
    """Ligas de los **jugadores y equipos** que sigue la gente por su cuenta.

    Por qué hace falta
    ------------------
    Seguir una liga ya metía esa liga en la unión (`ligas_de_usuarios`). Seguir a
    un jugador o a un equipo **no**, y el efecto era el peor posible: el aviso se
    guardaba, el usuario veía "te avisaré", y no le llegaba nunca nada — porque la
    pasada solo consulta las cuentas de las ligas en uso, y Faker no aparece si la
    LCK no se barre. Silencio sin error.

    Así que la suscripción arrastra su liga: es la única forma de que el aviso
    pueda existir.

    Se resuelve contra los rosters ya descargados (`accounts_from_teams.json`), que
    traen `name`, `team`, `team_name` y `league` por jugador: lectura de disco, sin
    red. Un nombre que no esté en el fichero no aporta nada, y eso es correcto:
    sin cuentas descargadas no hay nada que barrer de todas formas.

    Coste: esto ensancha la unión, y la unión no tiene techo (4 ligas por servidor
    y por usuario, pero la suma de todos no). Es la misma vigilancia que ya existe
    en la pasada: si no cabe en su intervalo, se ve en el log y en `/health`.
    """
    from tracking.soloq.user_config import usuarios_con

    nombres = {
        n.strip().casefold()
        for valores in usuarios_con("jugadores").values()
        for n in valores
        if n and n.strip()
    }
    equipos = {
        t.strip().casefold()
        for valores in usuarios_con("equipos").values()
        for t in valores
        if t and t.strip()
    }
    if not nombres and not equipos:
        return set()

    from tracking.soloq.accounts_io import load_tracked_accounts

    codigos: set[str] = set()
    try:
        for jugador in load_tracked_accounts():
            liga = (getattr(jugador, "league", "") or "").strip().lower()
            if liga not in LIGAS:
                continue
            nombre = (getattr(jugador, "name", "") or "").strip().casefold()
            if nombre and nombre in nombres:
                codigos.add(liga)
                continue
            # El equipo se compara por tricode y por nombre completo: la gente
            # escribe `t1` o `T1`, no "T1 Esports".
            for campo in ("team", "team_name"):
                valor = (getattr(jugador, campo, "") or "").strip().casefold()
                if valor and valor in equipos:
                    codigos.add(liga)
                    break
    except Exception:
        # Un JSON a medio escribir no puede tumbar la pasada: sin esto se pierde
        # el ensanchado, no los avisos que ya funcionaban.
        log.exception("No se pudieron resolver las ligas de los seguidos.")
    return codigos


def ligas_en_uso() -> list[str]:
    """Unión de las ligas que sigue algún servidor **o alguna persona**.

    Esto es lo que hay que descargar: el bot hace una pasada global sobre todas
    las cuentas y luego decide a quién avisa, así que scrapea la unión de todo lo
    que alguien esté siguiendo.

    Cada servidor entra con su cupo aplicado, no con lo que tiene guardado. Si no
    fuera así, un servidor con 4 ligas elegidas y plan gratuito haría que el bot
    descargara y consultara 4 ligas para luego avisar solo de 1: coste de
    peticiones por un dato que nadie recibe.

    Las suscripciones personales se suman aquí y no en cada llamante porque hay
    tres sitios que piden esta lista (el refresco de rosters, el calentamiento de
    rangos y la propia pasada); si la unión se hiciera fuera, olvidarla en uno
    significaría que el bot avisa a un usuario de una liga cuyas cuentas no ha
    descargado — es decir, no le avisa nunca y sin ningún error.

    Cuidado con la liga por defecto
    -------------------------------
    Un servidor que **no ha elegido** ligas sigue la LEC de forma implícita: es
    lo que devuelve `ligas_de()` y es el comportamiento de siempre, para que
    quien ya tenía el bot no note el cambio. Eso antes se cubría de casualidad,
    porque si nadie había elegido nada la unión salía vacía y se caía a la LEC al
    final de esta función.

    Con suscripciones personales esa casualidad se rompe: **un solo usuario
    suscrito a la LCK dejaba la unión en `{"lck"}`, y entonces la LEC ya no se
    descargaba** — los servidores que la seguían implícitamente se quedaban sin
    cuentas y sin ningún aviso, en silencio. Así que la implícita se resuelve
    explícitamente: cualquier servidor con canal de avisos aporta sus ligas, que
    para el que no ha elegido son la de por defecto.
    """
    datos = _cargar()
    codigos: set[str] = set()
    for clave, bloque in datos.items():
        if not isinstance(bloque, dict):
            continue
        guild_id = None if clave == "_global" else clave
        guardadas = [c for c in bloque.get("ligas", []) if c in LIGAS]
        codigos.update(guardadas[:tope_de_ligas(guild_id)])

    # Importaciones tardías: los dos módulos importan de este, así que arriba
    # serían ciclos. `channel_config` da los servidores que reciben avisos, que
    # es lo que decide si hay que descargar la liga por defecto.
    from tracking.soloq.channel_config import todos_los_canales
    from tracking.soloq.user_config import ligas_de_usuarios

    for guild_id in todos_los_canales():
        codigos.update(ligas_de(guild_id))
    codigos.update(ligas_de_usuarios())
    # Y las de los jugadores y equipos que sigue la gente: sin esto, `/track
    # Faker` guarda la suscripción y no avisa nunca. Ver `ligas_de_seguidos`.
    codigos.update(ligas_de_seguidos())

    if not codigos:
        codigos = {LIGA_POR_DEFECTO}
    return sorted(codigos)


def equipos_en_seguimiento(guild_id: int | str | None = None) -> set[str]:
    """Códigos de liga que hay que vigilar.

    Sin guild_id devuelve la unión de todas las ligas configuradas, que es lo
    que necesita la pasada global del tracker.
    """
    if guild_id is None:
        return set(ligas_en_uso())
    return set(ligas_de(guild_id))

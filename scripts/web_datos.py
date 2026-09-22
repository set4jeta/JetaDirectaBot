"""Los datos reales del bot, preparados para pintarlos en la web.

Por qué existe este módulo
--------------------------
`generar_web.py` ya tenía una regla: la web se rellena desde el código del bot
para que no pueda contradecirlo. Las páginas por liga suben la apuesta, porque
lo que hay que pintar ya no es una constante de Python sino los ficheros de
datos que el bot escribe en caliente: quién juega en cada liga, con qué cuenta y
en qué Elo, y qué campeones ha jugado últimamente.

Eso trae un problema que la landing no tenía: **los datos están incompletos a
propósito**. Hay dos niveles de detalle y no uno:

* **Barrido completo**, solo la LEC: cuentas con Riot ID, rangos refrescados en
  caliente y `last_champions` con partidas, victorias y DPM. Cuesta una petición
  a `/v1/pros/<nombre>` por jugador, así que barrer las 20 ligas serían ~900
  peticiones y no se hace para generar HTML.
* **Ranking del leaderboard**, las 20: una petición por liga trae nombre, equipo,
  rol, tier, LP, victorias, derrotas, KDA y 4 ids de campeón. No trae Riot ID ni
  historial con partidas, así que se pinta una tabla **distinta**, sin la columna
  de cuenta.

`leagues_probe.json` tiene tricodes de 11 de las 20 ligas y `ranked_data.json`
cubre 94 de las 137 cuentas con PUUID. Una página que asuma datos completos
saldría con huecos vacíos o con ceros, y una página de liga que diga "0
jugadores" es peor que no publicarla.

Así que aquí cada función dice **qué sabe y qué no**, y el generador decide qué
secciones pinta en función de eso. Lo que no hay, no se inventa ni se pinta.

Las cuatro fuentes y qué aporta cada una
---------------------------------------
* `tracking/soloq/accounts_from_teams.json` — lo bueno: 50 jugadores de la LEC
  con equipo, rol, país, contrato, cuentas con rango y `last_champions` con
  partidas, victorias, DPM y KDA. Es el dato propio que ningún tercero tiene
  agregado así, y es exactamente el material de las páginas de intención "Do".
* `tracking/soloq/leaderboards_ligas.json` — el ranking de SoloQ de las 20 ligas
  (919 jugadores), medido con una petición por liga. Es lo que convierte las 19
  páginas que solo tenían censo en rankings de verdad. Lo escribe
  `scripts/refrescar_ligas.py`.
* `tracking/soloq/leagues_probe.json` — los tricodes de los equipos de 11 ligas,
  medidos contra el leaderboard de dpm.lol. Queda como respaldo: el fichero de
  arriba trae los equipos de las 20.
* `scripts/_coste_ligas.json` — el censo medido de las 20 ligas (filas del
  leaderboard, personas distintas, equipos y cuentas estimadas). Es lo que
  permite escribir "la NLC son 74 jugadores en 15 equipos" con un número que se
  midió, no que se supuso.
"""

from __future__ import annotations

import json
import os
import re
import struct
from dataclasses import dataclass, field
from functools import lru_cache

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CUENTAS = os.path.join(RAIZ, "tracking", "soloq", "accounts_from_teams.json")
_PROBE = os.path.join(RAIZ, "tracking", "soloq", "leagues_probe.json")
_COSTE = os.path.join(RAIZ, "scripts", "_coste_ligas.json")
_RANGOS = os.path.join(RAIZ, "ranked_data.json")
_AVISOS = os.path.join(RAIZ, "tracking", "soloq", "avisos.jsonl")
_TABLAS = os.path.join(RAIZ, "tracking", "soloq", "leaderboards_ligas.json")
_PARTIDOS = os.path.join(RAIZ, "tracking", "esports", "proximos.json")

ASSETS = os.path.join(RAIZ, "assets")

_CONFIG = os.path.join(RAIZ, "config.py")


def _leer(ruta: str, defecto):
    """Lee un JSON y devuelve `defecto` si no existe o está roto.

    Sin excepciones a propósito: generar la web no puede fallar porque falte un
    fichero de datos que el bot crea al vuelo. Lo que hace es publicar menos.
    """
    try:
        with open(ruta, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return defecto


@lru_cache(maxsize=None)
def ajuste(nombre: str, defecto: int) -> int:
    """Un ajuste numérico de `config.py`, sin importar `config.py`.

    La web necesita algún número de configuración del bot —el intervalo de
    comprobación de partidas es el retardo máximo del aviso, y es un dato que la
    página de avisos tiene que decir bien—, pero `import config` arrastra
    `python-dotenv` y el intérprete con el que se generan estos ficheros no
    tiene las dependencias del bot instaladas. Ya pasó con Pillow.

    Así que se intenta importar primero (si las dependencias están, se lee el
    valor efectivo, incluido el que venga del entorno) y si falla se saca el
    valor por defecto del propio `config.py` con una expresión regular. Lo que no
    se hace es escribir el número a mano en la página: eso es exactamente lo que
    se queda desfasado sin que nadie se entere.
    """
    try:
        import config  # noqa: PLC0415  (import tardío a propósito)
        valor = getattr(config, nombre, None)
        if valor is not None:
            return int(valor)
    except Exception:  # noqa: BLE001 — falta una dependencia del bot, no un error
        pass
    try:
        with open(_CONFIG, encoding="utf-8") as fh:
            fuente = fh.read()
    except OSError:
        return defecto
    encaje = re.search(
        rf'^{re.escape(nombre)}\s*=\s*_int\(\s*"{re.escape(nombre)}"\s*,\s*(\d+)',
        fuente, re.MULTILINE,
    )
    if encaje:
        return int(encaje.group(1))
    encaje = re.search(rf"^{re.escape(nombre)}\s*=\s*(\d+)", fuente, re.MULTILINE)
    return int(encaje.group(1)) if encaje else defecto


# ---------------------------------------------------------------------- #
# Tamaño de las imágenes, sin Pillow
# ---------------------------------------------------------------------- #

def medir_imagen(ruta: str) -> tuple[int, int] | None:
    """`(ancho, alto)` de un PNG o WebP leyendo la cabecera. `None` si no puede.

    Hace falta porque la lista del usuario pide `width` y `height` explícitos en
    cada `<img>`: sin ellos el navegador no sabe cuánto sitio reservar, la página
    salta al cargar las imágenes y eso es CLS, que es una de las tres Core Web
    Vitals que Google mide.

    Está a mano en vez de con Pillow, aunque Pillow está en `requirements.txt`,
    por una razón medida: el intérprete que ejecuta los scripts de este proyecto
    (3.13) **no tiene PIL instalado** —solo lo tiene el 3.12 con el que corre el
    bot—, así que importarlo aquí haría que generar la web fallase según con qué
    python se lanzara. Leer 30 bytes de cabecera no justifica esa dependencia.

    Verificado contra Pillow sobre los tres formatos que hay en `assets/`
    (PNG, WebP VP8 y WebP VP8X): 16 de 16 coinciden.
    """
    try:
        with open(ruta, "rb") as fh:
            cabeza = fh.read(16)
            if cabeza[:8] == b"\x89PNG\r\n\x1a\n":
                ancho, alto = struct.unpack(">II", fh.read(8))
                return int(ancho), int(alto)
            if cabeza[:4] == b"RIFF" and cabeza[8:12] == b"WEBP":
                fh.seek(12)
                tipo = fh.read(4)
                fh.read(4)  # longitud del chunk, no hace falta
                if tipo == b"VP8X":
                    datos = fh.read(10)
                    ancho = int.from_bytes(datos[4:7], "little") + 1
                    alto = int.from_bytes(datos[7:10], "little") + 1
                    return ancho, alto
                if tipo == b"VP8 ":
                    datos = fh.read(10)
                    ancho = struct.unpack("<H", datos[6:8])[0] & 0x3FFF
                    alto = struct.unpack("<H", datos[8:10])[0] & 0x3FFF
                    return ancho, alto
                if tipo == b"VP8L":
                    datos = fh.read(5)
                    bits = int.from_bytes(datos[1:5], "little")
                    return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    except (OSError, struct.error, IndexError):
        return None
    return None


@dataclass(frozen=True)
class Imagen:
    """Una imagen local lista para pintar, con su tamaño ya medido."""

    #: Ruta relativa desde la carpeta de la web (`img/players/Caps.webp`).
    src: str
    ancho: int
    alto: int
    #: Ruta absoluta del original, para copiarlo a la carpeta de salida.
    origen: str


@lru_cache(maxsize=None)
def imagen_de_equipo(tricode: str) -> Imagen | None:
    """El logo de un equipo, si está descargado.

    Devuelve `None` cuando no hay fichero, y el llamante pinta la tarjeta sin
    imagen. Hay 17 logos en `assets/team_images` para 10 equipos de la LEC más
    restos de temporadas anteriores; el resto de ligas no tiene ninguno, así que
    este `None` es el caso normal y no un error.
    """
    if not tricode:
        return None
    for carpeta, ext in (("team_images", "webp"), ("teams", "webp"), ("teams", "png"),
                         ("team_logos", "png")):
        ruta = os.path.join(ASSETS, carpeta, f"{tricode.upper()}.{ext}")
        if not os.path.exists(ruta):
            continue
        medida = medir_imagen(ruta)
        if medida:
            return Imagen(f"img/teams/{tricode.upper()}.{ext}", medida[0], medida[1], ruta)
    return None


@lru_cache(maxsize=None)
def imagen_de_jugador(nombre: str) -> Imagen | None:
    """La foto de un jugador, si está descargada.

    Se busca en las dos carpetas que existen y con dos capitalizaciones, porque
    se llenaron con scripts distintos: `assets/players` guarda `Caps.webp` y
    `assets/player_images` guarda `caps.webp`. Preferir una y fallar en la otra
    dejaría fuera media plantilla.
    """
    if not nombre:
        return None
    for carpeta in ("players", "player_images"):
        for variante in (nombre, nombre.lower(), nombre.capitalize()):
            ruta = os.path.join(ASSETS, carpeta, f"{variante}.webp")
            if not os.path.exists(ruta):
                continue
            medida = medir_imagen(ruta)
            if medida:
                return Imagen(
                    f"img/players/{variante}.webp", medida[0], medida[1], ruta
                )
    return None


# ---------------------------------------------------------------------- #
# Jugadores
# ---------------------------------------------------------------------- #

#: Orden de los roles en una alineación. Es el de siempre en LoL, y el que usa
#: `ROLE_ORDER` en el bot: una plantilla ordenada alfabéticamente (ADC, Jungla,
#: Mid...) se lee mal porque nadie piensa en un equipo en ese orden.
ROLES = ("Top", "Jungle", "Mid", "Bot", "Support")
_PESO_ROL = {r.lower(): i for i, r in enumerate(ROLES)}

#: Peso de cada liga para comparar rangos. Mismo criterio que
#: `utils/rank_utils.py`, reescrito aquí para no arrastrar el módulo del bot al
#: generador (y porque aquí los tiers vienen en dos formatos distintos: la cuenta
#: los trae en mayúsculas y `ranked_data.json` capitalizados).
_TIERS = ("IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD",
          "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER")
_PESO_TIER = {t: i + 1 for i, t in enumerate(_TIERS)}
_DIVISIONES = {"IV": 1, "III": 2, "II": 3, "I": 4}


def valor_rango(rango: dict | None) -> int:
    """Entero comparable de un rango. 0 si no hay o no se reconoce."""
    if not isinstance(rango, dict):
        return 0
    tier = str(rango.get("tier") or "").strip().upper()
    peso = _PESO_TIER.get(tier, 0)
    if not peso:
        return 0
    division = str(rango.get("rank") or rango.get("division") or "").strip().upper()
    try:
        lp = int(rango.get("lp") or 0)
    except (TypeError, ValueError):
        lp = 0
    return peso * 1_000_000 + _DIVISIONES.get(division, 0) * 10_000 + lp


def texto_rango(rango: dict | None) -> str:
    """`"Challenger 5399 LP"` o `"Diamante I · 75 LP"`. Vacío si no hay rango.

    Los tiers se traducen porque la web está en español y "Emerald" en una página
    en español canta; los tres altos (Master, Grandmaster, Challenger) no llevan
    división porque no la tienen.
    """
    if not isinstance(rango, dict):
        return ""
    tier = str(rango.get("tier") or "").strip().upper()
    if tier not in _PESO_TIER:
        return ""
    nombres = {
        "IRON": "Hierro", "BRONZE": "Bronce", "SILVER": "Plata", "GOLD": "Oro",
        "PLATINUM": "Platino", "EMERALD": "Esmeralda", "DIAMOND": "Diamante",
        "MASTER": "Máster", "GRANDMASTER": "Gran Máster", "CHALLENGER": "Challenger",
    }
    nombre = nombres[tier]
    try:
        lp = int(rango.get("lp") or 0)
    except (TypeError, ValueError):
        lp = 0
    if tier in ("MASTER", "GRANDMASTER", "CHALLENGER"):
        return f"{nombre} · {lp} LP"
    division = str(rango.get("rank") or rango.get("division") or "").strip().upper()
    return f"{nombre} {division} · {lp} LP".replace("  ", " ").strip()


@dataclass(frozen=True)
class Campeon:
    """Un campeón del historial reciente de un jugador."""

    nombre: str
    partidas: int
    victorias: int
    dpm: float
    kda: float

    @property
    def winrate(self) -> int:
        """Redondeado a entero. Con 11 partidas, un decimal es ruido."""
        if not self.partidas:
            return 0
        return round(self.victorias * 100 / self.partidas)


@dataclass(frozen=True)
class Jugador:
    """Un pro con lo que la web necesita de él."""

    nombre: str
    equipo: str            # tricode
    equipo_nombre: str     # "Fnatic"
    rol: str
    liga: str
    pais: str
    edad: int | None
    #: Mejor cuenta: `(riot_id, rango, plataforma)`. Riot ID puede ir vacío.
    riot_id: str = ""
    rango: dict | None = None
    plataforma: str = ""
    cuentas: int = 0
    campeones: tuple[Campeon, ...] = ()

    @property
    def peso_rol(self) -> int:
        return _PESO_ROL.get(self.rol.lower(), len(ROLES))

    @property
    def valor(self) -> int:
        return valor_rango(self.rango)

    @property
    def rango_texto(self) -> str:
        return texto_rango(self.rango)


def _mejor_cuenta(cuentas: list[dict], rangos: dict) -> tuple[str, dict | None, str, int]:
    """La cuenta con más Elo de un jugador: `(riot_id, rango, plataforma, total)`.

    Un pro tiene varias cuentas (172 cuentas para 50 jugadores en la LEC) y la
    primera del fichero no es la mejor: puede ser una secundaria en Diamante
    teniendo la principal en Challenger. Es el mismo criterio que `/team` aplica
    en el bot con `rank_utils.mejor_cuenta`.

    Se mira el rango de dos sitios: el que la cuenta trae embebido (106 de 137) y
    `ranked_data.json`, que es el que el bot refresca en caliente (94 de 137). Se
    prefiere el más alto de los dos, no uno fijo: el embebido puede ser de la
    última descarga de rosters y el refrescado de hace unos minutos, y cuál está
    más al día depende de cuándo se ejecutó cada cosa.
    """
    mejor_valor = -1
    mejor: tuple[str, dict | None, str, int] = ("", None, "", len(cuentas))
    for cuenta in cuentas:
        if not isinstance(cuenta, dict):
            continue
        candidatos = [cuenta.get("rank")]
        puuid = cuenta.get("puuid")
        if puuid and puuid in rangos:
            candidatos.append(rangos[puuid])
        rango = max(candidatos, key=valor_rango, default=None)
        valor = valor_rango(rango)
        if valor <= mejor_valor:
            continue
        rid = cuenta.get("riot_id") or {}
        nombre = (rid.get("game_name") or "").strip()
        tag = (rid.get("tag_line") or "").strip()
        mejor = (
            f"{nombre}#{tag}" if nombre and tag else nombre,
            rango,
            str(cuenta.get("platform") or "").upper(),
            len(cuentas),
        )
        mejor_valor = valor
    return mejor


@lru_cache(maxsize=1)
def jugadores() -> tuple[Jugador, ...]:
    """Todos los pros que hay descargados, con su mejor cuenta y sus campeones.

    Hoy son 50 y todos de la LEC, porque es la única liga barrida. El generador
    tiene que preguntar `jugadores_de(liga)` y aceptar una lista vacía: publicar
    una página de la LCK con la plantilla vacía es peor que publicarla solo con
    los equipos y el censo medido, que sí se saben.
    """
    crudos = _leer(_CUENTAS, [])
    rangos = _leer(_RANGOS, {})
    if not isinstance(crudos, list):
        return ()

    salida = []
    for p in crudos:
        if not isinstance(p, dict):
            continue
        nombre = (p.get("name") or p.get("displayName") or "").strip()
        if not nombre:
            continue
        riot_id, rango, plataforma, total = _mejor_cuenta(
            [c for c in (p.get("accounts") or []) if isinstance(c, dict)], rangos
        )
        campeones = tuple(
            Campeon(
                nombre=str(c.get("champion_name") or "").strip(),
                partidas=int(c.get("games") or 0),
                victorias=int(c.get("wins") or 0),
                dpm=float(c.get("avg_dpm_score") or 0.0),
                kda=float(c.get("avg_kda") or 0.0),
            )
            for c in (p.get("last_champions") or [])
            if isinstance(c, dict) and (c.get("champion_name") or "").strip()
        )
        salida.append(Jugador(
            nombre=nombre,
            equipo=(p.get("team") or "").strip().upper(),
            equipo_nombre=(p.get("team_name") or p.get("team") or "").strip(),
            rol=(p.get("role") or "").strip(),
            liga=(p.get("league") or "").strip().lower(),
            pais=(p.get("country") or "").strip(),
            edad=int(p["age"]) if isinstance(p.get("age"), int) else None,
            riot_id=riot_id,
            rango=rango,
            plataforma=plataforma,
            cuentas=total,
            campeones=campeones,
        ))
    return tuple(salida)


def jugadores_de(codigo: str) -> list[Jugador]:
    """Los pros de una liga, ordenados por Elo de mayor a menor.

    Ordenar por Elo y no por equipo es deliberado: la página de una liga es, en
    la práctica, un ranking de SoloQ, y es lo que alguien viene a mirar. Los que
    no tienen rango van al final en vez de omitirse, porque siguen siendo parte de
    la plantilla y quitarlos haría que la lista no cuadrara con el censo.
    """
    return sorted(
        (j for j in jugadores() if j.liga == codigo),
        key=lambda j: (-j.valor, j.nombre.lower()),
    )


def plantilla_de(tricode: str) -> list[Jugador]:
    """Los jugadores de un equipo, en orden de rol."""
    return sorted(
        (j for j in jugadores() if j.equipo == tricode.upper()),
        key=lambda j: (j.peso_rol, j.nombre.lower()),
    )


# ---------------------------------------------------------------------- #
# Ranking del leaderboard: las 20 ligas, con menos detalle
# ---------------------------------------------------------------------- #
#
# Esta es la mitad barata del dato. `Jugador` sale de barrer la liga jugador por
# jugador y solo existe para la LEC; `Clasificado` sale de una petición por liga
# y existe para las 20. Son tipos distintos **a propósito**: si fueran el mismo
# con campos vacíos, la plantilla no podría distinguir "no tiene Riot ID porque
# no se ha barrido" de "no tiene Riot ID porque no se le encontró", y acabaría
# pintando una columna vacía, que es justo lo que no se quiere.

@dataclass(frozen=True)
class Clasificado:
    """Una entrada del ranking de SoloQ de una liga.

    Sin Riot ID y sin historial de campeones con partidas: el leaderboard no los
    da. Lo que sí da, y no está agregado en ninguna web pública por liga, es el
    Elo de la mejor cuenta de cada pro con su racha de victorias y su KDA.
    """

    nombre: str
    equipo: str
    rol: str
    tier: str
    division: str
    lp: int
    victorias: int
    derrotas: int
    kda: float
    #: Ids de campeón, no nombres. Se resuelven al pintar con el catálogo
    #: vigente, así que refrescar el catálogo arregla también lo ya escrito.
    campeones: tuple[str, ...] = ()
    cuentas: int = 1

    @property
    def rango(self) -> dict:
        """El rango en el formato que entienden `valor_rango` y `texto_rango`."""
        return {"tier": self.tier, "rank": self.division, "lp": self.lp}

    @property
    def valor(self) -> int:
        return valor_rango(self.rango)

    @property
    def rango_texto(self) -> str:
        return texto_rango(self.rango)

    @property
    def partidas(self) -> int:
        return self.victorias + self.derrotas

    @property
    def winrate(self) -> int:
        """Redondeado a entero, y 0 si no hay partidas.

        Las cuatro filas sin `tier` del leaderboard vienen también con 0
        victorias y 0 derrotas, así que este 0 no se pinta: la plantilla escribe
        un guion cuando no hay partidas.
        """
        if not self.partidas:
            return 0
        return round(self.victorias * 100 / self.partidas)

    @property
    def peso_rol(self) -> int:
        return _PESO_ROL.get(self.rol.lower(), len(ROLES))


@lru_cache(maxsize=1)
def _catalogo_campeones() -> dict[str, str]:
    """`{id: nombre}` del catálogo de campeones, o vacío si no se puede leer.

    Se importa el módulo del bot en vez de releer el JSON para que no haya dos
    lecturas del mismo fichero que puedan divergir. `cache/champion_cache.py` es
    solo `json` y `os`, así que no arrastra dependencias al generador; si aun así
    fallara, se devuelve vacío y la columna de campeones no se pinta.
    """
    try:
        from cache.champion_cache import CHAMPION_ID_TO_NAME  # noqa: PLC0415
        return dict(CHAMPION_ID_TO_NAME)
    except Exception:  # noqa: BLE001 — sin catálogo se publica menos, no se falla
        return {}


def nombre_de_campeon(champion_id: str) -> str:
    """`"904"` -> `"Zaahen"`. Cadena vacía si el id no está en el catálogo.

    Vacío y no `"ID 904"`: en un embed de Discord ese texto es un aviso de que
    hay que refrescar el catálogo, pero en una página pública es basura, y la
    plantilla ya sabe omitir lo que viene vacío.
    """
    return _catalogo_campeones().get(str(champion_id), "")


@lru_cache(maxsize=1)
def _tablas() -> dict[str, dict]:
    crudo = _leer(_TABLAS, {})
    if not isinstance(crudo, dict):
        return {}
    ligas = crudo.get("ligas")
    return ligas if isinstance(ligas, dict) else {}


def fecha_de_tablas() -> str:
    """Cuándo se midieron los rankings, en `YYYY-MM-DD`. Vacío si no se sabe.

    La página lo cita porque un Elo sin fecha no se puede verificar, y porque la
    recencia es lo que decide si un sistema que responde preguntas usa este dato
    o el de otro.
    """
    crudo = _leer(_TABLAS, {})
    sello = crudo.get("generado") if isinstance(crudo, dict) else None
    return str(sello)[:10] if sello else ""


def clasificacion_de(codigo: str, *, tope: int = 0) -> list[Clasificado]:
    """El ranking de SoloQ de una liga, de más Elo a menos.

    Ya viene ordenado del fichero, pero se reordena aquí igualmente: el orden de
    la página no debe depender de que quien escribió el JSON lo dejara bien.
    """
    filas = (_tablas().get(codigo) or {}).get("jugadores")
    if not isinstance(filas, list):
        return []

    salida = []
    for f in filas:
        if not isinstance(f, dict):
            continue
        nombre = str(f.get("nombre") or "").strip()
        if not nombre:
            continue
        salida.append(Clasificado(
            nombre=nombre,
            equipo=str(f.get("equipo") or "").strip().upper(),
            rol=str(f.get("rol") or "").strip(),
            tier=str(f.get("tier") or "").strip().upper(),
            division=str(f.get("division") or "").strip().upper(),
            lp=int(f.get("lp") or 0),
            victorias=int(f.get("victorias") or 0),
            derrotas=int(f.get("derrotas") or 0),
            kda=float(f.get("kda") or 0.0),
            campeones=tuple(
                str(c) for c in (f.get("campeones") or []) if str(c).strip()
            ),
            cuentas=int(f.get("cuentas") or 1),
        ))

    salida.sort(key=lambda c: (-c.valor, c.nombre.lower()))
    return salida[:tope] if tope else salida


def campeones_del_ranking(codigo: str, *, tope: int = 10) -> list[UsoCampeon]:
    """Los campeones más presentes en el ranking de una liga.

    Se cuenta **presencia**, no partidas: `mostChamps` dice "estos cuatro son los
    que más juega" sin decir cuántas veces, así que lo único que se puede afirmar
    es en cuántos de los rankings aparece. Por eso `partidas` sale a 0 y la
    plantilla pinta una tabla de dos columnas en vez de la de la LEC, que sí
    tiene partidas, winrate y DPM.

    No se mezcla con `campeones_de()`. Ese agrega `last_champions`, que es otra
    ventana y otra unidad; comprobado sobre 73 jugadores de la LEC, el conjunto
    de campeones de las dos fuentes no coincide en ningún caso.
    """
    conteo: dict[str, dict] = {}
    for c in clasificacion_de(codigo):
        for cid in c.campeones:
            nombre = nombre_de_campeon(cid)
            if not nombre:
                continue
            entrada = conteo.setdefault(nombre, {"jugadores": set(), "top": ("", -1)})
            entrada["jugadores"].add(c.nombre)
            # "Quien más lo juega" no se puede saber; el mejor sustituto honesto
            # es el jugador de más Elo que lo lleva, que es un dato verificable.
            if c.valor > entrada["top"][1]:
                entrada["top"] = (c.nombre, c.valor)

    salida = [
        UsoCampeon(
            nombre=nombre,
            partidas=0,
            victorias=0,
            jugadores=len(d["jugadores"]),
            top=d["top"][0],
        )
        for nombre, d in conteo.items()
    ]
    salida.sort(key=lambda u: (-u.jugadores, u.nombre))
    return salida[:tope]


# ---------------------------------------------------------------------- #
# Equipos y censo por liga
# ---------------------------------------------------------------------- #

@dataclass(frozen=True)
class Censo:
    """Lo que se midió de una liga contra el leaderboard de dpm.lol.

    Los cuatro números salen de `tracking/soloq/leaderboards_ligas.json` cuando la
    liga está ahí, y de `scripts/_coste_ligas.json` —la medición con la que se
    fijó `MAX_LIGAS_POR_SERVIDOR`— cuando no.

    El orden importa y no es una preferencia estética: el fichero de rankings
    trae las filas y las personas de la **misma** descarga que se está pintando en
    la tabla. Si el censo saliera del fichero viejo, una liga que hoy tiene 35
    jugadores en la tabla podría llevar "34 jugadores" en el resumen, y la página
    se contradiría a sí misma en dos párrafos.
    """

    filas: int = 0        # entradas del leaderboard (una cuenta por fila)
    personas: int = 0     # jugadores distintos
    equipos: int = 0
    cuentas: int = 0      # estimadas con el multiplicador 3,44 medido en la LEC

    @property
    def hay(self) -> bool:
        return self.personas > 0


@lru_cache(maxsize=1)
def _censos() -> dict[str, Censo]:
    crudo = _leer(_COSTE, {})
    salida: dict[str, Censo] = {}
    if isinstance(crudo, dict):
        salida = {
            codigo: Censo(
                filas=int(d.get("filas") or 0),
                personas=int(d.get("personas") or 0),
                equipos=int(d.get("equipos") or 0),
                cuentas=int(d.get("cuentas_estimadas") or 0),
            )
            for codigo, d in crudo.items() if isinstance(d, dict)
        }

    for codigo, d in _tablas().items():
        if not isinstance(d, dict):
            continue
        personas = len(d.get("jugadores") or [])
        if not personas:
            continue
        salida[codigo] = Censo(
            filas=int(d.get("filas") or 0) or personas,
            personas=personas,
            equipos=len(d.get("equipos") or []),
            cuentas=int(d.get("cuentas_estimadas") or 0),
        )
    return salida


def censo_de(codigo: str) -> Censo:
    """El censo medido de una liga, o uno vacío. Nunca `None`."""
    return _censos().get(codigo, Censo())


@lru_cache(maxsize=1)
def _tricodes() -> dict[str, tuple[str, ...]]:
    crudo = _leer(_PROBE, {})
    if not isinstance(crudo, dict):
        return {}
    return {
        codigo: tuple(sorted(str(t).strip().upper() for t in equipos if str(t).strip()))
        for codigo, equipos in crudo.items() if isinstance(equipos, list)
    }


def equipos_de(codigo: str) -> list[str]:
    """Tricodes de los equipos de una liga.

    Tres fuentes por orden de frescura: los jugadores barridos (que traen el
    nombre completo del equipo), el ranking del leaderboard (que cubre las 20
    ligas y se descargó hoy) y el sondeo de `leagues_probe.json` (11 ligas, más
    viejo). La primera que tenga algo, gana.

    Con la segunda fuente esto ya no devuelve lista vacía para ninguna liga del
    catálogo, así que las 20 páginas pintan sus equipos. Se conserva igualmente la
    tercera y el respaldo vacío: si el fichero de rankings no existe —repositorio
    recién clonado, disco de Render reiniciado— la web se genera igual, con menos.
    """
    de_jugadores = sorted({j.equipo for j in jugadores() if j.liga == codigo and j.equipo})
    if de_jugadores:
        return de_jugadores
    del_ranking = (_tablas().get(codigo) or {}).get("equipos")
    if isinstance(del_ranking, list) and del_ranking:
        return sorted(str(t).strip().upper() for t in del_ranking if str(t).strip())
    return list(_tricodes().get(codigo, ()))


def nombre_de_equipo(tricode: str) -> str:
    """`"FNC"` -> `"Fnatic"`, si se sabe. Si no, el propio tricode.

    El nombre completo solo está en las fichas de jugadores, así que solo se sabe
    de las ligas descargadas. Devolver el tricode como respaldo es correcto:
    "SHFT" es como se le llama al equipo en la práctica.
    """
    for j in jugadores():
        if j.equipo == tricode.upper() and j.equipo_nombre:
            return j.equipo_nombre
    return tricode.upper()


# ---------------------------------------------------------------------- #
# Agregados que solo se pueden calcular con datos propios
# ---------------------------------------------------------------------- #
#
# Esto es lo que la lista del usuario llama "alimentarlos con datos propios": no
# es contenido que un tercero pueda copiar de una wiki, porque sale de cruzar los
# rosters con los rangos de las cuentas y con el historial de campeones. Un LLM
# que quiera responder "qué campeones están jugando los mid de la LEC" no tiene
# de dónde sacarlo salvo de una página que lo publique.

@dataclass(frozen=True)
class UsoCampeon:
    """Un campeón agregado sobre varios jugadores."""

    nombre: str
    partidas: int
    victorias: int
    jugadores: int
    #: Quién lo juega más, para poder citarlo en el texto.
    top: str = ""
    _dpm: float = field(default=0.0, repr=False)

    @property
    def winrate(self) -> int:
        if not self.partidas:
            return 0
        return round(self.victorias * 100 / self.partidas)

    @property
    def dpm(self) -> int:
        return round(self._dpm)


def campeones_de(codigo: str, *, rol: str = "", tope: int = 10) -> list[UsoCampeon]:
    """Los campeones más jugados en una liga, opcionalmente filtrando por rol.

    Agrega `last_champions` de todos los jugadores. El DPM se pondera por
    partidas y no se promedian los promedios: un jugador con 11 partidas y otro
    con 1 no pueden pesar igual, y hacer la media de las medias es el error que
    convierte una estadística en un número decorativo.

    Ordena por partidas y no por winrate a propósito. Un campeón con 2 partidas y
    100 % de victorias saldría primero y no significa nada; lo que se está
    midiendo es qué se está jugando.
    """
    acumulado: dict[str, dict] = {}
    for j in jugadores():
        if j.liga != codigo:
            continue
        if rol and j.rol.lower() != rol.lower():
            continue
        for c in j.campeones:
            entrada = acumulado.setdefault(
                c.nombre,
                {"partidas": 0, "victorias": 0, "dpm": 0.0, "jugadores": set(), "top": ("", 0)},
            )
            entrada["partidas"] += c.partidas
            entrada["victorias"] += c.victorias
            entrada["dpm"] += c.dpm * c.partidas
            entrada["jugadores"].add(j.nombre)
            if c.partidas > entrada["top"][1]:
                entrada["top"] = (j.nombre, c.partidas)

    salida = [
        UsoCampeon(
            nombre=nombre,
            partidas=d["partidas"],
            victorias=d["victorias"],
            jugadores=len(d["jugadores"]),
            top=d["top"][0],
            _dpm=d["dpm"] / d["partidas"] if d["partidas"] else 0.0,
        )
        for nombre, d in acumulado.items()
    ]
    salida.sort(key=lambda u: (-u.partidas, u.nombre))
    return salida[:tope]


# ---------------------------------------------------------------------- #
# Avisos publicados de verdad
# ---------------------------------------------------------------------- #
#
# Esto es lo que faltaba para que `avisos.html` fuera un histórico y no solo un
# ejemplo del formato. Lo escribe `tracking/soloq/avisos_log.py` cuando un aviso
# sale de verdad, y aquí solo se lee.
#
# Regla de siempre: si el fichero no existe —bot recién desplegado, disco
# efímero de Render reiniciado— esto devuelve lista vacía y la página pinta el
# ejemplo en lugar del histórico. Lo que no se hace es enseñar una tabla vacía
# con un "aún no hay avisos", que es admitir que la función no se usa.

@dataclass(frozen=True)
class Aviso:
    """Un aviso que el bot publicó, tal y como quedó registrado."""

    momento: int          # epoch en segundos
    jugador: str
    equipo: str           # tricode
    liga: str             # código de liga
    campeon: str
    rango: str
    cuenta: str
    partida: str

    @property
    def fecha(self) -> str:
        """`AAAA-MM-DD`, para el `<time datetime=...>`."""
        from datetime import datetime, timezone

        return datetime.fromtimestamp(self.momento, timezone.utc).strftime("%Y-%m-%d")

    @property
    def hora(self) -> str:
        """`HH:MM` en UTC.

        En UTC y no en la hora local de quien genera: el HTML se sirve igual a
        todo el mundo, así que una hora local sin zona sería incorrecta para casi
        todos los que la leen. El `<time>` lleva la marca completa.
        """
        from datetime import datetime, timezone

        return datetime.fromtimestamp(self.momento, timezone.utc).strftime("%H:%M")

    @property
    def sello(self) -> str:
        """El `datetime` completo en ISO 8601 con zona, para el atributo."""
        from datetime import datetime, timezone

        return datetime.fromtimestamp(self.momento, timezone.utc).isoformat()


def avisos(tope: int = 20) -> list[Aviso]:
    """Los últimos avisos publicados, del más reciente al más antiguo.

    Lee el JSONL a mano en vez de importar `tracking.soloq.avisos_log` por la
    misma razón que `ajuste()` no importa `config`: ese módulo arrastra
    `utils.logger`, y el intérprete que genera la web no tiene las dependencias
    del bot. El formato es una línea por objeto, así que leerlo aquí son cuatro
    líneas y no una duplicación de lógica.

    Se descarta cualquier línea que no sea JSON válido o que no traiga jugador:
    una línea a medias por un SIGTERM en pleno volcado es un caso esperado.

    Se recorre de abajo arriba —el fichero es de solo añadir, así que el final es
    lo más nuevo— y además se ordena por marca de tiempo antes de devolver. Lo
    segundo parece redundante y no lo es: la página afirma por escrito "del más
    reciente al más antiguo", y basta un ajuste de reloj del contenedor o un
    fichero recompuesto de dos trozos para que el orden del fichero deje de ser
    el cronológico. Ordenar 20 elementos es gratis; publicar una lista que
    contradice su propio encabezado, no.
    """
    try:
        with open(_AVISOS, encoding="utf-8") as fh:
            lineas = fh.readlines()
    except OSError:
        return []

    salida: list[Aviso] = []
    for linea in reversed(lineas):
        linea = linea.strip()
        if not linea:
            continue
        try:
            d = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict) or not d.get("jugador"):
            continue
        try:
            momento = int(d.get("ts") or 0)
        except (TypeError, ValueError):
            continue
        if momento <= 0:
            continue
        salida.append(Aviso(
            momento=momento,
            jugador=str(d.get("jugador") or ""),
            equipo=str(d.get("equipo") or "").upper(),
            liga=str(d.get("liga") or ""),
            campeon=str(d.get("campeon") or ""),
            rango=str(d.get("rango") or ""),
            cuenta=str(d.get("cuenta") or ""),
            partida=str(d.get("partida") or ""),
        ))
        if len(salida) >= tope:
            break
    salida.sort(key=lambda a: -a.momento)
    return salida


# ---------------------------------------------------------------------- #
# Próximos partidos profesionales
# ---------------------------------------------------------------------- #

# Esto es lo único de la web que no sale de SoloQ, y está aquí por lo mismo que
# está el resto: es un dato medido que el bot ya sabe pedir. Lo escribe
# `scripts/refrescar_partidos.py` desde el calendario de lolesports.
#
# La decisión que importa: **se pinta en el HTML y no se pide por JavaScript**.
# Un calendario que solo existe después de un `fetch` no lo ve el rastreador, y
# es justo el contenido que da la frescura que el resto del sitio no tiene. El
# JavaScript, si algún día se añade, será para actualizar lo que ya está escrito.


@dataclass(frozen=True)
class Equipo:
    """Un equipo dentro de un partido del calendario."""

    nombre: str
    codigo: str        # tricode
    logo: str          # URL absoluta en static.lolesports.com, ya en https
    victorias: int | None
    derrotas: int | None

    @property
    def record(self) -> str:
        """`"6-0"`, o cadena vacía si la fuente no lo trae o no dice nada.

        Los dos a la vez o ninguno: un `"6-"` es peor que no decir nada, y la
        API deja los dos en `null` para los partidos de fase eliminatoria en los
        que el equipo aún no está confirmado.

        Y `0-0` también se descarta, que es el caso de casi todos los partidos de
        playoffs: el récord está ahí para ver la forma del equipo de un vistazo, y
        un `0-0` no dice ninguna. Ocupa sitio en la tarjeta y no informa.
        """
        if self.victorias is None or self.derrotas is None:
            return ""
        if not self.victorias and not self.derrotas:
            return ""
        return f"{self.victorias}-{self.derrotas}"


@dataclass(frozen=True)
class Partido:
    """Un partido profesional que aún no ha terminado."""

    inicio: str            # ISO 8601 con Z, tal como viene
    liga: str              # código de liga del catálogo del bot
    liga_nombre: str       # el nombre oficial de lolesports
    fase: str              # "Week 4", "Playoffs"...
    estado: str            # "unstarted" | "inProgress"
    bo: int | None
    equipos: tuple[Equipo, ...]

    @property
    def en_juego(self) -> bool:
        return self.estado == "inProgress"

    @property
    def momento(self):
        """`datetime` con zona, o `None` si la marca viene mal.

        Se parsea aquí y no en el generador porque las tres propiedades de abajo
        lo necesitan, y `fromisoformat` no acepta la `Z` antes de Python 3.11.
        """
        from datetime import datetime

        try:
            return datetime.fromisoformat(self.inicio.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            return None

    @property
    def dia(self) -> str:
        """`AAAA-MM-DD` en UTC, para agrupar y para el `<time datetime=...>`."""
        momento = self.momento
        return momento.strftime("%Y-%m-%d") if momento else ""

    @property
    def hora(self) -> str:
        """`HH:MM` en UTC.

        En UTC por lo mismo que los avisos: el HTML es el mismo para todo el
        mundo, así que una hora local sin zona sería incorrecta para casi todos.
        El atributo `datetime` lleva la marca completa y el navegador puede
        traducirla.
        """
        momento = self.momento
        return momento.strftime("%H:%M") if momento else ""


def partidos(codigo: str = "", *, tope: int = 0) -> list[Partido]:
    """Los próximos partidos, en orden cronológico. `codigo` filtra por liga.

    Devuelve `[]` cuando no hay fichero, que es el caso de una instalación
    limpia: la web sale sin la sección y no con una vacía.
    """
    documento = _leer(_PARTIDOS, {})
    if not isinstance(documento, dict):
        return []

    salida: list[Partido] = []
    for bruto in documento.get("partidos") or []:
        if not isinstance(bruto, dict):
            continue
        if codigo and bruto.get("liga") != codigo:
            continue
        equipos = tuple(
            Equipo(
                nombre=str(eq.get("nombre") or ""),
                codigo=str(eq.get("codigo") or "").upper(),
                logo=str(eq.get("logo") or ""),
                victorias=eq.get("victorias"),
                derrotas=eq.get("derrotas"),
            )
            for eq in (bruto.get("equipos") or [])
            if isinstance(eq, dict)
        )
        if len(equipos) != 2:
            continue
        salida.append(Partido(
            inicio=str(bruto.get("inicio") or ""),
            liga=str(bruto.get("liga") or ""),
            liga_nombre=str(bruto.get("liga_nombre") or ""),
            fase=str(bruto.get("fase") or ""),
            estado=str(bruto.get("estado") or "unstarted"),
            bo=bruto.get("bo") if isinstance(bruto.get("bo"), int) else None,
            equipos=equipos,
        ))

    salida.sort(key=lambda p: p.inicio)
    return salida[:tope] if tope else salida


def fecha_de_partidos() -> str:
    """Cuándo se refrescó el calendario. Cadena vacía si no hay fichero."""
    documento = _leer(_PARTIDOS, {})
    if not isinstance(documento, dict):
        return ""
    return str(documento.get("generado") or "")


def ligas_con_partido() -> set[str]:
    """Los códigos de liga que tienen algún partido publicable.

    Lo usa el generador para decidir si una página de liga lleva sección de
    calendario. Es un `set` y no una lista porque la pregunta siempre es de
    pertenencia.
    """
    return {p.liga for p in partidos()}



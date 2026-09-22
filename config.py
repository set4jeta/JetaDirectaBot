"""Configuración central del bot.

Todo lo que es configurable o sensible se lee aquí, del entorno (`.env`), en un
solo sitio. Antes las claves estaban repartidas por el código: la de lolesports
y la de Firebase dentro de `esports_extension/services/api.py`, un token OAuth
de Twitch dentro de `chat_winner_detector.py` y la misma clave de lolesports
copiada en tres scripts sueltos.

Regla: **ningún secreto en el código**. Si un valor obligatorio falta, el bot lo
dice al arrancar en vez de fallar a media ejecución.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


# ---------------------------------------------------------------------- #
# Secretos obligatorios
# ---------------------------------------------------------------------- #

# Clave de la API de Riot. La de producción da 500 req/10s y 30000 req/10min.
RIOT_API_KEY = _str("RIOT_API_KEY")

# Token del bot de Discord.
DISCORD_TOKEN = _str("DISCORD_TOKEN")


# ---------------------------------------------------------------------- #
# APIs públicas (tienen valor por defecto, pero se pueden sobreescribir)
# ---------------------------------------------------------------------- #

# Esta es la clave pública que usa lolesports.com desde el navegador: no es un
# secreto, pero se saca del código para poder cambiarla sin editar nada.
LOL_API_KEY = _str("LOL_API_KEY", "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z")

# Clave web pública del proyecto lolesports-ink en Firestore.
FIREBASE_API_KEY = _str("FIREBASE_API_KEY", "AIzaSyAWJjAJglbZ8L2gAPipdMMfcQQWdC4UOMQ")


# ---------------------------------------------------------------------- #
# Secretos opcionales (la función se desactiva si no están)
# ---------------------------------------------------------------------- #

# Token OAuth de Twitch para deducir el ganador por el chat. Es un secreto real.
TWITCH_OAUTH_TOKEN = _str("TWITCH_OAUTH_TOKEN")


# ---------------------------------------------------------------------- #
# Ajustes de funcionamiento
# ---------------------------------------------------------------------- #

CHECK_GAMES_INTERVAL = _int("CHECK_GAMES_INTERVAL", 30)
TRACKER_CONCURRENCY = _int("TRACKER_CONCURRENCY", 12)
INFOPLAYERS_PER_HOUR = _int("INFOPLAYERS_PER_HOUR", 60)
RANKED_CACHE_TTL = _int("RANKED_CACHE_TTL", 120)

# ---------------------------------------------------------------------- #
# Almacén persistente de rangos (ranked_data.json)
# ---------------------------------------------------------------------- #

# Cuánto se conserva un rango en disco. El fichero tenía 1885 entradas, 1154
# de julio de 2025 y 710 tan viejas que ni llevaban timestamp: un rango de hace
# un año no sirve para nada y además hacía el fichero (y cada escritura) enorme.
RANK_DATA_MAX_AGE_DAYS = _int("RANK_DATA_MAX_AGE_DAYS", 30)

# Tope de entradas. El tracker guarda el rango de los 10 participantes de cada
# partida detectada, incluidos rivales aleatorios, así que sin tope el fichero
# crece para siempre.
RANK_DATA_MAX_ENTRIES = _int("RANK_DATA_MAX_ENTRIES", 4000)

# Antigüedad máxima para dar por bueno un rango cacheado **que se sabe que ha
# jugado**. Se usa en los embeds: enseñar un rango de antes de su último partido
# es enseñar un dato que ya no es.
#
# Ojo con lo que significa ahora (22-09-2026): esto **ya no** es la ventana de
# validez general. La validez la decide la actividad —un rango guardado después
# del último partido observado no caduca nunca, juegue o no— y este número solo
# entra cuando consta que la cuenta ha jugado después de guardarlo, o cuando no
# hay ninguna señal de actividad. Por eso puede ser 30 min en vez de 6 h: antes
# 6 h era el compromiso entre datos viejos y peticiones de más; ahora solo se
# aplica a cuentas que sí han jugado, y ahí lo correcto es pedirlo ya.
#   Ver `core/rank_store.py` (cabecera) y `tracking/soloq/rank_warm.py`.
RANK_CACHE_MAX_AGE = _int("RANK_CACHE_MAX_AGE", 1800)

# Ventana de `rank_warm`: en cuánto tiempo tiene que pasar por todas las cuentas
# **sin dato válido**. Estaba atada a `RANK_CACHE_MAX_AGE` y se ha separado: con
# la validez por actividad, atarlas multiplicaba por 18 el trabajo de esa tarea
# (de 9 a ~160 peticiones por vuelta) sin ganar nada, porque lo que refresca son
# cuentas que no tienen rango, no cuentas que caducan.
RANK_WARM_WINDOW = _int("RANK_WARM_WINDOW", 6 * 3600)

# Hueco máximo sin pasadas antes de dar por sospechosos los rangos guardados. Si
# el bot estuvo apagado más que esto, una partida pudo pasar sin que nadie la
# viera y no se puede afirmar que los rangos de antes sigan valiendo.
RANK_HUECO_MAX = _int("RANK_HUECO_MAX", 900)

# Cada cuánto, como máximo, se vuelca el almacén a disco. Antes cada
# `save_rank_data` reescribía los 316 KB completos: un `!team` de 25 cuentas
# escribía casi 8 MB y una partida detectada, 3 MB.
RANK_FLUSH_INTERVAL = _int("RANK_FLUSH_INTERVAL", 30)

# Refresco en segundo plano de los rangos de las cuentas seguidas, para que
# `!team` y `!ranking` tengan siempre datos frescos sin esperar a la API.
RANK_WARM = _int("RANK_WARM", 1) == 1
RANK_WARM_INTERVAL = _int("RANK_WARM_INTERVAL", 300)

# ---------------------------------------------------------------------- #
# Delay del espectador
# ---------------------------------------------------------------------- #

# Segundos que el servidor de espectadores va por detrás de la partida real.
#
# **Solo se usa de respaldo.** `spectator-v5` manda `gameStartTime` (reloj real)
# y `gameLength` (reloj del espectador) en la misma respuesta, así que el delay
# se mide restándolos en vez de suponerlo; ver `utils/game_clock.py`. Esta
# constante entra en juego cuando falta uno de los dos, típicamente en pantalla
# de carga (`gameStartTime == 0`).
#
# Medido contra la API con `scripts/probe_spectator_timing.py` sobre partidas
# reales: `gameLength` **no** avanza segundo a segundo, sube a saltos de ~62 s
# (la longitud de chunk del espectador), y se queda entre ~150 s y ~206 s por
# detrás de `ahora - gameStartTime`.
#
# 180 s es el valor oficial de Riot y el que se deja por defecto, pero conviene
# saber que **se queda corto**: se han medido desfases de hasta 206 s. Por eso el
# valor medido tiene prioridad sobre esta constante; usarla a ciegas hacía que el
# bot dijera "ya se puede ver" hasta 26 s antes de que fuera verdad.
SPECTATOR_DELAY = _int("SPECTATOR_DELAY", 180)

# Arena (CHERRY, cola 1750) va con bastante menos retraso: en las mediciones el
# desfase bajaba a 60 s, frente a los ~150 s mínimos de SoloQ.
SPECTATOR_DELAY_ARENA = _int("SPECTATOR_DELAY_ARENA", 90)

# ---------------------------------------------------------------------- #
# DPM.lol (no es la API de Riot: no comparte rate limit con la key)
# ---------------------------------------------------------------------- #

# Peticiones simultáneas a DPM.lol. Antes no había límite y `!historial`
# lanzaba cientos de hilos a la vez, cada uno creando su propio scraper.
DPM_CONCURRENCY = _int("DPM_CONCURRENCY", 8)

# Segundos que se reutiliza un historial ya descargado.
DPM_HISTORY_TTL = _int("DPM_HISTORY_TTL", 300)

# Cuántas partidas se guardan en caché por cuenta. `!historial` solo muestra
# 10, así que guardar las cientos que devuelve dpm.lol es memoria tirada.
DPM_HISTORY_MATCHES = _int("DPM_HISTORY_MATCHES", 20)

# Guardar solo los campos que usa el bot. Cada participante trae unos 90 campos
# (runas, pings, objetos, puntuaciones internas de dpm.lol...) y `!historial`
# solo enseña campeón, K/D/A, posición y resultado. Al quedarnos con los campos
# útiles la caché baja de ~27 MB a ~3 MB con las 130 cuentas actuales.
# Ponlo a 0 si alguna función nueva necesita el participante completo.
DPM_SLIM_HISTORY = _int("DPM_SLIM_HISTORY", 1) == 1

# Segundos que se recuerda un PUUID de DPM.lol.
DPM_PUUID_TTL = _int("DPM_PUUID_TTL", 86400)

# Tope de entradas en las cachés de DPM.lol (evita que crezcan sin freno).
DPM_CACHE_MAX = _int("DPM_CACHE_MAX", 500)

# Timeout de red en segundos.
DPM_TIMEOUT = _float("DPM_TIMEOUT", 20.0)

# Parche del que se sacan los pickrates por línea. El fichero que había en el
# repo era del 15.14 y solo cubría 149 campeones (faltaban Lee Sin, Kai'Sa,
# Wukong...). Con un parche actual dpm.lol devuelve 173.
DPM_PATCH = _str("DPM_PATCH", "16.17")

# ---------------------------------------------------------------------- #
# Precalentamiento del historial
# ---------------------------------------------------------------------- #

# `!historial` tarda unos 20 s en frío porque tiene que descargar las partidas
# de las 130 cuentas. Con esto una tarea de fondo mantiene la caché caliente y
# el comando responde al instante.
HISTORIAL_WARM = _int("HISTORIAL_WARM", 1) == 1

# Cada cuánto se refresca una parte de las cuentas. Se hace por lotes para no
# lanzar 260 peticiones de golpe: en `DPM_HISTORY_TTL / intervalo` vueltas se
# ha pasado por todas, así que ninguna entrada llega a caducar.
HISTORIAL_WARM_INTERVAL = _int("HISTORIAL_WARM_INTERVAL", 60)
RIOT_REQUEST_TIMEOUT = _float("RIOT_REQUEST_TIMEOUT", 15.0)
RIOT_MAX_RETRIES = _int("RIOT_MAX_RETRIES", 4)
LOG_LEVEL = _str("LOG_LEVEL", "INFO")


# ---------------------------------------------------------------------- #
# Filtros de partidas notificables
# ---------------------------------------------------------------------- #

def _int_set(name: str, default: set[int]) -> set[int]:
    raw = os.getenv(name)
    if not raw:
        return default
    return {int(v) for v in raw.split(",") if v.strip().lstrip("-").isdigit()}


def _str_set(name: str, default: set[str]) -> set[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return {v.strip() for v in raw.split(",") if v.strip()}


# Por defecto solo SoloQ / Normal / Flex. Ampliable sin tocar código:
#   TRACKER_MODES=CLASSIC,CHERRY   TRACKER_QUEUES=400,420,430,440,1750
TRACKER_MODES = _str_set("TRACKER_MODES", {"CLASSIC"})
TRACKER_QUEUES = _int_set("TRACKER_QUEUES", {400, 420, 430, 440})


# ---------------------------------------------------------------------- #
# Verificación al arrancar
# ---------------------------------------------------------------------- #

def missing_required() -> list[str]:
    """Variables obligatorias que faltan."""
    falta = []
    if not RIOT_API_KEY:
        falta.append("RIOT_API_KEY")
    if not DISCORD_TOKEN:
        falta.append("DISCORD_TOKEN")
    return falta


def resumen() -> str:
    """Resumen para el arranque. No muestra ningún valor sensible."""
    return "\n".join([
        f"  RIOT_API_KEY       : {'ok' if RIOT_API_KEY else 'FALTA'}",
        f"  DISCORD_TOKEN      : {'ok' if DISCORD_TOKEN else 'FALTA'}",
        f"  LOL_API_KEY        : {'ok' if LOL_API_KEY else 'FALTA'}",
        f"  TWITCH_OAUTH_TOKEN : {'ok' if TWITCH_OAUTH_TOKEN else 'no configurado (chat-winner desactivado)'}",
        f"  partidas           : cada {CHECK_GAMES_INTERVAL}s · concurrencia {TRACKER_CONCURRENCY}",
        f"  modos aceptados    : {', '.join(sorted(TRACKER_MODES))}",
        f"  colas aceptadas    : {', '.join(str(q) for q in sorted(TRACKER_QUEUES))}",
        f"  nivel de log       : {LOG_LEVEL}",
    ])

"""Prueba del reloj de partida y de la cuenta atrás del espectador.

No copia la lógica: importa `Reloj`, `desde_partida` y `desde_cache` del propio
`utils/game_clock.py`, más los renderizadores que usan `!live` y el embed de
`!match`. Si el módulo cambia, la prueba lo refleja.

Casos que cubre (los que se rompían antes):

* Partida dentro del delay -> cuenta atrás, **no** un tiempo negativo rotulado
  como tiempo de juego (`⏱ -02:14 en partida`).
* Partida pasada del delay -> tiempo transcurrido normal, sin aviso.
* `gameStartTime == 0` (pantalla de carga) -> respaldo a `gameLength` **sin**
  recortar el signo: ese negativo ES la cuenta atrás.
* Arena usa el delay corto.
* Entradas de caché: se prefiere `gameStartTime` de la partida guardada antes de
  extrapolar desde `game_length`.
* Coherencia entre `!live` y el embed: los dos tienen que decir lo mismo.

Uso:
    python scripts/test_game_clock.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from utils.game_clock import (  # noqa: E402
    COLAS_ARENA,
    MODO_ARENA,
    Reloj,
    delay_de,
    desde_cache,
    desde_partida,
    humano,
    mmss,
)

AHORA = 1_700_000_000.0
DELAY = config.SPECTATOR_DELAY

fallos: list[str] = []
comprobaciones = 0


def check(etiqueta: str, obtenido, esperado) -> None:
    global comprobaciones
    comprobaciones += 1
    if obtenido == esperado:
        print(f"   ok   {etiqueta:<52} {obtenido!r}")
    else:
        fallos.append(f"{etiqueta}: esperaba {esperado!r}, salió {obtenido!r}")
        print(f"   FALLO {etiqueta:<52} {obtenido!r} != {esperado!r}")


def check_que(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    global comprobaciones
    comprobaciones += 1
    if condicion:
        print(f"   ok   {etiqueta:<52} {detalle}")
    else:
        fallos.append(f"{etiqueta}: {detalle}")
        print(f"   FALLO {etiqueta:<52} {detalle}")


def partida(segundos_reales: float | None, longitud=None, cola=420, modo="CLASSIC",
            base: float | None = None) -> dict:
    """Respuesta de `spectator-v5` con los campos que mira el reloj.

    `base` permite anclar la partida al reloj real en vez de a `AHORA`, que es
    lo que necesitan las pruebas de `limpiar_cache_partidas_viejas` (esa función
    lee `time.time()` por dentro).
    """
    ancla = AHORA if base is None else base
    inicio = 0 if segundos_reales is None else int((ancla - segundos_reales) * 1000)
    game = {
        "gameId": 123456789,
        "gameStartTime": inicio,
        "gameQueueConfigId": cola,
        "gameMode": modo,
    }
    if longitud is not None:
        game["gameLength"] = longitud
    return game


# ---------------------------------------------------------------------- #
print("=" * 74)
print("PRUEBA DEL RELOJ DE PARTIDA (utils/game_clock.py)")
print("=" * 74)
print(f"   delay normal {DELAY}s · delay Arena {config.SPECTATOR_DELAY_ARENA}s")

# -- formateo ---------------------------------------------------------- #
print()
print("-- formateo " + "-" * 62)
check("mmss(754)", mmss(754), "12:34")
check("mmss(0)", mmss(0), "00:00")
check("mmss(-65, con_signo)", mmss(-65, con_signo=True), "-01:05")
check("mmss(-65, sin signo)", mmss(-65), "01:05")
check("humano(40)", humano(40), "40 s")
check("humano(61) redondea arriba", humano(61), "2 min")
check("humano(180)", humano(180), "3 min")
check("humano(-30) no negativo", humano(-30), "0 s")

# -- dentro del delay -------------------------------------------------- #
print()
print("-- partida recién detectada (dentro del delay) " + "-" * 27)
# 46 s de juego real: el espectador va DELAY-46 s por detrás.
r = desde_partida(partida(46), AHORA)
check("transcurrido", r.transcurrido, 46)
check("fuente", r.fuente, "inicio")
check("visible (negativo a propósito)", r.visible, 46 - DELAY)
check("espectable", r.espectable, False)
check("falta_para_espectar", r.falta_para_espectar, DELAY - 46)
check_que(
    "texto_corto NO dice 'en partida'",
    "en partida" not in r.texto_corto(),
    r.texto_corto(),
)
check_que(
    "texto_corto lleva cuenta atrás",
    "se podrá ver en" in r.texto_corto() and "-" in r.texto_corto(),
    r.texto_corto(),
)
check_que("aviso_delay presente", r.aviso_delay() is not None, (r.aviso_delay() or "")[:60])
check_que(
    "aviso_delay dice 'Comienza dentro de'",
    "Comienza dentro de" in (r.aviso_delay() or ""),
    (r.aviso_delay() or "")[:70],
)
check_que("texto_embed avisa", "espectable en" in r.texto_embed(), r.texto_embed())

# El caso exacto del backlog: recién detectada -> "dentro de 3 min".
r0 = desde_partida(partida(1), AHORA)
check_que(
    "recién empezada -> '3 min'",
    humano(r0.falta_para_espectar) == f"{DELAY // 60} min",
    r0.texto_corto(),
)

# -- justo en la frontera ---------------------------------------------- #
print()
print("-- frontera del delay " + "-" * 52)
check("un segundo antes: espectable", desde_partida(partida(DELAY - 1), AHORA).espectable, False)
check("justo en el delay: espectable", desde_partida(partida(DELAY), AHORA).espectable, True)
check("justo en el delay: visible", desde_partida(partida(DELAY), AHORA).visible, 0)
check(
    "justo en el delay: falta 0",
    desde_partida(partida(DELAY), AHORA).falta_para_espectar,
    0,
)
check_que(
    "un segundo después: sin aviso",
    desde_partida(partida(DELAY + 1), AHORA).aviso_delay() is None,
    "",
)

# -- ya espectable ----------------------------------------------------- #
print()
print("-- partida avanzada (ya espectable) " + "-" * 38)
r = desde_partida(partida(22 * 60 + 34), AHORA)
check("transcurrido", r.transcurrido, 1354)
check("texto_corto", r.texto_corto(), "⏱ 22:34 en partida")
check("texto_embed", r.texto_embed(), "22m 34s")
check("aviso_delay", r.aviso_delay(), None)
check("espectable", r.espectable, True)

# -- pantalla de carga: gameStartTime == 0 ----------------------------- #
print()
print("-- pantalla de carga (gameStartTime == 0) " + "-" * 32)
# `gameLength` negativo: es literalmente la cuenta atrás del espectador.
r = desde_partida(partida(None, longitud=-42), AHORA)
check("fuente", r.fuente, "longitud")
check("visible conserva el signo", r.visible, -42)
check("transcurrido = longitud + delay", r.transcurrido, DELAY - 42)
check("espectable", r.espectable, False)
check("falta_para_espectar", r.falta_para_espectar, 42)
check_que("cuenta atrás en pantalla", "-00:42" in r.texto_corto(), r.texto_corto())

# gameLength positivo pero por debajo del delay: sigue sin ser visible... no:
# gameLength ES el reloj del espectador, así que positivo => ya se puede ver.
r = desde_partida(partida(None, longitud=15), AHORA)
check("longitud positiva -> espectable", r.espectable, True)
check("longitud positiva -> visible", r.visible, 15)
check("longitud -> marcado como aproximado", r.aproximado, True)
check_que("y se ve el ~ en pantalla", r.texto_corto().startswith("⏱ ~"), r.texto_corto())
check_que("y también en el embed", r.texto_embed().startswith("~"), r.texto_embed())
check("desde gameStartTime NO es aproximado", desde_partida(partida(600), AHORA).aproximado, False)

# Sin ningún dato de tiempo.
r = desde_partida(partida(None), AHORA)
check("sin datos: fuente", r.fuente, "desconocido")
check("sin datos: fiable", r.fiable, False)
check("sin datos: texto_corto", r.texto_corto(), "⏱ tiempo desconocido")
check("sin datos: texto_embed", r.texto_embed(), "Desconocido")
check("sin datos: aviso", r.aviso_delay(), None)
check("None: no revienta", desde_partida(None, AHORA).fuente, "desconocido")
check("no-dict: no revienta", desde_partida("nope", AHORA).fuente, "desconocido")

# -- Arena ------------------------------------------------------------- #
print()
print("-- Arena (delay corto) " + "-" * 51)
arena = config.SPECTATOR_DELAY_ARENA
check_que("hay más de una cola de Arena mapeada", len(COLAS_ARENA) >= 1, str(sorted(COLAS_ARENA)))
for cola in sorted(COLAS_ARENA):
    check(f"delay_de(cola={cola})", delay_de(None, cola), arena)
check(f"delay_de(modo={MODO_ARENA})", delay_de(MODO_ARENA, None), arena)
check("delay_de(cola=420) normal", delay_de("CLASSIC", 420), DELAY)
check("delay_de() sin datos", delay_de(), DELAY)

cola_arena = sorted(COLAS_ARENA)[0]
r = desde_partida(partida(100, cola=cola_arena, modo=MODO_ARENA), AHORA)
check("Arena a los 100s: delay", r.delay, arena)
check("Arena a los 100s: espectable", r.espectable, arena <= 100)
r_clasica = desde_partida(partida(100), AHORA)
check_que(
    "Arena se ve antes que la clásica",
    r.falta_para_espectar < r_clasica.falta_para_espectar,
    f"arena {r.falta_para_espectar}s vs clásica {r_clasica.falta_para_espectar}s",
)

# -- delay medido, no estimado ----------------------------------------- #
print()
print("-- delay MEDIDO (los dos campos presentes) " + "-" * 31)
# Este es el caso real: `spectator-v5` manda `gameStartTime` y `gameLength` a la
# vez, así que el delay no hay que suponerlo. La sonda midió 192 s en SoloQ, por
# encima de SPECTATOR_DELAY=180: si se restara la constante, el bot diría «ya se
# puede ver» 12 s antes de que fuera verdad.
g = partida(200, longitud=8)  # 200 s de juego, el espectador va por 8 s
r = desde_partida(g, AHORA)
check("fuente", r.fuente, "medido")
check("transcurrido (de gameStartTime)", r.transcurrido, 200)
check("visible (de gameLength, sin restar nada)", r.visible, 8)
check("delay medido", r.delay, 192)
check("no marcado como aproximado", r.aproximado, False)
check_que("y se muestra el tiempo real", r.texto_corto(), "⏱ 03:20 en partida")

# El caso peligroso: 185 s de juego con el espectador todavía en negativo.
# Restando la constante (180) saldría «espectable»; midiendo, no.
r = desde_partida(partida(185, longitud=-7), AHORA)
check("con delay real 192s: NO espectable", r.espectable, False)
check("falta lo que dice gameLength", r.falta_para_espectar, 7)
check(
    "restando la constante habría dicho espectable",
    185 - config.SPECTATOR_DELAY >= 0,
    True,
)

# Un delay medido absurdo (dato viejo) se descarta y se vuelve a la constante.
r = desde_partida(partida(3600, longitud=100), AHORA)
check("delay incoherente -> se estima", r.fuente, "inicio")
check("delay incoherente -> usa la constante", r.delay, DELAY)

# -- entradas de caché ------------------------------------------------- #
print()
print("-- caché de partidas activas " + "-" * 45)
# Caso normal: la entrada se guardó hace 120 s con un `game_length` de entonces.
# `gameStartTime` no envejece, pero `game_length` sí: hay que adelantarlo 120 s.
entrada = {
    "active_game": partida(600),
    "timestamp": AHORA - 120,
    "game_length": (600 - 120) - 170,  # el espectador iba 170 s por detrás
}
r = desde_cache(entrada, AHORA)
check("caché: fuente", r.fuente, "medido")
check("caché: transcurrido exacto", r.transcurrido, 600)
check("caché: game_length adelantado 120s", r.visible, 600 - 170)
check("caché: delay medido, no supuesto", r.delay, 170)
check_que(
    "no envejece el gameStartTime",
    r.transcurrido == 600,
    f"120s en caché y sigue diciendo {r.transcurrido}s",
)

# Entrada con `game_length` a None (el tracker no lo pudo leer): se cae al de la
# partida guardada y, si tampoco, a la constante.
entrada_sin_gl = {"active_game": partida(600), "timestamp": AHORA, "game_length": None}
r = desde_cache(entrada_sin_gl, AHORA)
check("caché sin game_length: fuente", r.fuente, "inicio")
check("caché sin game_length: usa la constante", r.delay, DELAY)
entrada_gl_en_partida = {
    "active_game": partida(600, longitud=600 - 170),
    "timestamp": AHORA,
    "game_length": None,
}
check(
    "caché: game_length de la partida como respaldo",
    desde_cache(entrada_gl_en_partida, AHORA).delay,
    170,
)

# Entrada guardada hace rato, sin `gameStartTime`: hay que extrapolar.
entrada = {
    "active_game": partida(None),
    "timestamp": AHORA - 300,
    "game_length": -60,
}
r = desde_cache(entrada, AHORA)
check("caché sin inicio: fuente", r.fuente, "longitud")
check("caché sin inicio: visible", r.visible, -60 + 300)
check("caché sin inicio: transcurrido", r.transcurrido, 240 + DELAY)

# Entrada recién guardada en pantalla de carga: sigue en cuenta atrás.
entrada = {
    "active_game": partida(None),
    "timestamp": AHORA - 10,
    "game_length": -100,
}
r = desde_cache(entrada, AHORA)
check("caché recién guardada: visible", r.visible, -90)
check("caché recién guardada: espectable", r.espectable, False)
check("caché recién guardada: falta", r.falta_para_espectar, 90)

# Arena por caché, sin `gameStartTime`: el delay tiene que seguir siendo el corto.
entrada = {
    "active_game": partida(None, cola=cola_arena, modo=MODO_ARENA),
    "timestamp": AHORA,
    "game_length": -30,
}
check("caché de Arena: delay corto", desde_cache(entrada, AHORA).delay, arena)

# Basura.
check("caché None", desde_cache(None, AHORA).fuente, "desconocido")
check("caché vacía", desde_cache({}, AHORA).fuente, "desconocido")
check(
    "caché sin timestamp",
    desde_cache({"active_game": partida(None), "game_length": -30}, AHORA).fuente,
    "desconocido",
)

# -- coherencia entre call sites --------------------------------------- #
print()
print("-- coherencia !live / embed " + "-" * 46)
for segundos in (5, 60, DELAY - 1, DELAY, DELAY + 1, 1800):
    g = partida(segundos)
    por_partida = desde_partida(g, AHORA)
    por_cache = desde_cache(
        {"active_game": g, "timestamp": AHORA, "game_length": segundos - DELAY}, AHORA
    )
    check_que(
        f"a los {segundos}s coinciden partida y caché",
        (por_partida.transcurrido, por_partida.espectable)
        == (por_cache.transcurrido, por_cache.espectable),
        f"{por_partida.texto_corto()}",
    )

# -- limpieza de caché usa el mismo reloj ------------------------------ #
print()
print("-- expiración de caché " + "-" * 51)
from utils.cache_utils import MAX_CACHE_AGE, limpiar_cache_partidas_viejas  # noqa: E402
from tracking.soloq.active_game_cache import (  # noqa: E402
    ACTIVE_GAME_CACHE,
    ACTIVE_GAME_CACHE_BY_NAME,
    set_active_game,
)

ACTIVE_GAME_CACHE.clear()
ACTIVE_GAME_CACHE_BY_NAME.clear()
# `limpiar_cache_partidas_viejas` mira `time.time()` por dentro, así que estas
# partidas se anclan al reloj real y no a `AHORA`.
real = time.time()
set_active_game("puuid-viva", partida(600, base=real), "jugador vivo")
set_active_game("puuid-vieja", partida(MAX_CACHE_AGE + 600, base=real), "jugador viejo")
borradas = limpiar_cache_partidas_viejas()
check("partidas caducadas borradas", borradas, 1)
check("la que sigue viva se queda", "puuid-viva" in ACTIVE_GAME_CACHE, True)
check("la vieja se va", "puuid-vieja" in ACTIVE_GAME_CACHE, False)
check_que(
    "el índice por nombre también se limpia",
    "jugador viejo" not in ACTIVE_GAME_CACHE_BY_NAME,
    f"quedan {sorted(ACTIVE_GAME_CACHE_BY_NAME)}",
)

# Una partida justo en el límite no se borra.
ACTIVE_GAME_CACHE.clear()
ACTIVE_GAME_CACHE_BY_NAME.clear()
set_active_game("puuid-limite", partida(MAX_CACHE_AGE - 30, base=time.time()), "limite")
check("en el límite no se borra", limpiar_cache_partidas_viejas(), 0)
ACTIVE_GAME_CACHE.clear()
ACTIVE_GAME_CACHE_BY_NAME.clear()

# -- troceado de !live ------------------------------------------------- #
print()
print("-- troceado del mensaje de !live " + "-" * 41)
from core.live_command import MAX_DURACION, _partir  # noqa: E402

texto = "\n".join(
    f"👤 G2 Jugador{i} — cuenta{i}#EUW | Syndra (MID) | ⏱ 12:34 en partida"
    for i in range(60)
)
trozos = _partir(texto)
check_que(
    "todos los trozos dentro del límite",
    all(len(t) <= 1900 for t in trozos),
    f"{len(texto)} car -> {len(trozos)} trozos (máx {max(len(t) for t in trozos)})",
)
check("ninguna línea perdida", sum(t.count("👤") for t in trozos), 60)
check("texto corto = un solo trozo", len(_partir("una línea")), 1)
check("MAX_DURACION de !live", MAX_DURACION, 90 * 60)

# El filtro de partidas terminadas: por encima de MAX_DURACION se descarta.
check_que(
    "una partida de 2h se descartaría",
    desde_partida(partida(2 * 3600), AHORA).transcurrido > MAX_DURACION,
    "",
)

# -- !live de verdad, con la caché rellenada a mano --------------------- #
print()
print("-- !live sobre cuentas reales " + "-" * 44)
from core.live_command import construir_mensaje  # noqa: E402
from tracking.soloq.accounts_io import load_tracked_accounts  # noqa: E402

check_que(
    "sin nada en caché lo dice claramente",
    "No hay jugadores en partida" in construir_mensaje(AHORA),
    "",
)

# Se cogen cuentas trackeadas reales para que `construir_mensaje` las resuelva.
#
# Una cuenta **por jugador distinto**: la comprobación de más abajo ("la partida
# terminada NO sale") busca el nombre del jugador en el mensaje, así que si los
# tres salieran del mismo jugador —y ahora Vladi tiene 5 cuentas— ese nombre
# aparecería igual por su otra partida y el fallo sería del fixture, no del bot.
_por_jugador: dict[str, tuple] = {}
for _p in load_tracked_accounts():
    for _a in _p.accounts:
        if _a.puuid and not getattr(_a, "stale", False):
            _por_jugador.setdefault(_p.name, (_p, _a))
            break
cuentas = list(_por_jugador.values())
check_que(
    "hay cuentas trackeadas con PUUID de jugadores distintos",
    len(cuentas) >= 3,
    f"{len(cuentas)} jugadores",
)


def partida_falsa(puuids: list[str], segundos: float, cola=420, modo="CLASSIC") -> dict:
    """Partida de 10 jugadores con `puuids` colocados en el equipo azul.

    Los campeones son ids reales para que `assign_roles` (que lee los pickrates
    del disco) tenga algo con lo que trabajar.
    """
    campeones_azul = [266, 64, 103, 22, 412]   # Aatrox, Lee Sin, Ahri, Ashe, Thresh
    campeones_rojo = [86, 245, 238, 236, 111]  # Garen, Ekko, Zed, Lucian, Nautilus
    g = partida(segundos, cola=cola, modo=modo)
    g["gameId"] = 900000 + int(segundos)
    g["participants"] = []
    for i, champ in enumerate(campeones_azul):
        g["participants"].append({
            "puuid": puuids[i] if i < len(puuids) else f"relleno-azul-{i}",
            "championId": champ,
            "teamId": 100,
            "spell1Id": 4,
            "spell2Id": 11 if champ == 64 else 14,
            "riotId": f"Azul{i}#EUW",
        })
    for i, champ in enumerate(campeones_rojo):
        g["participants"].append({
            "puuid": f"relleno-rojo-{i}",
            "championId": champ,
            "teamId": 200,
            "spell1Id": 4,
            "spell2Id": 11 if champ == 245 else 14,
            "riotId": f"Rojo{i}#EUW",
        })
    return g


# Tres partidas: una dentro del delay, una ya visible, y una ya terminada.
jugador_nuevo, cuenta_nueva = cuentas[0]
jugador_medio, cuenta_media = cuentas[1]
jugador_viejo, cuenta_vieja = cuentas[2]

ACTIVE_GAME_CACHE.clear()
ACTIVE_GAME_CACHE_BY_NAME.clear()
for (jug, cta), segundos in (
    ((jugador_nuevo, cuenta_nueva), 30),
    ((jugador_medio, cuenta_media), 900),
    ((jugador_viejo, cuenta_vieja), MAX_DURACION + 600),
):
    g = partida_falsa([cta.puuid], segundos)
    ACTIVE_GAME_CACHE[cta.puuid] = {
        "active_game": g,
        "timestamp": AHORA,
        "game_length": segundos - DELAY,
    }

mensaje = construir_mensaje(AHORA)
print()
for linea in mensaje.split("\n"):
    if linea.strip():
        print(f"      | {linea}")
print()

check_que(
    "la partida dentro del delay sale con cuenta atrás",
    "se podrá ver en" in mensaje,
    "",
)
check_que(
    "la partida avanzada sale como '15:00 en partida'",
    "15:00 en partida" in mensaje,
    "",
)
check_que(
    "la partida terminada NO sale",
    jugador_viejo.name not in mensaje,
    f"jugador descartado: {jugador_viejo.name}",
)
check_que(
    "ningún tiempo negativo rotulado 'en partida'",
    "-" not in mensaje.split("en partida")[0].split("| ⏱")[-1],
    "",
)
check_que("hay resumen de partidas en espera", "todavía dentro del delay" in mensaje, "")
check_que(
    "la cuenta atrás va primero (orden por tiempo)",
    mensaje.index("se podrá ver en") < mensaje.index("15:00 en partida"),
    "",
)
# El rol tiene que ser el de la partida (deducido del campeón), no el del equipo.
check_que(
    "el rol sale normalizado y corto",
    any(f"({r})" in mensaje for r in ("TOP", "JGL", "MID", "BOT", "SUP")),
    [t for t in mensaje.split() if t.startswith("(") and t.endswith(")")][:4],
)
check_que(
    "no aparecen los roles largos de assign_roles",
    not any(f"({r})" in mensaje for r in ("MIDDLE", "BOTTOM", "SUPPORT", "JUNGLE")),
    "",
)

# Dos cuentas del mismo jugador en la misma partida: solo una línea por cuenta,
# pero los roles se resuelven una sola vez por partida.
ACTIVE_GAME_CACHE.clear()
ACTIVE_GAME_CACHE_BY_NAME.clear()
compartida = partida_falsa([c.puuid for _p, c in cuentas[:3]], 600)
for _jug, cta in cuentas[:3]:
    ACTIVE_GAME_CACHE[cta.puuid] = {
        "active_game": compartida,
        "timestamp": AHORA,
        "game_length": 600 - DELAY,
    }
mensaje = construir_mensaje(AHORA)
check("tres cuentas en la misma partida = 3 líneas", mensaje.count("👤"), 3)
check_que("todas dicen 10:00", mensaje.count("10:00 en partida") == 3, "")

# Una entrada corrupta no debe tumbar el comando.
ACTIVE_GAME_CACHE.clear()
ACTIVE_GAME_CACHE_BY_NAME.clear()
ACTIVE_GAME_CACHE["puuid-basura"] = {"timestamp": AHORA}
ACTIVE_GAME_CACHE[cuentas[0][1].puuid] = {
    "active_game": partida_falsa([cuentas[0][1].puuid], 300),
    "timestamp": AHORA,
    "game_length": 300 - DELAY,
}
mensaje = construir_mensaje(AHORA)
check("entrada corrupta ignorada, la buena sale", mensaje.count("👤"), 1)
ACTIVE_GAME_CACHE.clear()
ACTIVE_GAME_CACHE_BY_NAME.clear()

# -- roles: vocabulario y modos raros ---------------------------------- #
print()
print("-- roles " + "-" * 65)
from models.soloq_match import SoloQParticipant  # noqa: E402
from utils.constants import ROLE_ORDER, normalizar_rol, rol_corto  # noqa: E402
from utils.role_assigner import assign_roles  # noqa: E402

for crudo, esperado in (
    ("Top", "TOP"), ("Jungle", "JUNGLE"), ("Mid", "MIDDLE"), ("Bot", "BOTTOM"),
    ("Support", "SUPPORT"), ("ADC", "BOTTOM"), ("UTILITY", "SUPPORT"),
    ("MIDDLE", "MIDDLE"), (None, "?"), ("", "?"),
):
    check(f"normalizar_rol({crudo!r})", normalizar_rol(crudo), esperado)
check("rol_corto('Support')", rol_corto("Support"), "SUP")
check("rol_corto('Jungle')", rol_corto("Jungle"), "JGL")
check_que(
    "SUPPORT tiene orden propio (no cae al 99)",
    ROLE_ORDER.get("SUPPORT") == ROLE_ORDER.get("UTILITY") == 4,
    f"SUPPORT={ROLE_ORDER.get('SUPPORT')} UTILITY={ROLE_ORDER.get('UTILITY')}",
)


def _part(champ, team, s2=14):
    return SoloQParticipant(
        puuid=f"p{champ}{team}", champion_id=champ, champion_name=None, riot_id={},
        team_id=team, datos_extra={"spell1Id": 4, "spell2Id": s2},
    )


# 5v5: Aatrox / Lee Sin (Smite) / Ahri / Ashe / Thresh -> las cinco líneas.
equipo = [_part(266, 100), _part(64, 100, 11), _part(103, 100),
          _part(22, 100), _part(412, 100)]
rivales = [_part(86, 200), _part(245, 200, 11), _part(238, 200),
           _part(236, 200), _part(111, 200)]
res = assign_roles(equipo + rivales)
check("5v5: cada equipo cubre las 5 líneas", len({p.role for p in res}), 5)
check("Lee Sin con Smite -> JUNGLE", equipo[1].role, "JUNGLE")
check("Ashe -> BOTTOM", equipo[3].role, "BOTTOM")
check("Thresh -> SUPPORT", equipo[4].role, "SUPPORT")

# Arena: 18 jugadores, todos con teamId 100. No hay líneas que repartir.
arena_parts = [_part(76 + i, 100) for i in range(18)]
res = assign_roles(arena_parts)
check("Arena: nadie recibe rol inventado", {p.role for p in res}, {None})
check("Arena: no se pierde a nadie", len(res), 18)

# -- reloj sin ahora explícito ----------------------------------------- #
print()
print("-- reloj en tiempo real " + "-" * 50)
g = {"gameStartTime": int((time.time() - 300) * 1000), "gameQueueConfigId": 420}
r = desde_partida(g)
check_que(
    "usa time.time() si no se le pasa `ahora`",
    298 <= r.transcurrido <= 302,
    f"{r.transcurrido}s",
)

# -- resumen ----------------------------------------------------------- #
print()
print("=" * 74)
print("RESUMEN")
print("=" * 74)
print(f"   comprobaciones : {comprobaciones}")
print(f"   fallos         : {len(fallos)}")
for f in fallos:
    print(f"      - {f}")

if not fallos:
    print()
    print("   Ejemplos de lo que verá el usuario:")
    for segundos, etiqueta in ((8, "recién detectada"), (120, "a mitad del delay"),
                               (DELAY + 30, "ya espectable"), (1800, "partida larga")):
        rr = desde_partida(partida(segundos), AHORA)
        print(f"      {etiqueta:<20} !live: {rr.texto_corto()}")
        print(f"      {'':<20} embed: {rr.texto_embed()}")

raise SystemExit(1 if fallos else 0)

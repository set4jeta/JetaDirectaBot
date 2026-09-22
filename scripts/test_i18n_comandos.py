"""Comprueba que `/team`, `/info`, `/historial` y `/health` hablan los dos idiomas.

Por qué existe
--------------
Estos cuatro comandos eran los últimos que quedaban en español a pelo. Al
traducirlos hay cuatro formas de romperlos y ninguna se nota hasta que un
usuario lo ve:

1. **Una clave mal escrita.** `t()` no lanza nunca: devuelve la clave. Así que
   un typo no da error, da un mensaje que dice literalmente `team.titulo`.
2. **Una clave sin inglés.** Cae al español y el servidor en inglés recibe
   media respuesta en castellano sin que nada avise.
3. **Un `{placeholder}` que está en el español pero no en el inglés.** `t()`
   captura el `KeyError` del `format` y devuelve la **plantilla sin rellenar**,
   así que el usuario lee `{jugador}` en vez del nick. Solo queda un warning en
   el log.
4. **Un cuerpo de comando que sigue mandando una cadena literal.** Compila, pasa
   las tres pruebas de arriba y sale en español igual.

Esta prueba cubre las cuatro: audita el catálogo entero y luego **ejecuta los
cuerpos reales** de los comandos con un `Respuesta` de pega que apunta lo que se
manda en vez de hablar con Discord. Sin red: los dos comandos que la usarían
(`/team` y `/historial`) reciben monkeypatch de su capa de datos.

    python scripts/test_i18n_comandos.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re  # noqa: E402

from utils.i18n import _CATALOGO, IDIOMAS, t  # noqa: E402

fallos: list[str] = []


def check(etiqueta: str, ok: bool, detalle: str = "") -> None:
    marca = "OK  " if ok else "FALLO"
    print(f"  [{marca}] {etiqueta}" + (f" — {detalle}" if detalle else ""))
    if not ok:
        fallos.append(etiqueta)


# --------------------------------------------------------------------- #
# 1. Auditoría del catálogo
# --------------------------------------------------------------------- #

print("\n1) Catálogo completo")

sin_ingles = [k for k, v in _CATALOGO.items() if not (v.get("en") or "").strip()]
check(f"las {len(_CATALOGO)} claves tienen inglés no vacío",
      not sin_ingles, ", ".join(sin_ingles) or "todas")

sin_espanol = [k for k, v in _CATALOGO.items() if not (v.get("es") or "").strip()]
check("todas tienen español no vacío", not sin_espanol,
      ", ".join(sin_espanol) or "todas")

# Una traducción igual a su clave es indistinguible de una clave que no existe.
iguales = [
    f"{k}[{idi}]"
    for k, v in _CATALOGO.items()
    for idi in IDIOMAS
    if v.get(idi) == k
]
check("ninguna traducción es igual a su clave", not iguales,
      ", ".join(iguales) or "ok")

_PLACEHOLDER = re.compile(r"\{(\w+)")

descuadres: list[str] = []
for clave, formas in _CATALOGO.items():
    huecos_es = set(_PLACEHOLDER.findall(formas.get("es", "")))
    for idi in IDIOMAS:
        if idi == "es":
            continue
        texto = formas.get(idi)
        if not texto:
            continue
        faltan = huecos_es - set(_PLACEHOLDER.findall(texto))
        if faltan:
            descuadres.append(f"{clave}[{idi}] sin {sorted(faltan)}")
check("los {placeholder} del español están en el inglés", not descuadres,
      "; ".join(descuadres) or "cuadran")

# Y al revés: un hueco que solo esté en inglés también deja la plantilla cruda.
extras: list[str] = []
for clave, formas in _CATALOGO.items():
    huecos_es = set(_PLACEHOLDER.findall(formas.get("es", "")))
    for idi in IDIOMAS:
        if idi == "es":
            continue
        texto = formas.get(idi)
        if not texto:
            continue
        sobran = set(_PLACEHOLDER.findall(texto)) - huecos_es
        if sobran:
            extras.append(f"{clave}[{idi}] añade {sorted(sobran)}")
check("el inglés no inventa {placeholder} nuevos", not extras,
      "; ".join(extras) or "ninguno")

check("una clave inexistente se devuelve tal cual",
      t("no.existe.esta.clave", "en") == "no.existe.esta.clave")


# --------------------------------------------------------------------- #
# 2. Respuesta de pega
# --------------------------------------------------------------------- #

class RespuestaFalsa:
    """Stand-in de `core.responder.Respuesta` que apunta en vez de enviar.

    Solo implementa lo que usan los cuerpos convertidos. `guild_id` es el
    gancho: `tr()` resuelve el idioma a partir de él, así que se sobreescribe
    `utils.i18n.idioma_de` en la prueba para no tocar `idiomas_config.json`.
    """

    def __init__(self, guild_id: int = 1):
        self.guild_id = guild_id
        self.guild = None
        self.canal_id = 1
        self.enviados: list[str] = []
        self.embeds: list[object] = []

    def es_admin(self) -> bool:
        return True

    async def esperando(self, texto: str = "") -> None:
        if texto:
            self.enviados.append(texto)

    async def send(self, content=None, **kwargs):
        if content:
            self.enviados.append(str(content))
        embed = kwargs.get("embed")
        if embed is not None:
            self.embeds.append(embed)
            self.enviados.append(_texto_de_embed(embed))
        # Los ficheros adjuntos se cierran: si no, Windows deja el .webp
        # abierto y la siguiente pasada del bucle no puede leerlo.
        for f in list(kwargs.get("files") or []) + ([kwargs["file"]] if kwargs.get("file") else []):
            try:
                f.close()
            except Exception:
                pass
        return None

    async def error(self, texto: str):
        self.enviados.append(texto)
        return None

    async def enviar_partido(self, texto: str, limite: int = 1900) -> None:
        self.enviados.append(texto)

    async def enviar_bloque(self, texto: str, lenguaje: str = "markdown") -> None:
        self.enviados.append(texto)

    def todo(self) -> str:
        return "\n".join(self.enviados)


def _texto_de_embed(embed) -> str:
    partes = [str(embed.title or ""), str(embed.description or "")]
    for campo in embed.fields:
        partes.append(str(campo.name or ""))
        partes.append(str(campo.value or ""))
    pie = getattr(embed, "footer", None)
    if pie is not None and getattr(pie, "text", None):
        partes.append(str(pie.text))
    return "\n".join(partes)


# Todas las claves del catálogo: si alguna aparece literalmente en la salida,
# es que `t()` no la encontró (o el cuerpo la escribió a mano).
CLAVES = sorted(_CATALOGO)


def claves_crudas(texto: str) -> list[str]:
    return [k for k in CLAVES if k in texto]


# --------------------------------------------------------------------- #
# 3. Datos sintéticos
# --------------------------------------------------------------------- #

class _Cuenta:
    def __init__(self, nombre: str, tag: str = "EUW", puuid: str = "puuid-1"):
        self.puuid = puuid
        self.riot_id = {"game_name": nombre, "tag_line": tag}
        self.platform = "euw1"
        self.stale = False
        self.rank = {"tier": "CHALLENGER", "division": "I", "lp": 900}


class _Jugador:
    def __init__(self, nombre: str, cuentas, equipo: str = "G2", rol: str = "Mid"):
        self.name = nombre
        self.team = equipo
        self.team_name = "G2 Esports"
        self.role = rol
        self.accounts = cuentas
        self.league = "lec"


def jugadores_falsos():
    """Dos jugadores: uno con una cuenta y otro con dos, para el 'mejor de N'."""
    return [
        _Jugador("Caps", [_Cuenta("Caps", "EUW", "puuid-1")]),
        _Jugador(
            "Hans Sama",
            [_Cuenta("HansSama", "EUW", "puuid-2"),
             _Cuenta("HansAlt", "EUW", "puuid-3")],
            rol="ADC",
        ),
    ]


PARTIDA_DPM = {
    "gameCreation": 1_700_000_000_000,
    "gameDuration": 1800,
    "participants": [{
        "puuid": "dpm-1",
        "championName": "Syndra",
        "kills": 7, "deaths": 2, "assists": 9,
        "win": True,
        "teamPosition": "MIDDLE",
    }],
}


# --------------------------------------------------------------------- #
# 4. Los cuatro comandos, en es y en en
# --------------------------------------------------------------------- #

async def probar_team(idioma: str) -> None:
    import core.register_team_commands as mod

    jugadores = jugadores_falsos()
    mod.load_tracked_accounts = lambda: jugadores

    async def _mejor(jugador, semaforo):
        rango = {"tier": "CHALLENGER", "division": "I", "lp": 900}
        return jugador.accounts[0], rango, len(jugador.accounts)

    mod._mejor_cuenta_de = _mejor

    # Con equipo: el camino normal.
    res = RespuestaFalsa()
    await mod._cuerpo_team(res, "g2")
    salida = res.todo()
    check(f"{idioma}/team G2: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")
    check(f"{idioma}/team G2: manda algo", bool(salida.strip()))

    # Sin argumento y equipo inexistente: los dos avisos.
    res = RespuestaFalsa()
    await mod._cuerpo_team(res, "")
    salida = res.todo()
    check(f"{idioma}/team sin argumento: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")

    res = RespuestaFalsa()
    await mod._cuerpo_team(res, "noexiste")
    salida = res.todo()
    check(f"{idioma}/team desconocido: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")

    # Un jugador que revienta y otro sin cuentas: las dos líneas de error.
    async def _mejor_roto(jugador, semaforo):
        if jugador.name == "Caps":
            raise RuntimeError("rango no disponible")
        return None, None, 0

    mod._mejor_cuenta_de = _mejor_roto
    res = RespuestaFalsa()
    await mod._cuerpo_team(res, "g2")
    salida = res.todo()
    check(f"{idioma}/team con fallos: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")


async def probar_info(idioma: str) -> None:
    import core.info_command as mod

    ficha = {
        "nombre": "Caps", "nombre_real": "Rasmus Winther", "edad": 25,
        "equipo": "G2 Esports", "pais": "Denmark",
        "birthdate": "1999-10-17", "contrato_hasta": "2026-11-15",
        "redes_sociales": {"twitter": "https://x.com/G2Caps"},
    }
    cuentas = [{
        "nombre": "Caps#EUW", "region": "EUW", "liga": "Challenger",
        "lp": 900, "victorias": 120, "derrotas": 80,
        "ultima_partida": 1_700_000_000_000,
    }]
    campeones = [{"nombre": "Syndra", "partidas": 20, "victorias": 13,
                  "kda_promedio": 4.2}]
    stats = {"games": 40, "wins": 25, "losses": 15, "timePlayed": 90_000}

    mod.buscar_jugador_o_cuenta = lambda nombre: {
        "jugador": ficha, "cuentas": [dict(c) for c in cuentas],
        "campeones_recientes": campeones, "estadisticas_2_semanas": stats,
    }

    res = RespuestaFalsa()
    await mod._cuerpo_info(res, "Caps")
    salida = res.todo()
    check(f"{idioma}/info ficha: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")
    check(f"{idioma}/info ficha: monta el embed", bool(res.embeds))

    # Una ficha vacía ejercita todos los "Desconocido"/"Sin equipo".
    mod.buscar_jugador_o_cuenta = lambda nombre: {
        "jugador": {}, "cuentas": [], "campeones_recientes": [],
        "estadisticas_2_semanas": {},
    }
    res = RespuestaFalsa()
    await mod._cuerpo_info(res, "Vacio")
    salida = res.todo()
    check(f"{idioma}/info ficha vacía: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")

    # No encontrado y sin argumento.
    mod.buscar_jugador_o_cuenta = lambda nombre: None
    res = RespuestaFalsa()
    await mod._cuerpo_info(res, "NoExiste")
    salida = res.todo()
    check(f"{idioma}/info no encontrado: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")

    res = RespuestaFalsa()
    await mod._cuerpo_info(res, "")
    salida = res.todo()
    check(f"{idioma}/info sin argumento: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")


async def probar_historial(idioma: str) -> None:
    import core.historial_commands as mod

    jugadores = jugadores_falsos()
    mod.load_tracked_accounts = lambda: jugadores

    async def _partidas(jugador, account, cuenta):
        return [{
            "jugador": jugador,
            "participante": PARTIDA_DPM["participants"][0],
            "match": PARTIDA_DPM,
            "cuenta": cuenta,
        }]

    mod.partidas_de_cuenta = _partidas

    # Global.
    res = RespuestaFalsa()
    await mod._cuerpo_historial(res, "")
    salida = res.todo()
    check(f"{idioma}/historial global: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")

    # Individual por nick con dos cuentas: la cabecera "todas sus cuentas".
    res = RespuestaFalsa()
    await mod._cuerpo_historial(res, "Hans Sama")
    salida = res.todo()
    check(f"{idioma}/historial 2 cuentas: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")
    # Y que el sufijo de cuenta de `match_format` viene traducido.
    check(f"{idioma}/historial 2 cuentas: marca la cuenta en cada línea",
          "HansSama#EUW)" in salida, salida[:80])

    # Individual con una sola cuenta: la otra cabecera.
    res = RespuestaFalsa()
    await mod._cuerpo_historial(res, "Caps")
    salida = res.todo()
    check(f"{idioma}/historial 1 cuenta: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")

    # Jugador que no existe.
    res = RespuestaFalsa()
    await mod._cuerpo_historial(res, "NoExiste")
    salida = res.todo()
    check(f"{idioma}/historial no encontrado: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")

    # Sin partidas y sin jugadores registrados.
    async def _vacio(jugador, account, cuenta):
        return []

    mod.partidas_de_cuenta = _vacio
    res = RespuestaFalsa()
    await mod._cuerpo_historial(res, "Caps")
    salida = res.todo()
    check(f"{idioma}/historial sin partidas: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")

    mod.load_tracked_accounts = lambda: []
    res = RespuestaFalsa()
    await mod._cuerpo_historial(res, "")
    salida = res.todo()
    check(f"{idioma}/historial sin jugadores: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")


async def probar_health(idioma: str) -> None:
    import core.health_command as mod
    from core import health as salud

    # Estado sano: nada registrado todavía (todo "sin comprobar").
    res = RespuestaFalsa()
    await mod._cuerpo_health(res)
    salida = res.todo()
    check(f"{idioma}/health limpio: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")
    check(f"{idioma}/health limpio: monta el embed", bool(res.embeds))

    # Con una fuente al día, una con un fallo y una averiada: las tres líneas.
    salud.registrar("riot", True)
    salud.registrar("historial", False, "dpm.lol no respondió")
    for _ in range(3):
        salud.registrar("pickrates", False, "403 de Cloudflare")

    res = RespuestaFalsa()
    await mod._cuerpo_health(res)
    salida = res.todo()
    check(f"{idioma}/health con averías: sin claves crudas",
          not claves_crudas(salida), ", ".join(claves_crudas(salida)) or "limpio")
    check(f"{idioma}/health con averías: sale el aviso",
          "⚠️" in salida)

    # Los campos de un embed no pueden pasar de 1024 ni el título de 256.
    for embed in res.embeds:
        largos = [
            (c.name, len(str(c.value)))
            for c in embed.fields if len(str(c.value or "")) > 1024
        ]
        check(f"{idioma}/health: campos <= 1024", not largos, str(largos))
        check(f"{idioma}/health: título <= 256",
              len(embed.title or "") <= 256, str(len(embed.title or "")))

    salud._estados.clear()


async def main() -> None:
    import utils.i18n as i18n
    import core.health as salud_mod
    import core.info_command as info_mod
    import core.historial_commands as hist_mod
    import core.register_team_commands as team_mod
    import ui.player_info_embed as ficha_mod
    import utils.match_format as fmt_mod
    import utils.rank_utils as rank_mod

    # Se fija el idioma a mano en vez de escribir en `idiomas_config.json`: la
    # prueba no debe tocar la configuración real del bot.
    originales = {
        "i18n": i18n.idioma_de,
        "info": getattr(info_mod, "idioma_de"),
        "hist": getattr(hist_mod, "idioma_de"),
        "team": getattr(team_mod, "idioma_de"),
    }
    guardados = {
        "buscar": info_mod.buscar_jugador_o_cuenta,
        "cargar_hist": hist_mod.load_tracked_accounts,
        "cargar_team": team_mod.load_tracked_accounts,
        "partidas": hist_mod.partidas_de_cuenta,
        "mejor": team_mod._mejor_cuenta_de,
    }

    print("\n2) Los cuatro comandos con un Respuesta de pega")
    for idioma in ("es", "en"):
        print(f"\n  --- idioma {idioma} ---")
        fijo = (lambda gid, _i=idioma: _i)
        i18n.idioma_de = fijo
        info_mod.idioma_de = fijo
        hist_mod.idioma_de = fijo
        team_mod.idioma_de = fijo

        await probar_team(idioma)
        await probar_info(idioma)
        await probar_historial(idioma)
        await probar_health(idioma)

        # Cada idioma parte de los módulos como estaban.
        info_mod.buscar_jugador_o_cuenta = guardados["buscar"]
        hist_mod.load_tracked_accounts = guardados["cargar_hist"]
        team_mod.load_tracked_accounts = guardados["cargar_team"]
        hist_mod.partidas_de_cuenta = guardados["partidas"]
        team_mod._mejor_cuenta_de = guardados["mejor"]

    i18n.idioma_de = originales["i18n"]
    info_mod.idioma_de = originales["info"]
    hist_mod.idioma_de = originales["hist"]
    team_mod.idioma_de = originales["team"]

    # --- Comparación es/en a ojo, igual que en test_i18n_embed ---
    print("\n3) Lo que ve el usuario")
    for idioma in ("es", "en"):
        print(f"\n  --- {idioma} ---")
        print(f"  /team línea:   **Caps** (Caps#EUW) - "
              f"{rank_mod.formatear_rank({'tier': 'Challenger', 'division': 'I', 'lp': 900}, idioma)}"
              f"{t('team.mejor_de', idioma, total=3)}")
        print(f"  /team sin elo: {rank_mod.formatear_rank(None, idioma)}")
        print(f"  /team aviso:   {t('team.aviso_sin_datos', idioma, n=1)}")
        print(f"  /historial:    "
              f"{fmt_mod.formatear_partida(PARTIDA_DPM['participants'][0], PARTIDA_DPM, 'Caps#EUW', idioma)}")
        print(f"  /historial cab: {t('historial.cabecera_jugador_todas', idioma, n=10, jugador='Caps [G2]')}")
        print(f"  /health up:    {t('health.encendido', idioma, tiempo=t('health.uptime_horas', idioma, horas=3, minutos=12))}")
        print(f"  /health fuente: {salud_mod.linea('riot', salud_mod.Estado(ok=True, ultimo_ok=__import__('time').time() - 120), idioma)}")
        print(f"  /info cuenta:  {t('info.cuenta_balance', idioma, victorias=120, derrotas=80, winrate='60%')}")

    # --- El "jugador(es)" del aviso de /team con 1 y con 2 ---
    print("\n4) Concordancia de los recuentos")
    for n in (1, 2):
        for idioma in ("es", "en"):
            texto = t("team.aviso_sin_datos", idioma, n=n)
            check(f"{idioma}: aviso con n={n} lleva el número y no queda crudo",
                  str(n) in texto and "{n}" not in texto, texto)


asyncio.run(main())

print("\n" + "=" * 60)
if fallos:
    print(f"FALLOS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("Todo correcto: /team, /info, /historial y /health funcionan en es y en en.")

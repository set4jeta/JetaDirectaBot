"""El censo se publica desde GitHub y el bot se lo baja. Esto lo vigila.

Por qué existe
--------------
Desde el 01-11-2026 los rosters no se pueden bajar desde Render: Cloudflare
contesta 403 a su IP (ver `apis/transporte_dpm.py`). El refresco pasó a un runner
de GitHub (`.github/workflows/refrescar-rosters.yml` →
`scripts/refrescar_rosters.py`) que publica **solo** el censo compacto en la rama
de estado, y el bot se lo vuelve a bajar cada pocas horas
(`sincronizar_censo_remoto`).

Ese reparto tiene tres formas de romperse en silencio, y las tres se comprueban
aquí sin tocar la red:

1. **Publicar de más.** Si el workflow subiera toda la rama, su copia de
   `egress.json` y `notified_games.json` —una foto de horas antes— pisaría los
   contadores vivos del bot. Por eso existe `guardar(solo=...)`.
2. **Publicar de menos.** Si el bot no volviera a bajarse el censo, se quedaría
   con el del arranque: en el plan gratuito un proceso puede tirarse semanas sin
   reiniciarse.
3. **Insistir en el scraping bloqueado.** La rotación horaria de rosters seguiría
   encadenando 403 cada hora para nada.

Uso:
    python scripts/test_rosters_github.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from core import estado_remoto  # noqa: E402
from tracking.soloq import censo  # noqa: E402

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


class _SesionFalsa:
    """Lo mínimo de `aiohttp.ClientSession` que usan `guardar`/`restaurar`."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _ApiFalsa:
    """Sustituye a `estado_remoto._api` y apunta lo que se le pide."""

    def __init__(self, contenido: str = "", estado_get: int = 404):
        self.llamadas: list[tuple[str, str]] = []
        self.contenido = contenido
        self.estado_get = estado_get

    async def __call__(self, sesion, metodo, ruta, **kwargs):
        self.llamadas.append((metodo, ruta))
        if metodo == "PUT":
            return 201, {"content": {"sha": "nuevo"}}
        if self.estado_get != 200:
            return self.estado_get, None
        import base64

        return 200, {
            "content": base64.b64encode(self.contenido.encode("utf-8")).decode("ascii"),
            "sha": "remoto",
        }

    def rutas(self, metodo: str) -> list[str]:
        return [r.split("/contents/", 1)[-1] for m, r in self.llamadas if m == metodo]


class _Entorno:
    """Deja `estado_remoto` apuntando a un directorio temporal y con token."""

    def __init__(self, tmp: Path):
        self.tmp = tmp

    def __enter__(self):
        self._base = estado_remoto.BASE_DIR
        self._api = estado_remoto._api
        self._asegurar = estado_remoto._asegurar_rama
        self._sesion = estado_remoto.aiohttp.ClientSession
        self._token = estado_remoto.config.GITHUB_TOKEN
        self._repo = estado_remoto.config.GITHUB_REPO

        estado_remoto.BASE_DIR = self.tmp
        estado_remoto.aiohttp.ClientSession = _SesionFalsa
        estado_remoto.config.GITHUB_TOKEN = "token-de-prueba"
        estado_remoto.config.GITHUB_REPO = "alguien/repo"

        async def _asegurar(sesion):
            return True

        estado_remoto._asegurar_rama = _asegurar
        return self

    def __exit__(self, *exc):
        estado_remoto.BASE_DIR = self._base
        estado_remoto._api = self._api
        estado_remoto._asegurar_rama = self._asegurar
        estado_remoto.aiohttp.ClientSession = self._sesion
        estado_remoto.config.GITHUB_TOKEN = self._token
        estado_remoto.config.GITHUB_REPO = self._repo
        return False


def _escribir(ruta: Path, texto: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


# ---------------------------------------------------------------------- #
# 1 · La selección de ficheros
# ---------------------------------------------------------------------- #

def prueba_seleccion() -> None:
    print("\n=== `solo` elige ficheros de ARCHIVOS, y avisa de lo que no está ===")
    ok(estado_remoto._seleccion(None) == estado_remoto.ARCHIVOS,
       "sin `solo` se toca todo el estado")

    solo_censo = estado_remoto._seleccion(estado_remoto.CENSO)
    ok(solo_censo == (estado_remoto.CENSO,),
       "con `solo=CENSO` se toca solo el censo", ", ".join(solo_censo))

    ok(estado_remoto.CENSO in estado_remoto.ARCHIVOS,
       "el censo está en ARCHIVOS (si no, no viajaría nunca)")

    # Un nombre inventado se descarta, pero **no** se traga en silencio.
    ok(estado_remoto._seleccion(("no/existe.json",)) == (),
       "un fichero que no está en ARCHIVOS se ignora")

    # Y el orden manda: aunque se pidan al revés, salen en el orden de ARCHIVOS.
    desordenado = estado_remoto._seleccion(
        (estado_remoto.CENSO, "tracking/soloq/egress.json")
    )
    esperado = tuple(r for r in estado_remoto.ARCHIVOS
                     if r in (estado_remoto.CENSO, "tracking/soloq/egress.json"))
    ok(desordenado == esperado, "se respeta el orden de ARCHIVOS", ", ".join(desordenado))


# ---------------------------------------------------------------------- #
# 2 · Guardar y restaurar con `solo`
# ---------------------------------------------------------------------- #

def prueba_guardar_solo_el_censo() -> None:
    print("\n=== guardar(solo=CENSO) no sube los contadores vivos ===")
    tmp = Path(tempfile.mkdtemp(prefix="estado_solo_"))
    try:
        for relativo in estado_remoto.ARCHIVOS:
            _escribir(tmp / relativo, '{"prueba": 1}')
        api = _ApiFalsa()
        with _Entorno(tmp):
            estado_remoto._api = api
            estado_remoto._ultimo_subido.clear()
            subidos = asyncio.run(
                estado_remoto.guardar(forzar=True, solo=estado_remoto.CENSO)
            )

        ok(subidos == 1, "sube exactamente un fichero", str(subidos))
        ok(api.rutas("PUT") == [estado_remoto.CENSO],
           "el único PUT es el del censo", ", ".join(api.rutas("PUT")))
        ok("tracking/soloq/egress.json" not in api.rutas("PUT"),
           "no se sube egress.json (contador vivo del bot)")
        ok("notified_games.json" not in api.rutas("PUT"),
           "no se sube notified_games.json (registro vivo del bot)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def prueba_restaurar_solo_el_censo() -> None:
    print("\n=== restaurar(solo=CENSO) baja un solo fichero ===")
    tmp = Path(tempfile.mkdtemp(prefix="estado_rest_"))
    try:
        api = _ApiFalsa(contenido='{"escrito_en": "2026-11-01", "jugadores": []}',
                        estado_get=200)
        with _Entorno(tmp):
            estado_remoto._api = api
            estado_remoto._ultimo_subido.clear()
            bajados = asyncio.run(
                estado_remoto.restaurar(solo=estado_remoto.CENSO)
            )

        ok(bajados == 1, "restaura exactamente un fichero", str(bajados))
        ok(api.rutas("GET") == [estado_remoto.CENSO],
           "solo se pide el censo", ", ".join(api.rutas("GET")))
        ok((tmp / estado_remoto.CENSO).exists(), "el censo queda en disco")
        ok(not (tmp / "tracking/soloq/egress.json").exists(),
           "no se toca egress.json")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def prueba_sin_token_no_hace_nada() -> None:
    print("\n=== sin token no se llama a GitHub ===")
    tmp = Path(tempfile.mkdtemp(prefix="estado_token_"))
    try:
        api = _ApiFalsa()
        with _Entorno(tmp):
            estado_remoto._api = api
            estado_remoto.config.GITHUB_TOKEN = None
            subidos = asyncio.run(estado_remoto.guardar(solo=estado_remoto.CENSO))
            bajados = asyncio.run(estado_remoto.restaurar(solo=estado_remoto.CENSO))
        ok(subidos == 0 and bajados == 0, "devuelve 0 y no toca la red")
        ok(not api.llamadas, "no hubo ni una llamada")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------- #
# 3 · El script del workflow
# ---------------------------------------------------------------------- #

_JUGADOR = {
    "name": "Faker",
    "team": "T1",
    "team_name": "T1",
    "league": "lck",
    "role": "Mid",
    "accounts": [{
        "riot_id": {"game_name": "Hide on bush", "tag_line": "KR1"},
        "puuid": "puuid-de-prueba",
        "platform": "KR",
        "stale": False,
    }],
}


def prueba_censo_previo() -> None:
    print("\n=== el censo de la rama se siembra como fichero previo ===")
    import json

    from tracking.soloq import accounts_from_teams

    import refrescar_rosters

    tmp = Path(tempfile.mkdtemp(prefix="censo_previo_"))
    try:
        ruta_censo = tmp / "censo_compacto.json"
        ruta_json = tmp / "accounts_from_teams.json"
        censo_antes, json_antes = censo.RUTA, accounts_from_teams.JSON_PATH
        censo.RUTA = str(ruta_censo)
        accounts_from_teams.JSON_PATH = str(ruta_json)
        try:
            # Sin copia: no se siembra nada y se dice (es un alta completa).
            ok(refrescar_rosters._preparar_censo_previo() == 0,
               "sin censo en la rama no se siembra nada")

            censo.escribir([_JUGADOR])
            sembrados = refrescar_rosters._preparar_censo_previo()
            ok(sembrados == 1, "siembra el jugador del censo", str(sembrados))
            ok(ruta_json.exists(), "se escribe el fichero grande")

            datos = json.loads(ruta_json.read_text(encoding="utf-8"))
            cuentas = (datos[0].get("accounts") or [{}]) if datos else [{}]
            ok(bool(cuentas and cuentas[0].get("puuid")),
               "el PUUID sobrevive a la siembra (si no, se pide a Riot cada día)")
            ok(cuentas[0].get("platform") == "KR",
               "la plataforma también (sin ella no se puede sondear)")

            # Y no pisa un censo grande que ya está bien: la copia es un
            # respaldo, no la fuente (no guarda rank, icono, links…).
            antes = ruta_json.read_text(encoding="utf-8")
            ok(refrescar_rosters._preparar_censo_previo() == 0,
               "con el censo grande ya en disco no se siembra")
            ok(ruta_json.read_text(encoding="utf-8") == antes,
               "y el fichero queda igual")
        finally:
            censo.RUTA = censo_antes
            accounts_from_teams.JSON_PATH = json_antes
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def prueba_codigos() -> None:
    print("\n=== --ligas valida contra el catálogo ===")
    from tracking.soloq.leagues import LIGAS

    import refrescar_rosters

    todas = refrescar_rosters._codigos([])
    ok(todas == list(LIGAS), "sin `--ligas` se refrescan todas", str(len(todas)))

    ok(refrescar_rosters._codigos(["lec", "lck"]) == ["lec", "lck"],
       "se respetan las pedidas")
    ok(refrescar_rosters._codigos(["lec", "lec"]) == ["lec"],
       "no se repite una liga")
    ok(refrescar_rosters._codigos(["no-existe"]) == [],
       "una liga inventada no se cuela")


def prueba_no_insiste_si_esta_bloqueado() -> None:
    print("\n=== con dpm.lol bloqueando, refrescar_ligas no hace peticiones ===")
    from apis import transporte_dpm
    from tracking.soloq import accounts_from_teams

    anterior = transporte_dpm._ultimo_bloqueo
    peticiones: list[str] = []

    def _pedir_falso(url, *args, **kwargs):
        peticiones.append(url)
        return None

    pedir_antes = accounts_from_teams.safe_request
    try:
        transporte_dpm._ultimo_bloqueo = time.time()
        accounts_from_teams.safe_request = _pedir_falso
        ok(transporte_dpm.bloqueado_recientemente(), "el bloqueo reciente se detecta")

        resultado = accounts_from_teams.refrescar_ligas(["lec"])
        ok(resultado is False, "devuelve False sin tocar el fichero")
        ok(not peticiones, "no se hizo ni una petición a dpm.lol", str(len(peticiones)))
    finally:
        transporte_dpm._ultimo_bloqueo = anterior
        accounts_from_teams.safe_request = pedir_antes


# ---------------------------------------------------------------------- #
# 4 · Que el bot esté realmente suscrito a la rama
# ---------------------------------------------------------------------- #

def prueba_tropezón_no_es_muro() -> None:
    print("\n=== un 403 suelto no es un bloqueo ===")
    from apis import transporte_dpm

    bloqueo_antes = transporte_dpm._ultimo_bloqueo
    ok_antes = transporte_dpm._ultimo_ok
    try:
        # Desde Render: 403 detrás de 403, ninguna respuesta buena -> muro.
        transporte_dpm._ultimo_ok = 0.0
        transporte_dpm._ultimo_bloqueo = time.time()
        ok(transporte_dpm.bloqueado_recientemente(),
           "sin ninguna respuesta buena detrás, el 403 es un muro")

        # Desde un runner de GitHub: 403 y después respuestas buenas -> seguir.
        transporte_dpm._ultimo_ok = time.time() + 1
        ok(not transporte_dpm.bloqueado_recientemente(),
           "con una respuesta buena detrás, es un tropezón y hay que seguir")

        # Y caducado el rato, tampoco.
        transporte_dpm._ultimo_ok = 0.0
        transporte_dpm._ultimo_bloqueo = time.time() - transporte_dpm.BLOQUEO_VIGENTE - 1
        ok(not transporte_dpm.bloqueado_recientemente(),
           "pasado BLOQUEO_VIGENTE ya no cuenta")
    finally:
        transporte_dpm._ultimo_bloqueo = bloqueo_antes
        transporte_dpm._ultimo_ok = ok_antes


def prueba_no_repite_si_esta_fresco() -> None:
    print("\n=== con el censo reciente no se repite el scraping ===")
    from argparse import Namespace

    from tracking.soloq import accounts_from_teams

    import refrescar_rosters

    tmp = Path(tempfile.mkdtemp(prefix="censo_fresco_"))
    try:
        ruta = tmp / "censo_compacto.json"
        censo_antes = censo.RUTA
        json_antes = accounts_from_teams.JSON_PATH
        censo.RUTA = str(ruta)
        # También el fichero grande: sin esto la prueba escribiría en el censo
        # de verdad del proyecto (pasó, y hubo que restaurarlo del `.bak`).
        accounts_from_teams.JSON_PATH = str(tmp / "accounts_from_teams.json")
        restaurar_antes = estado_remoto.restaurar
        refrescar_antes = refrescar_rosters._refrescar
        try:
            censo.escribir([_JUGADOR])  # escrito_en = ahora mismo

            async def _restaurar_falsa(solo=None):
                return 0

            def _refrescar_prohibido(codigos):
                raise AssertionError("no debería scrapearse: el censo es reciente")

            estado_remoto.restaurar = _restaurar_falsa
            refrescar_rosters._refrescar = _refrescar_prohibido

            args = Namespace(
                ligas=[], sin_publicar=True, sin_puuid=True, sin_restaurar=False,
                si_mas_de_minutos=5.0, forzar=False,
            )
            ok(asyncio.run(refrescar_rosters._run(args)) == 0,
               "sale con 0 sin scrapear")

            args.forzar = True
            args.si_mas_de_minutos = 0.0
            disparado = []
            refrescar_rosters._refrescar = lambda codigos: (disparado.append(1), (0, 0))[1]
            asyncio.run(refrescar_rosters._run(args))
            ok(bool(disparado), "con --forzar sí se scrapea")
        finally:
            censo.RUTA = censo_antes
            accounts_from_teams.JSON_PATH = json_antes
            estado_remoto.restaurar = restaurar_antes
            refrescar_rosters._refrescar = refrescar_antes
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def prueba_relay() -> None:
    print("\n=== el relay de Cloudflare va primero, y solo si está configurado ===")
    from apis import transporte_dpm as t

    antes = (t.RELAY_URL, t.RELAY_CLAVE, t._pedir_una, t._pedir_por_relay,
             t._ultimo_bloqueo, t._ultimo_ok, t._relay_fallos_seguidos,
             t._relay_en_cuarentena_hasta)
    llamadas: list[str] = []
    try:
        t._ultimo_bloqueo = 0.0
        t._ultimo_ok = 0.0

        def _local(url, timeout, transporte):
            llamadas.append(transporte)
            return t.Respuesta(200, '{"ok": 1}', transporte)

        # 1 · Sin relay configurado se comporta como siempre.
        t.RELAY_URL = ""
        t._pedir_una = _local
        r = t.pedir("https://dpm.lol/v1/pros/X")
        ok(bool(r) and r.transporte == "curl_cffi", "sin relay se usa curl_cffi")
        ok(llamadas == ["curl_cffi"], "y no se intenta nada más", str(llamadas))

        # 2 · Con relay, va primero y no gasta peticiones locales.
        llamadas.clear()
        t.RELAY_URL = "https://relay.ejemplo"
        t._pedir_por_relay = lambda url, timeout: t.Respuesta(200, '{"ok": 1}', "relay")
        r = t.pedir("https://dpm.lol/v1/pros/X")
        ok(bool(r) and r.transporte == "relay", "con relay configurado manda el relay")
        ok(not llamadas, "sin gastar curl_cffi ni cloudscraper", str(llamadas))

        # 3 · Si el relay no sirve, se cae a los locales en vez de rendirse.
        llamadas.clear()
        t._pedir_por_relay = lambda url, timeout: t.Respuesta(403, "no", "relay")
        r = t.pedir("https://dpm.lol/v1/pros/X")
        ok(bool(r) and r.transporte == "curl_cffi",
           "si el relay falla se sigue con curl_cffi")
        ok(llamadas == ["curl_cffi"], "y se intentó de verdad", str(llamadas))

        # 4 · El relay no anota bloqueo: que falle no dice nada de dpm.lol.
        ok(t._ultimo_bloqueo == 0.0,
           "un relay caído no se cuenta como bloqueo de dpm.lol")

        # 5 · Un relay que falla siempre entra en cuarentena y deja de gastar
        #     peticiones. El 01-11-2026 el Worker devolvía el desafío de Cloudflare
        #     en el 100 % de los casos y cada ficha pagaba un viaje para nada:
        #     1 800 fallos en una hora.
        t._relay_fallos_seguidos = 0
        t._relay_en_cuarentena_hasta = 0.0
        for _ in range(t.FALLOS_PARA_CUARENTENA):
            t._anotar_fallo_relay("prueba")
        ok(t.relay_en_cuarentena(),
           "a los %d fallos seguidos el relay va a cuarentena"
           % t.FALLOS_PARA_CUARENTENA)

        llamadas.clear()
        # Se devuelve la función de verdad: la comprobación de cuarentena vive
        # dentro de ella, así que con un doble no se estaría probando nada.
        t._pedir_por_relay = antes[3]
        r = t.pedir("https://dpm.lol/v1/pros/X")
        ok(bool(r) and r.transporte == "curl_cffi",
           "en cuarentena ni se intenta: se va directo a curl_cffi")
        ok(llamadas == ["curl_cffi"], "sin gastar un viaje al relay", str(llamadas))

        t._anotar_relay_bueno()
        ok(not t.relay_en_cuarentena(),
           "un 200 del relay lo devuelve al servicio (no es permanente)")
    finally:
        (t.RELAY_URL, t.RELAY_CLAVE, t._pedir_una, t._pedir_por_relay,
         t._ultimo_bloqueo, t._ultimo_ok, t._relay_fallos_seguidos,
         t._relay_en_cuarentena_hasta) = antes


def prueba_worker_del_relay() -> None:
    print("\n=== el Worker no es un proxy abierto ===")
    ruta = RAIZ / "infra" / "relay-dpm" / "worker.js"
    ok(ruta.exists(), "existe infra/relay-dpm/worker.js")
    if not ruta.exists():
        return
    texto = ruta.read_text(encoding="utf-8")
    ok('"dpm.lol"' in texto, "solo habla con dpm.lol")
    ok("RELAY_KEY" in texto, "exige clave (si no, lo usa cualquiera)")
    ok("PREFIJOS" in texto, "limita las rutas a las del bot")
    ok("x-relay-upstream" in texto, "dice qué contestó dpm.lol, para diagnosticar")

    # La lista blanca tiene que cubrir **todas** las rutas que pide el bot. Si se
    # queda corta, el Worker contesta 400 y el log lo cuenta como si dpm.lol
    # estuviera bloqueando: un fallo propio disfrazado de bloqueo ajeno. Pasó con
    # `/tierlist` y con `/pro/`.
    import re

    m = re.search(r"const PREFIJOS = \[([^\]]+)\]", texto)
    ok(bool(m), "se pueden leer los prefijos permitidos")
    if m:
        permitidos = re.findall(r'"([^"]+)"', m.group(1))
        usadas = set()
        for py in RAIZ.rglob("*.py"):
            if "test_" in py.name or ".workbuddy-ai" in str(py):
                continue
            for hallado in re.findall(r"dpm\.lol(/[A-Za-z0-9_{}$\./-]*)", py.read_text(encoding="utf-8", errors="replace")):
                if hallado != "/":
                    usadas.add(hallado)
        fuera = sorted(
            u for u in usadas
            # `/v1` sin barra es la constante `_BASE`, no una ruta: se compara
            # también sin la barra final para no marcarla como fallo.
            if not any(u.startswith(p) or u == p.rstrip("/") for p in permitidos)
        )
        ok(not fuera, "todas las rutas que usa el bot están permitidas", ", ".join(fuera))


def prueba_tarea_del_bot() -> None:
    print("\n=== el bot vuelve a bajarse el censo cada pocas horas ===")
    from core import background_tasks

    tarea = getattr(background_tasks, "sincronizar_censo_remoto", None)
    ok(tarea is not None, "existe `sincronizar_censo_remoto`")
    if tarea is None:
        return
    ok(tarea in background_tasks.TAREAS_PERIODICAS,
       "está en TAREAS_PERIODICAS (si no, no se para al cerrar)")
    ok(background_tasks.CENSO_SINCRONIZAR_HORAS > 0,
       "el intervalo es positivo",
       f"{background_tasks.CENSO_SINCRONIZAR_HORAS} h")
    # Y baja solo el censo: bajar la rama entera revertiría los contadores.
    codigo = Path(background_tasks.__file__).read_text(encoding="utf-8")
    ok("restaurar(solo=estado_remoto.CENSO)" in codigo,
       "la tarea usa `solo=CENSO`")


def prueba_workflow() -> None:
    print("\n=== el workflow existe y pide permiso de escritura ===")
    ruta = RAIZ / ".github" / "workflows" / "refrescar-rosters.yml"
    ok(ruta.exists(), "existe .github/workflows/refrescar-rosters.yml")
    if not ruta.exists():
        return
    texto = ruta.read_text(encoding="utf-8")
    ok("cron:" in texto, "tiene programación")
    ok("workflow_dispatch" in texto, "se puede lanzar a mano")
    ok("contents: write" in texto, "pide contents: write (sin eso no publica)")
    ok("scripts/refrescar_rosters.py" in texto, "llama al script de refresco")
    ok("RIOT_API_KEY" in texto, "pasa la clave de Riot")

    # El freno de las vueltas del cron tiene que ser menor que el hueco entre
    # vueltas, o el cron no hace nada nunca. Estuvo mal desde el 01-11-2026:
    # cron cada 3 h y freno de 300 minutos, así que el censo siempre tenía ~3 h,
    # todas las vueltas se saltaban y el workflow solo trabajaba con `push`.
    import re

    m = re.search(r"cron:\s*'([^']+)'", texto)
    ok(bool(m), "se puede leer la expresión del cron")
    if m:
        campos = m.group(1).split()
        horas = campos[1] if len(campos) > 1 else "*"
        m2 = re.search(r"--si-mas-de-minutos\s+(\d+)", texto)
        ok(bool(m2), "se puede leer el freno de las vueltas del cron")
        if m2:
            # `*` es cada hora; `*/N`, cada N horas. Cualquier otra forma
            # (una lista de horas, por ejemplo) se deja pasar: no hay hueco fijo
            # que comparar y el test no debe inventárselo.
            if horas == "*":
                cada = 1
            elif horas.startswith("*/"):
                cada = int(horas[2:])
            else:
                cada = 0
            if cada:
                freno = int(m2.group(1))
                ok(
                    freno < cada * 60,
                    "el freno (%d min) es menor que el hueco entre vueltas (%d min): "
                    "si no, el cron nunca scrapea" % (freno, cada * 60),
                    f"cron {m.group(1)} vs {freno} min",
                )


def main() -> int:
    prueba_seleccion()
    prueba_guardar_solo_el_censo()
    prueba_restaurar_solo_el_censo()
    prueba_sin_token_no_hace_nada()
    prueba_censo_previo()
    prueba_codigos()
    prueba_no_insiste_si_esta_bloqueado()
    prueba_tropezón_no_es_muro()
    prueba_no_repite_si_esta_fresco()
    prueba_relay()
    prueba_worker_del_relay()
    prueba_tarea_del_bot()
    prueba_workflow()

    print(f"\nfallos: {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())

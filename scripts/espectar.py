"""Abre en el cliente de League of Legends la partida en vivo de un pro.

Qué hace esto y por qué existe
------------------------------
El bot manda un `.bat` con cada aviso, pero un `.bat` no se puede depurar: si
falla, se cierra. Este script hace lo mismo desde Python, que sí se puede
ejecutar a mano, con diagnóstico y con mensajes de error de verdad.

Se usa así:

    python scripts/espectar.py --diagnostico
    python scripts/espectar.py --pro Caps
    python scripts/espectar.py --pro Caps --esperar
    python scripts/espectar.py --partida 5651554245 --clave u1j8... --region NA1
    python scripts/espectar.py --bat --pro Caps

Cómo funciona el espectador (lo que costó averiguarlo)
------------------------------------------------------
1. El bot pregunta a `spectator-v5` si la cuenta está en partida. La respuesta
   trae `gameId`, `platformId` y **`observers.encryptionKey`**.
2. Esa clave es de **32 caracteres alfanuméricos**. Hay otra en los metadatos
   (`decodedEncryptionKey`) que acaba en `=` y **no sirve**: con ella el cliente
   no descifra el chunk 1 y se queda pidiéndolo en bucle, sin decir nada.
3. Se le pide **al cliente** que abra el juego, con el lanzador de su función
   Watch:

       POST /lol-gameflow/v1/watch/launch
       ["spectator <host>:8080 <clave> <gameId> <platform>"]

   El cuerpo es un **vector de argumentos**, no un objeto: con `{}` contesta
   «Couldn't assign value to 'args' of type vector». Con el array devuelve 204 y
   el cliente arranca el juego él mismo, con sus propios argumentos
   (`-Region=…`, `-PlatformID=…`, `-Locale=…`).

4. La partida no se puede ver hasta que pasa el retardo del espectador (~3 min).
   Antes de eso el cliente se abre y se queda sin imagen, que parece un fallo.

Vanguard
--------
El juego **solo lo puede abrir el cliente**. Lanzar `League of Legends.exe` a
mano contesta **acceso denegado (error 5)**, y no es la ruta ni los permisos:
medido el 04-11-2026 con el sandbox desactivado y las ACL normales,
`LeagueCrashHandler64.exe` —en la misma carpeta— también da 5, mientras que un
`notepad.exe` copiado a esa carpeta arranca sin problema. Es el binario.

Por eso este script **no intenta lanzarlo directamente**: si el cliente no está
abierto, lo dice y se acaba. Vanguard no se toca nunca.

Y ojo con el endpoint «de espectar»: `POST /lol-spectator/v1/spectate/launch`
**no vale entre plataformas**. Por dentro llama a
`/lol-gameflow/v2/spectate/launch`, que resuelve la partida contra el shard del
cliente: con un cliente `LA2` y una partida de `NA1` contesta `404 NOT_FOUND`, y
con `puuid`+`spectatorKey`, `500`. El de Watch no tiene ese problema porque
recibe los argumentos del juego ya montados.
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import config  # noqa: E402  (carga el .env)
from utils.game_clock import desde_partida, mmss  # noqa: E402
from utils.spectate_bat import (  # noqa: E402
    fuente_del_cliente,
    generar_bat_spectate,
    ruta_del_cliente,
    servidor_de,
)

ANCHO = 74


def _titulo(texto: str) -> None:
    print()
    print(texto)
    print("-" * min(ANCHO, max(20, len(texto))))


def _si_no(valor: bool | None, si: str = "sí", no: str = "no") -> str:
    if valor is None:
        return "no se pudo comprobar"
    return si if valor else no


# --------------------------------------------------------------------------- #
#  Comprobaciones del PC
# --------------------------------------------------------------------------- #


def _tasklist(filtro: str) -> str:
    """La salida de `tasklist`, decodificada de verdad.

    En un Windows en español `tasklist` **no** escribe UTF-8: manda la salida en
    la página de códigos de la consola (cp850 aquí). Leerla como UTF-8 revienta
    en el primer acento —`INFORMACIÓN`— y deja la cadena vacía, así que la
    comprobación de procesos contestaba «no está corriendo» siempre, incluso con
    el proceso delante. Se prueban las codificaciones en orden y la última no
    puede fallar.
    """
    try:
        salida = subprocess.run(
            ["tasklist", "/FI", filtro, "/NH"],
            capture_output=True, timeout=20,
        )
    except Exception:
        return ""
    crudo = salida.stdout or b""
    for codificacion in ("utf-8", "oem", "cp850", "cp1252"):
        try:
            return crudo.decode(codificacion)
        except (UnicodeDecodeError, LookupError):
            continue
    return crudo.decode("latin-1", "replace")


def vanguard_en_marcha() -> bool | None:
    """Si `vgc.exe` está corriendo. `None` si no se puede comprobar.

    Se mira el proceso y no el servicio porque `sc.exe` está en la lista negra
    de este equipo y `tasklist` da la misma información sin pedir permisos.

    `vgc.exe` es el servicio; `vgtray.exe` es solo el icono de la bandeja y no
    sirve para jugar, así que no cuenta como «Vanguard en marcha».
    """
    texto = _tasklist("IMAGENAME eq vgc.exe")
    if not texto.strip():
        return None
    return "vgc.exe" in texto.lower()


def juego_abierto() -> bool:
    """Si ya hay una partida abierta (dos a la vez no caben)."""
    return "league of legends.exe" in _tasklist("IMAGENAME eq League of Legends.exe").lower()


def cliente_abierto(ruta: str | None) -> tuple[int, str] | None:
    """`(puerto, contraseña)` del cliente de LoL, o `None` si está cerrado.

    El `lockfile` lo reescribe el cliente al arrancar y desaparece al cerrarlo,
    así que es la forma fiable de saber si está abierto y en qué puerto escucha
    su API local.

    Con un matiz: si el cliente se cierra de golpe (o se cuelga) el `lockfile`
    **se queda** con el puerto de la sesión anterior. Por eso se comprueba que
    el proceso que dice el fichero siga vivo; si no, se trata como cerrado en
    vez de intentar conectar a un puerto muerto y culpar al proxy.
    """
    if not ruta:
        return None
    try:
        texto = Path(ruta, "lockfile").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    partes = texto.split(":")
    if len(partes) < 5:
        return None
    try:
        pid = int(partes[1])
        puerto = int(partes[2])
    except ValueError:
        return None
    if not _pid_vivo(pid):
        return None
    return puerto, partes[3]


def _pid_vivo(pid: int) -> bool:
    """Si ese proceso existe ahora mismo. `False` si no se puede saber."""
    return str(pid) in _tasklist(f"PID eq {pid}")


def _lcu(puerto: int, clave: str, ruta: str, metodo: str = "GET",
         cuerpo: dict | None = None) -> tuple[int, str]:
    """Una petición a la API local del cliente (HTTPS con certificado propio).

    Sin `ProxyHandler({})` la petición se va por el proxy del sistema si lo hay
    (VPN, Clash, el propio sandbox) y contesta **502 Bad Gateway**: parece que el
    cliente no escucha cuando el que no llega es el proxy. La API del cliente es
    de loopback y por definición no pasa por ningún proxy.
    """
    import base64
    import json
    import urllib.error
    import urllib.request

    contexto = ssl.create_default_context()
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    credencial = base64.b64encode(f"riot:{clave}".encode()).decode()
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(
        f"https://127.0.0.1:{puerto}{ruta}",
        data=datos,
        method=metodo,
        headers={"Authorization": f"Basic {credencial}",
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
    )
    abridor = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=contexto),
    )
    try:
        with abridor.open(peticion, timeout=8) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:300]
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def alcanza(host_puerto: str, timeout: float = 5.0) -> tuple[bool, str]:
    """¿Responde el servidor de espectadores? TCP, que es lo que importa."""
    host, _, puerto = host_puerto.partition(":")
    inicio = time.monotonic()
    try:
        with socket.create_connection((host, int(puerto)), timeout=timeout) as s:
            ip = s.getpeername()[0]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    ms = (time.monotonic() - inicio) * 1000
    return True, f"{ip} en {ms:.0f} ms"


def parche_instalado(ruta: str) -> str:
    """La versión del juego instalada, leída del propio cliente."""
    try:
        import json

        datos = json.loads(
            Path(ruta, "Game", "code-metadata.json").read_text(encoding="utf-8")
        )
        return str(datos.get("version") or "?")
    except Exception:
        return "?"


# --------------------------------------------------------------------------- #
#  Diagnóstico
# --------------------------------------------------------------------------- #


def diagnostico() -> int:
    print("=" * ANCHO)
    print("DIAGNÓSTICO DEL ESPECTADOR")
    print("=" * ANCHO)

    _titulo("Instalación de League of Legends")
    ruta, origen = fuente_del_cliente()
    if ruta:
        exe = Path(ruta, "Game", "League of Legends.exe")
        print(f"  ruta     : {ruta}")
        print(f"  fuente   : {origen}")
        print(f"  ejecutable: {exe.stat().st_size:,} bytes".replace(",", "."))
        print(f"  parche   : {parche_instalado(ruta)}")
    else:
        print("  NO ENCONTRADA")
        print("  Se ha buscado en: variable LOL_PATH, RiotClientInstalls.json,")
        print("  el registro y todas las unidades.")
        print("  Si el juego está instalado, define LOL_PATH con su carpeta.")

    _titulo("Vanguard")
    vg = vanguard_en_marcha()
    print(f"  vgc.exe  : {_si_no(vg, 'en marcha', 'no corre')}")
    if vg is False:
        print("  Es normal si el cliente de Riot está cerrado: vgc.exe solo vive")
        print("  con él. Para espectar no hace falta — el juego usa el driver vgk.")

    _titulo("Cliente de League of Legends")
    lock = cliente_abierto(ruta)
    if lock:
        puerto, clave = lock
        print(f"  abierto  : sí (API local en el puerto {puerto})")
        estado, cuerpo = _lcu(puerto, clave, "/lol-gameflow/v1/gameflow-phase")
        if estado == 200:
            print(f"  fase     : {cuerpo.strip().strip(chr(34))}")
        elif estado == 0:
            # «error 0» no dice nada: el motivo es el cuerpo.
            print(f"  fase     : no se pudo preguntar ({cuerpo})")
        else:
            print(f"  fase     : error {estado}")
    else:
        print("  abierto  : no")

    _titulo("Servidores de espectadores")
    for plataforma in ("EUW1", "NA1", "KR", "LA2"):
        host = servidor_de(plataforma)
        ok, detalle = alcanza(host)
        print(f"  {plataforma:5} {host:34} {'OK' if ok else 'FALLA':5} {detalle}")

    _titulo("Partida en curso en este PC")
    print(f"  juego abierto: {_si_no(juego_abierto())}")

    print()
    return 0


# --------------------------------------------------------------------------- #
#  Lanzar
# --------------------------------------------------------------------------- #


def abrir_con_el_cliente(puerto: int, clave_lcu: str, servidor: str,
                         clave: str, game_id: int,
                         region: str) -> tuple[int, str]:
    """Pide al cliente de LoL que abra el espectador. Es el único camino que
    Vanguard permite.

    **Esto es lo importante del 04-11-2026**: lanzar `League of Legends.exe` a
    mano ya no funciona. Vanguard solo autoriza al cliente, así que hay que usar
    el lanzador de su función Watch, que recibe los argumentos del juego tal
    cual y no resuelve nada contra el shard del cliente (por eso también vale
    para partidas de otra plataforma).

    El cuerpo es un vector de argumentos, no un objeto: el cliente lo deserializa
    como `args` de tipo `vector` y con `{}` contesta «Couldn't assign value to
    'args' of type vector because the input not a collection».

    Y hay que **forzar la plataforma**. El cliente añade siempre los suyos al
    final (`-PlatformID=LA2`, `-Region=LA2` si el cliente está en LAS) y el juego
    se queda con el **primero** que ve. Con el del cliente, el `ReplayDownloader`
    pide `getGameMetaData/LA2/<partida>/…` al servidor de NA1, que contesta 404, y
    se queda en «Fetch MetaData Phase» indefinidamente: se ve la pantalla de
    carga y nada más. Con `-PlatformID=NA1` delante entra en `GAMELOOP` a los 19
    segundos (medido el 04-11-2026).
    """
    argumentos = [
        f"spectator {servidor} {clave} {game_id} {region}",
        f"-PlatformID={region}",
        f"-Region={region}",
    ]
    return _lcu(puerto, clave_lcu, "/lol-gameflow/v1/watch/launch", "POST",
                argumentos)


def lanzar(ruta: str, servidor: str, clave: str, game_id: int, region: str,
           seco: bool = False) -> int:
    """Abre el juego apuntando al espectador. Devuelve el código de salida."""
    exe = Path(ruta, "Game", "League of Legends.exe")
    if not exe.is_file():
        print(f"  No existe el ejecutable: {exe}")
        return 1

    _titulo("Lanzando")
    print(f"  partida : {game_id} ({region})")
    print(f"  servidor: {servidor}")
    print(f"  clave   : {clave[:6]}... ({len(clave)} caracteres)")
    print(f"  orden   : spectator {servidor} {clave[:6]}... {game_id} {region}")

    if seco:
        print("\n  (--sin-lanzar: no se ha abierto nada)")
        return 0

    if len(clave) != 32:
        # La clave buena son 32 caracteres. La otra (`decodedEncryptionKey`)
        # acaba en `=` y deja al cliente pidiendo el chunk 1 para siempre.
        print(f"\n  AVISO: la clave tiene {len(clave)} caracteres y debería tener 32.")
        print("  ¿Es `observers.encryptionKey` y no `decodedEncryptionKey`?")

    lock = cliente_abierto(ruta)
    if not lock:
        print("\n  El cliente de League of Legends no está abierto.")
        print("  El juego ya no se puede abrir desde fuera: Vanguard solo deja que")
        print("  lo abra el cliente. Ábrelo, espera a que cargue y vuelve a probar.")
        return 1

    puerto, clave_lcu = lock
    estado, cuerpo = abrir_con_el_cliente(puerto, clave_lcu, servidor, clave,
                                          game_id, region)
    if estado in (200, 204):
        print(f"\n  El cliente ha abierto la partida (HTTP {estado}).")
        print("  Tarda unos segundos y luego aplica el retardo del espectador.")
        return 0

    print(f"\n  El cliente no la abrió (HTTP {estado}): {cuerpo[:200]}")
    print("  Lo más habitual: el cliente está en la pantalla de entrar, la")
    print("  partida ya terminó, o el cliente se está actualizando.")
    return 1


def _partida_desde_riot(pro: str) -> tuple[str, dict | None]:
    """Busca al pro en el censo y devuelve `(estado, partida en vivo)`.

    Los tres estados se distinguen a propósito: «no está en el censo» y «está
    en el censo pero no en partida» son cosas distintas, y decirlas con la misma
    frase manda a buscar el problema donde no está.
    """
    from apis.riot_client import get_riot_client
    from tracking.soloq.accounts_io import load_tracked_accounts
    from utils.player_filters import get_tracked_players

    catalogo = get_tracked_players(load_tracked_accounts())
    buscado = pro.strip().casefold()
    candidatos = [
        p for p in catalogo
        if (p.name or "").casefold() == buscado
        or (getattr(p, "display_name", "") or "").casefold() == buscado
    ]
    if not candidatos:
        parecidos = [
            p.name for p in catalogo
            if buscado in (p.name or "").casefold()
        ][:8]
        print(f"  No está «{pro}» en el censo de {len(catalogo)} jugadores.")
        if parecidos:
            print(f"  ¿Querías decir: {', '.join(parecidos)}?")
        return "no-existe", None

    jugador = candidatos[0]
    print(f"  jugador : {jugador.name} ({jugador.team or 'sin equipo'}, "
          f"{jugador.league or '?'})")

    async def buscar() -> tuple[dict | None, list[str], int]:
        from apis.riot_client import RiotApiError, close_riot_client

        cliente = await get_riot_client()
        errores: list[str] = []
        revisadas = 0
        try:
            for cuenta in jugador.accounts:
                if not cuenta.puuid:
                    continue
                try:
                    partida = await cliente.get_active_game(cuenta.puuid,
                                                            cuenta.platform)
                except RiotApiError as exc:
                    # Un puuid de otra región contesta «400 Exception decrypting»
                    # y antes eso tumbaba el script con una traza entera. Se
                    # apunta y se sigue con la siguiente cuenta: casi todos los
                    # pros tienen más de una y el fallo de una no dice nada.
                    errores.append(f"{cuenta.platform}: {exc}")
                    continue
                revisadas += 1
                if partida:
                    return partida, errores, revisadas
            return None, errores, revisadas
        finally:
            # Sin esto, aiohttp se queja al salir («Unclosed client session») y
            # el mensaje tapa el resultado, que es lo único que se venía a ver.
            await close_riot_client()

    partida, errores, revisadas = asyncio.run(buscar())
    if errores:
        print(f"  cuentas que fallaron: {len(errores)}")
        for linea in errores[:3]:
            print(f"    - {linea[:110]}")
    if partida:
        return "en-partida", partida
    if revisadas == 0:
        # Decir «no está en partida» cuando no se pudo preguntar manda a buscar
        # el problema donde no está.
        return "no-comprobable", None
    return "sin-partida", None


def _extraer(partida: dict) -> tuple[int, str, str] | None:
    """`(gameId, platformId, encryptionKey)` de la respuesta de `spectator-v5`."""
    try:
        return (
            int(partida["gameId"]),
            str(partida["platformId"]),
            str(partida["observers"]["encryptionKey"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Abre una partida en vivo en el cliente de League of Legends.",
    )
    parser.add_argument("--pro", help="nombre del jugador (p. ej. Caps)")
    parser.add_argument("--partida", type=int, help="gameId de la partida")
    parser.add_argument("--clave", help="observers.encryptionKey (32 caracteres)")
    parser.add_argument("--region", default="EUW1", help="plataforma (EUW1, NA1, KR...)")
    parser.add_argument("--servidor", help="host:puerto del espectador (se deduce)")
    parser.add_argument("--bat", action="store_true",
                        help="solo escribe el .bat y dice dónde está")
    parser.add_argument("--esperar", action="store_true",
                        help="espera al retardo del espectador antes de abrir")
    parser.add_argument("--sin-lanzar", action="store_true",
                        help="enseña la orden pero no abre el juego")
    parser.add_argument("--diagnostico", action="store_true",
                        help="comprueba el PC y sale")
    args = parser.parse_args()

    if args.diagnostico or (not args.pro and not args.partida):
        return diagnostico()

    print("=" * ANCHO)
    print("ESPECTAR UNA PARTIDA")
    print("=" * ANCHO)

    if args.pro:
        _titulo(f"Buscando a {args.pro}")
        estado, partida = _partida_desde_riot(args.pro)
        if estado == "no-existe":
            return 1
        if not partida:
            if estado == "no-comprobable":
                print("  No se pudo comprobar: todas sus cuentas dieron error.")
            else:
                print("  Está en el censo, pero no en partida ahora mismo.")
            return 1
        datos = _extraer(partida)
        if not datos:
            print("  La respuesta no trae `observers.encryptionKey`.")
            return 1
        game_id, region, clave = datos
        reloj = desde_partida(partida)
        print(f"  partida : {game_id} ({region})")
        print(f"  reloj   : {mmss(reloj.transcurrido)} de juego, "
              f"espectador en {mmss(reloj.visible, con_signo=True)}")
        if not reloj.espectable:
            print(f"  AÚN NO: faltan {mmss(reloj.falta_para_espectar)} para poder verla.")
            if args.esperar:
                espera = reloj.falta_para_espectar + 3
                print(f"  Esperando {espera} s...")
                time.sleep(espera)
            else:
                print("  Ábrelo con --esperar y espera solo, o vuelve a intentarlo.")
                return 1
    else:
        if not args.clave:
            print("  Con --partida hace falta --clave (observers.encryptionKey).")
            return 1
        game_id, region, clave = args.partida, args.region.upper(), args.clave

    servidor = args.servidor or servidor_de(region)

    ruta = ruta_del_cliente()
    if not ruta:
        _titulo("Instalación no encontrada")
        print("  Pasa `--diagnostico` para ver qué fuente falló.")
        return 1

    if args.bat:
        fichero = generar_bat_spectate(servidor, clave, game_id, region)
        print(f"\n  .bat escrito en: {fichero}")
        return 0

    vg = vanguard_en_marcha()
    if vg is False:
        # No es un bloqueo: vgc.exe solo corre con el cliente de Riot abierto y
        # para espectar no hace falta (el juego tira del driver vgk, que va con
        # Windows). Bloquear aquí impedía espectar con Vanguard funcionando.
        print("\n  AVISO: el cliente de Riot no está abierto (vgc.exe no corre).")
        print("  Se intenta abrir la partida igual.")
    if juego_abierto():
        print("\n  Ya hay una partida abierta. Ciérrala antes de abrir otra.")
        if not args.sin_lanzar:
            return 1

    ok, detalle = alcanza(servidor)
    if not ok:
        print(f"\n  AVISO: {servidor} no responde ({detalle}).")

    return lanzar(ruta, servidor, clave, game_id, region, seco=args.sin_lanzar)


if __name__ == "__main__":
    sys.exit(main())

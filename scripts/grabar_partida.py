"""Graba una partida en vivo de un pro, sin cliente de LoL y sin capturar pantalla.

Por qué esto es más simple de lo que parecía
--------------------------------------------
La intuición —y la mía al principio— es que grabar requiere abrir el cliente de
LoL, poner el modo espectador y capturar la pantalla. Eso llevaría a: una máquina
por partida, GPU, y gigabytes por grabación.

**No funciona así.** El servidor de espectadores de Riot no sirve vídeo: sirve
**datos**. La partida se descarga en trozos (`chunks`) de unos pocos kilobytes, y
el cliente los usa para reconstruir la partida. Así que grabar es hacer peticiones
HTTP a un servidor, y ya está.

Comprobado el 29-09-2026 contra una partida real (Jojopyun, MKOI, NA1):
`getGameMetaData` y `getGameDataChunk` responden 200 con datos de verdad. Un
chunk medido: 4.672 bytes.

Lo que eso cambia
-----------------
- **Grabar es barato**: medido el 29-09-2026 sobre una partida real, cada chunk
  pesa unos **200 kB** y hay uno cada 30 s, así que una partida de 30 minutos son
  unos **12 MB**. Una tarde entera de partidas cabe en un móvil.
- **Es paralelo**: son peticiones HTTP, no procesos. Se pueden grabar veinte
  partidas a la vez sin GPU ni RAM.
- **El cuello de botella se mueve al vídeo**: convertir la grabación en vídeo sí
  necesita reproducirla con un cliente y capturar, y eso es secuencial. Por eso lo
  sensato es **grabar todo y renderizar solo lo que merece la pena** — y el
  criterio ya lo tiene el bot: las partidas con **varios pros**.

Detalle que costó encontrar: el servidor habla **HTTP plano en el puerto 8080**,
no HTTPS. Pedirlo por HTTPS da `WRONG_VERSION_NUMBER`, que parece un problema de
certificados y es solo el protocolo equivocado.

Uso
---
    python scripts/grabar_partida.py --equipos G2 T1 KC --salida grabaciones
    python scripts/grabar_partida.py --partida 5651360639 --plataforma NA1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")

#: El servidor de espectadores, por plataforma. Se pide por HTTP plano.
#: `NA1` y `NA2` son el mismo servidor con dos nombres; se prueban los dos.
HOSTS = {
    "NA1": ("spectator.na1.lol.pvp.net", "spectator.na2.lol.pvp.net"),
    "EUW1": ("spectator.euw1.lol.pvp.net",),
    "EUN1": ("spectator.eun1.lol.pvp.net",),
    "KR": ("spectator.kr.lol.pvp.net",),
    "BR1": ("spectator.br1.lol.pvp.net",),
    "LA1": ("spectator.la1.lol.pvp.net",),
    "LA2": ("spectator.la2.lol.pvp.net",),
    "OC1": ("spectator.oc1.lol.pvp.net",),
    "TR1": ("spectator.tr1.lol.pvp.net",),
    "JP1": ("spectator.jp1.lol.pvp.net",),
    "RU": ("spectator.ru.lol.pvp.net",),
}

TIEMPO = 15


def _base(plataforma: str) -> str:
    """La URL base del servidor de espectadores de esa plataforma."""
    for host in HOSTS.get(plataforma.upper(), ()):
        base = f"http://{host}:8080/observer-mode/rest/consumer"
        try:
            with urllib.request.urlopen(base, timeout=6):
                return base
        except urllib.error.HTTPError:
            return base          # responde: el host existe
        except Exception:
            continue
    raise RuntimeError(f"ningún servidor de espectadores responde para {plataforma}")


def _traer(url: str, binario: bool = False, *, reintentos: int = 4):
    """Descarga una URL del servidor de espectadores, respetando su 429.

    El servidor de espectadores también limita peticiones, y **no** se puede
    confundir con que la partida haya terminado: un 429 es «ahora no», un 404 es
    «esto ya no existe». La primera versión los trataba igual y daba por buena
    una grabación cortada —`completa: true` con 5 chunks de 60—, que es
    exactamente el tipo de error que hace publicar un vídeo a medias creyendo que
    está entero.
    """
    peticion = urllib.request.Request(url, headers={"User-Agent": "LoLProTrackr/1.0"})
    for intento in range(reintentos):
        try:
            with urllib.request.urlopen(peticion, timeout=TIEMPO) as r:
                datos = r.read()
            return datos if binario else json.loads(datos.decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or intento == reintentos - 1:
                raise
            espera = float(exc.headers.get("Retry-After") or 5)
            print(f"    límite del servidor de espectadores; esperando {espera:.0f}s")
            time.sleep(min(espera, 30))
    raise RuntimeError("sin respuesta tras varios intentos")


def grabar(plataforma: str, game_id: int, destino: Path, *, cada: float = 5.0,
           limite_min: float = 90.0) -> Path:
    """Descarga la partida entera, chunk a chunk, hasta que termina.

    Se sondea `getLastChunkInfo` en vez de bajar los chunks en orden a ciegas: el
    servidor dice cuál es el último disponible y cuándo estará el siguiente. Bajar
    uno que no existe da 404, y bajar el mismo dos veces gasta ancho de banda de
    Riot sin ganar nada.
    """
    base = _base(plataforma)
    carpeta = destino / f"{plataforma}_{game_id}"
    carpeta.mkdir(parents=True, exist_ok=True)

    print(f"  grabando {game_id} en {plataforma} -> {carpeta}")

    # Los metadatos primero: dicen cuánto dura el retardo del espectador y son la
    # cabecera de la grabación.
    try:
        meta = _traer(f"{base}/getGameMetaData/{plataforma}/{game_id}/0/token")
        (carpeta / "meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        print(f"    metadatos: retardo {meta.get('delayTime', '?')} ms · "
              f"chunks cada {meta.get('chunkTimeInterval', '?')} ms")
    except Exception as exc:
        print(f"    sin metadatos: {type(exc).__name__}")

    bajados: set[int] = set()
    inicio = time.monotonic()
    terminada = False

    while time.monotonic() - inicio < limite_min * 60:
        try:
            info = _traer(f"{base}/getLastChunkInfo/{plataforma}/{game_id}/0/token")
        except urllib.error.HTTPError as exc:
            # **404 sí significa que terminó**: el servidor deja de servir la
            # partida cuando acaba. Un 429 no — ese lo reintenta `_traer`, y si
            # llega aquí es que se agotaron los reintentos, así que se sigue
            # esperando en vez de dar la grabación por buena.
            if exc.code == 404:
                print("    la partida ya no está disponible: terminó")
                terminada = True
                break
            print(f"    el servidor no responde (HTTP {exc.code}); se reintenta")
            time.sleep(cada)
            continue
        except Exception as exc:
            print(f"    fallo sondeando: {type(exc).__name__}; se reintenta")
            time.sleep(cada)
            continue

        ultimo = info.get("chunkId")
        fin = info.get("endGameChunkId") or 0

        # Los chunks de arranque van aparte (`endStartupChunkId`).
        pendientes = [
            c for c in range(1, (ultimo or 0) + 1) if c not in bajados
        ]
        for cid in pendientes:
            try:
                datos = _traer(
                    f"{base}/getGameDataChunk/{plataforma}/{game_id}/{cid}/token",
                    binario=True,
                )
            except urllib.error.HTTPError:
                continue
            (carpeta / f"chunk_{cid:04d}.bin").write_bytes(datos)
            bajados.add(cid)

        if pendientes:
            print(f"    {len(bajados)} chunks · último {ultimo} · "
                  f"{sum(f.stat().st_size for f in carpeta.glob('chunk_*.bin')) // 1024} kB")

        # `endGameChunkId` deja de ser 0 cuando la partida termina y ya están
        # todos los chunks; ahí se puede cerrar sin esperar más.
        if fin and ultimo and ultimo >= fin:
            print(f"    partida terminada ({fin} chunks)")
            terminada = True
            break

        time.sleep(cada)

    if not terminada:
        print(f"    se alcanzó el límite de tiempo; la grabación queda parcial")

    (carpeta / "resumen.json").write_text(json.dumps({
        "game_id": game_id,
        "plataforma": plataforma,
        "chunks": sorted(bajados),
        "total_chunks": len(bajados),
        "bytes": sum(f.stat().st_size for f in carpeta.glob("chunk_*.bin")),
        "completa": terminada,
    }, indent=2), encoding="utf-8")

    return carpeta


async def buscar_partidas(equipos: tuple[str, ...], maximo: int) -> list[dict]:
    """Partidas en vivo de esos equipos, con los pros que hay en cada una.

    Devuelve una entrada por **partida**, no por jugador, y con la lista de pros
    dentro: eso es lo que permite priorizar las que tienen varios, que es el
    contenido que no puede hacer nadie más.
    """
    from apis.riot_client import close_riot_client, get_riot_client
    from tracking.soloq.accounts_io import load_tracked_accounts

    jugadores = load_tracked_accounts()
    objetivo = [
        j for j in jugadores
        if not equipos or (j.team or "").upper() in equipos
    ]
    print(f"revisando {len(objetivo)} jugador(es) de {', '.join(equipos) or 'todos'}")

    client = await get_riot_client()
    partidas: dict[int, dict] = {}
    try:
        for j in objetivo:
            for acc in j.accounts:
                if not acc.puuid:
                    continue
                try:
                    d = await client.get_active_game(acc.puuid, acc.platform or "euw1")
                except Exception:
                    continue
                if not d:
                    continue
                gid = d["gameId"]
                entrada = partidas.setdefault(gid, {
                    "game_id": gid,
                    "plataforma": d.get("platformId", "").upper(),
                    "clave": (d.get("observers") or {}).get("encryptionKey"),
                    "pros": [],
                })
                entrada["pros"].append(f"{j.name} ({j.team})")
    finally:
        await close_riot_client()

    # Las de más pros primero: son las que interesan.
    return sorted(partidas.values(), key=lambda p: -len(p["pros"]))[:maximo]


def main() -> int:
    ap = argparse.ArgumentParser(description="Graba partidas en vivo de pros.")
    ap.add_argument("--equipos", nargs="*", default=["G2", "T1", "GEN", "MKOI", "KC"],
                    help="trícoles de equipo a vigilar (vacío = todos)")
    ap.add_argument("--partida", type=int, help="graba esta partida y no busca")
    ap.add_argument("--plataforma", default="NA1", help="con --partida")
    ap.add_argument("--maximo", type=int, default=3, help="cuántas grabar a la vez")
    ap.add_argument("--salida", default="grabaciones")
    args = ap.parse_args()

    destino = Path(args.salida)
    destino.mkdir(parents=True, exist_ok=True)

    if args.partida:
        grabar(args.plataforma.upper(), args.partida, destino)
        return 0

    partidas = asyncio.run(buscar_partidas(tuple(args.equipos), args.maximo))
    if not partidas:
        print("no hay ninguna partida en vivo de esos equipos ahora mismo.")
        return 0

    print(f"\n{len(partidas)} partida(s) en vivo:")
    for p in partidas:
        print(f"  {p['game_id']} · {p['plataforma']} · {len(p['pros'])} pro(s): "
              f"{', '.join(p['pros'])}")
        print(f"      clave de espectador: {'sí' if p['clave'] else 'no'}")

    print("\ngrabando (a la vez, sin cliente de LoL)...")
    for p in partidas:
        try:
            grabar(p["plataforma"], p["game_id"], destino)
        except Exception as exc:
            print(f"  {p['game_id']}: fallo — {type(exc).__name__}: {exc}")

    total = sum(f.stat().st_size for f in destino.rglob("*.bin"))
    print(f"\ntotal grabado: {total / 1024:.0f} kB en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

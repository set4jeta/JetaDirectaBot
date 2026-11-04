"""Que el `.bat` de espectar abra la partida de verdad, y sin pedir permisos.

Por qué esta prueba existe
--------------------------
El `.bat` es la única forma que tiene el usuario de ver la partida, y **falla en
silencio**: si la ruta del cliente está mal, se abre una consola, no encuentra el
ejecutable y se cierra antes de que dé tiempo a leer nada.

Y falló de la peor manera posible: la ruta se buscaba **al generar** el `.bat`,
que es en Render. En Render no hay `C:`, ni registro de Windows, ni `winreg`, así
que la búsqueda devolvía `None` **siempre** y todos los `.bat` salían con
`LOL_PATH` vacío. El usuario recibía un lanzador que solo sabía decir «no
encontrado».

La prueba anterior no lo vio porque se ejecutaba en Windows: comprobaba la
función en la única máquina donde sí funciona. De ahí `prueba_generado_en_linux`,
que simula Render y exige que el `.bat` sepa buscar por su cuenta.

Lo que se comprueba aquí es lo que se puede comprobar sin abrir el juego.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from utils import spectate_bat  # noqa: E402
from utils.spectate_bat import (  # noqa: E402
    generar_bat_spectate,
    ruta_del_cliente,
    servidor_de,
)

fallos: list[str] = []


def ok(condicion: bool, etiqueta: str, extra: str = "") -> None:
    print(f"  {'OK   ' if condicion else 'FALLA'} {etiqueta}"
          f"{f' ({extra})' if extra else ''}")
    if not condicion:
        fallos.append(etiqueta)


def _bat(**kwargs) -> str:
    argumentos = dict(server="spectator.na1.lol.pvp.net:8080",
                      key="u1j8NjZWRpow2grAca5PbrYGiFEpIkn7",
                      match_id=5651554245, region="NA1")
    argumentos.update(kwargs)
    return Path(generar_bat_spectate(**argumentos)).read_text(encoding="utf-8")


def prueba_datos_de_la_partida() -> None:
    print("\n=== el .bat lleva los datos de esta partida ===")

    texto = _bat()

    ok("spectator.na1.lol.pvp.net:8080" in texto, "el servidor de espectadores")
    ok("u1j8NjZWRpow2grAca5PbrYGiFEpIkn7" in texto,
       "la clave de la partida, que cambia cada vez")
    ok("5651554245" in texto, "el identificador de la partida")
    ok("NA1" in texto, "y la región")
    ok("spectator %SERVER% %KEY% %MATCH_ID% %REGION%" in texto,
       "el comando de espectador se arma con esas cuatro cosas")


def prueba_generado_en_linux() -> None:
    """El caso que rompió el `.bat` durante un mes: generarlo sin Windows.

    En Render `ruta_del_cliente()` devuelve `None` por definición. El `.bat` que
    sale de ahí **tiene que seguir sirviendo**: la búsqueda va dentro, no en el
    generador.
    """
    print("\n=== generado en Render (sin Windows), el .bat sigue buscando solo ===")

    original = spectate_bat.ruta_del_cliente
    spectate_bat.ruta_del_cliente = lambda: None
    try:
        texto = _bat()
    finally:
        spectate_bat.ruta_del_cliente = original

    # Las cuatro fuentes de búsqueda tienen que estar en el fichero.
    ok("call :desde_json" in texto,
       "busca en RiotClientInstalls.json al ejecutarse")
    ok("RiotClientInstalls.json" in texto, "y el fichero se nombra")
    ok("call :desde_registro" in texto, "consulta el registro de Windows")
    ok("reg query" in texto, "con reg query")
    ok("call :escanear" in texto, "y barre todas las unidades")
    ok('for %%D in (C D E F G H I J K L M N O P Q R S T U V W X Y Z)' in texto,
       "las 26 letras, no solo de la C a la K")
    ok("set /p \"LOL_PATH=Carpeta / Folder: \"" in texto,
       "y si no encuentra nada, pregunta la carpeta en vez de morir")

    # Y lo que no puede pasar: que se quede sin ruta y se cierre sin explicar.
    ok("goto :preguntar" in texto, "sin ruta se va a preguntar, no al vacío")
    ok("pause" in texto, "y siempre hay un pause antes de cerrar")

    # La pista del generador puede ir vacía: es opcional, no el único camino.
    ok('call :probar ""' in texto,
       "la pista del generador puede estar vacía sin romper nada")


def prueba_sin_vanguard() -> None:
    print("\n=== no toca Vanguard, así que no pide administrador ===")

    texto = _bat()

    for prohibido in ("net stop", "net start", "taskkill"):
        ok(prohibido not in texto, f"no aparece «{prohibido}»",
           "parar Vanguard es lo único que obligaba a pedir administrador")

    # `sc stop`/`sc start` sí serían tocar Vanguard; `sc query` solo mirar.
    ok("sc stop" not in texto and "sc start" not in texto,
       "no arranca ni para servicios")

    # Lo que sí hace: comprobar que está vivo, porque sin él no hay juego.
    ok("vgc.exe" in texto, "comprueba que Vanguard esté en marcha")
    ok("Vanguard no esta corriendo" in texto,
       "y avisa cuando no lo está, en vez de fallar sin decir nada")


def prueba_ruta_detectada() -> None:
    print("\n=== la ruta del cliente se detecta, no se escribe a mano ===")

    detectada = ruta_del_cliente()
    ok(detectada is not None,
       "se encuentra la instalación del cliente en este PC",
       str(detectada))

    if detectada:
        ok(Path(detectada, "Game", "League of Legends.exe").is_file(),
           "y apunta a un ejecutable que existe de verdad")

    texto = _bat()

    if detectada:
        ok(f'call :probar "{detectada}"' in texto,
           "el .bat lleva la ruta detectada como pista", detectada)

    # La ruta vieja estaba fijada a C:. Si el cliente no está ahí, que no
    # aparezca como si fuera la buena.
    if not Path("C:\\Riot Games\\League of Legends\\Game\\League of Legends.exe").is_file():
        ok("C:\\Riot Games\\League of Legends\\Game" not in texto,
           "y no lleva la ruta por defecto escrita a mano")


def prueba_servidores() -> None:
    print("\n=== el servidor de espectadores de cada plataforma ===")

    ok(servidor_de("EUW1") == "spectator.euw1.lol.pvp.net:8080",
       "EUW1", servidor_de("EUW1"))
    ok(servidor_de("euw1") == servidor_de("EUW1"),
       "da igual cómo venga escrita la plataforma")
    ok(servidor_de("KR") == "spectator.kr.lol.pvp.net:8080",
       "KR", servidor_de("KR"))
    ok(servidor_de("LA2") == "spectator.la2.lol.pvp.net:8080",
       "LA2, que es donde juega el dueño", servidor_de("LA2"))
    # Una plataforma que no esté en la tabla se construye igual: Riot usa la
    # misma convención para todas y no queremos romper al añadir una liga.
    ok(servidor_de("XX9") == "spectator.xx9.lol.pvp.net:8080",
       "una plataforma desconocida no revienta", servidor_de("XX9"))


def prueba_variable_de_entorno() -> None:
    print("\n=== se puede forzar la ruta sin tocar código ===")

    real = os.environ.get("LOL_PATH")
    try:
        # Una carpeta cualquiera que no tiene el ejecutable: no debe colarse.
        os.environ["LOL_PATH"] = str(RAIZ)
        ok(ruta_del_cliente() != str(RAIZ),
           "una ruta forzada que no tiene el cliente se ignora")

        detectada = ruta_del_cliente()
        if detectada:
            os.environ["LOL_PATH"] = detectada
            ok(ruta_del_cliente() == detectada,
               "y una que sí lo tiene se respeta", detectada)
    finally:
        if real is None:
            os.environ.pop("LOL_PATH", None)
        else:
            os.environ["LOL_PATH"] = real


def prueba_trampas_de_cmd() -> None:
    """Las dos trampas que dejaron el `.bat` mudo y no daban ningún error.

    Las dos se descubrieron ejecutando el `.bat` de verdad en el PC, no leyendo
    el código: el fichero se veía perfecto y no encontraba nada.
    """
    print("\n=== las trampas de cmd que fallaban en silencio ===")

    texto = _bat()

    # 1) El `|` dentro de `for /f`: la costumbre de escaparlo (`^|`) vale cuando
    #    el comando no va entre comillas. Aquí sí va, cmd respeta las comillas y
    #    el `^` llegaba hasta PowerShell, que contestaba «no se encuentra ningún
    #    parámetro de posición que acepte el argumento '^'» y dejaba la fuente
    #    muda: la buena, RiotClientInstalls.json.
    ok("^| ConvertFrom-Json" not in texto,
       "el pipe de PowerShell no va escapado (el ^ llegaba a PowerShell)")
    ok("| ConvertFrom-Json" in texto, "y el pipe está, sin escapar")

    # 2) El JSON de Riot guarda las rutas con barra normal y barra final
    #    (`D:/Riot Games/League of Legends/`). Recortar solo la invertida deja
    #    `.../\Game\...` y `exist` falla sin decir nada.
    ok('if "!CAND:~-1!"=="/"' in texto,
       "se recorta también la barra normal del final")

    # 3) Comparar el argumento entre comillas aborta el .bat con el código 255.
    ok('if "%~1"==""' not in texto,
       "no se compara el argumento entre comillas (abortaba con el código 255)")
    ok('set "CAND=%~1"' in texto, "se copia a CAND y se pregunta `if not defined`")


def prueba_no_puede_tocar_vanguard() -> None:
    """El `.bat` no puede parar, borrar ni reconfigurar nada del sistema.

    Esto no es paranoia: el dueño vio el icono de Vanguard gris justo después de
    ejecutar el lanzador y lo lógico es culpar al lanzador. La respuesta tiene
    que ser una lista de lo que el fichero puede hacer, no un «yo no fui».

    Se parte cada línea en segmentos (`&`, `|`) y se mira el **primer token** de
    cada uno, que es el programa que se ejecuta de verdad. Así «del bot» en un
    comentario no cuenta como el comando `del`.
    """
    print("\n=== el .bat no puede parar ni tocar Vanguard ===")

    texto = _bat()

    # Programas que pueden matar procesos, parar servicios o borrar cosas.
    prohibidos = {
        "taskkill", "tskill", "pskill", "psservice", "nssm",
        "del", "erase", "rd", "rmdir", "format", "diskpart", "bcdedit",
        "wmic", "schtasks", "shutdown", "vssadmin", "regedit",
        "net1", "netsh", "takeown", "icacls", "cacls",
    }

    encontrados: list[str] = []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("::") or limpia.lower().startswith("rem "):
            continue
        for segmento in limpia.replace("&", "|").split("|"):
            trozos = segmento.strip().split()
            if not trozos:
                continue
            primero = trozos[0].lower().strip('"')
            if primero in prohibidos:
                encontrados.append(limpia[:80])

    ok(not encontrados,
       "no hay ningún comando que mate procesos o pare servicios",
       "; ".join(encontrados[:2]))

    # `sc` y `net` son legítimos para consultar, y peligrosos con stop/delete.
    bajo = texto.lower()
    for pareja in ("sc stop", "sc delete", "sc config", "net stop", "net start",
                   "reg delete", "reg add", "stop-service"):
        ok(pareja not in bajo, f"no aparece «{pareja}»")

    # `reg` solo puede consultar.
    consultas_reg = [l for l in texto.splitlines()
                     if "reg " in l.lower() and l.strip().lower().startswith("for")]
    ok(consultas_reg and all("reg query" in l.lower() for l in consultas_reg),
       "el registro solo se consulta con `reg query`",
       f"{len(consultas_reg)} consultas")

    # PowerShell solo puede LEER: Get-Content y ConvertFrom-Json.
    lineas_ps = [l for l in texto.splitlines()
                 if "powershell" in l.lower() and not l.strip().startswith("::")]
    ok(len(lineas_ps) == 1, "hay una sola llamada a PowerShell",
       f"{len(lineas_ps)}")
    for linea in lineas_ps:
        for verbo in ("remove-", "stop-", "set-", "start-", "restart-",
                      "new-", "invoke-", "sc.exe", "taskkill", "delete"):
            ok(verbo not in linea.lower(),
               f"PowerShell no usa «{verbo}» (solo lee el JSON)")

    # Y lo único que nombra a Vanguard son consultas o mensajes.
    for linea in texto.splitlines():
        limpia = linea.strip()
        if "vgc" not in limpia.lower() and "vanguard" not in limpia.lower():
            continue
        es_consulta = limpia.lower().startswith("tasklist")
        es_mensaje = limpia.startswith("::") or limpia.lower().startswith("echo")
        ok(es_consulta or es_mensaje,
           "toda mención a Vanguard es una consulta o un mensaje", limpia[:70])

    # El ejecutable del juego es lo único que se abre, y solo una vez.
    ok(texto.count('start ""') == 1,
       "solo hay un `start`, el del juego")
    ok('start "" "%EXE_PATH%"' in texto,
       "y ese `start` abre League of Legends, nada más")


def main() -> None:
    print("=" * 66)
    print("EL .BAT DE ESPECTAR")
    print("=" * 66)

    prueba_datos_de_la_partida()
    prueba_generado_en_linux()
    prueba_sin_vanguard()
    prueba_no_puede_tocar_vanguard()
    prueba_trampas_de_cmd()
    prueba_ruta_detectada()
    prueba_servidores()
    prueba_variable_de_entorno()

    print(f"\nfallos : {len(fallos)}")
    if fallos:
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()

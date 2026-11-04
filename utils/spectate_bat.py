#utils/spectate_bat.py
"""El `.bat` que abre la partida de un pro en el cliente de League of Legends.

El fallo que tenía esto (y que se arregló el 03-11-2026)
-------------------------------------------------------
La ruta del cliente se buscaba **cuando se generaba el `.bat`**, y eso pasa en
Render, que es Linux: allí no hay `C:`, no hay registro de Windows y `winreg` ni
siquiera existe. Así que `ruta_del_cliente()` devolvía `None` **siempre**, el
`.bat` salía con `LOL_PATH` vacío y lo único que hacía al ejecutarse era decir
«League of Legends no encontrado» y cerrarse. Todos los avisos con `.bat` desde
el 30-09-2026 llevaban un lanzador que no podía funcionar en ningún PC.

La prueba no lo vio porque se ejecutaba en Windows: comprobaba la función en la
máquina donde sí funciona. La prueba nueva simula Linux y falla si el `.bat`
depende de la ruta del generador.

Por eso ahora la búsqueda va **dentro del `.bat`**, que es lo único que se
ejecuta en el PC del usuario. El generador solo puede aportar una pista, y esa
pista es opcional: si el `.bat` se generó en otro sitio, se ignora.

Las cinco fuentes, en orden
---------------------------
1. `LOL_PATH` en el entorno (para forzar una instalación rara sin editar nada).
2. La pista del generador (solo vale si el `.bat` se creó en este mismo PC).
3. `RiotClientInstalls.json` — el fichero que usa el propio cliente de Riot para
   saber dónde tiene instalado cada juego. Es la fuente buena.
4. El registro de Windows (`Riot Games, Inc\\League of Legends` → `Location`).
5. Barrido de **todas** las unidades y las carpetas habituales.

Vanguard: se comprueba, no se toca
----------------------------------
Durante la noche del 30-09-2026 se abrieron partidas con `vgtray.exe` corriendo y
funcionaron. Parar Vanguard era lo único que obligaba a ejecutar el `.bat` como
administrador, así que se dejó de hacer: un `.bat` que pide administrador para
algo innecesario es un `.bat` que la mitad de la gente no llega a ejecutar.

Lo que **sí** hay que hacer es comprobar que está **en marcha**. Vanguard es
requisito del juego (`dependencies: vanguard: true` en
`league_of_legends.live.product_settings.yaml`) y sin `vgc.exe` el juego no
arranca. El `.bat` nunca lo arranca ni lo para: si no está, **no lanza el
juego** y lo explica. Lanzarlo igual deja al cliente a medias y es la forma más
fácil de acabar con el icono gris y sin saber por qué (03-11-2026).

Que no exista una ruta no significa que no haya juego
-----------------------------------------------------
Si las cinco fuentes fallan, el `.bat` **pregunta** la carpeta en vez de morir.
Y si el juego no llega a abrirse, dice dónde está el log en vez de cerrarse en
silencio: el síntoma de antes (una consola que parpadea) no decía nada.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

#: Dónde suele estar el cliente, relativo a la raíz de cada unidad.
SUBCARPETAS = (
    r"Riot Games\League of Legends",
    r"Program Files\Riot Games\League of Legends",
    r"Program Files (x86)\Riot Games\League of Legends",
    r"Games\Riot Games\League of Legends",
    r"Riot\League of Legends",
)

#: Variable de entorno para forzar la ruta, si alguien tiene una instalación rara.
VARIABLE = "LOL_PATH"

#: Servidor de espectadores de cada plataforma, **medido** el 03-11-2026: todos
#: resuelven y aceptan TCP en el 8080. `NA2` no existe (DNS `gaierror`), así que
#: no está en la tabla: si algún día hace falta, la URL se construye igual.
HOSTS: dict[str, str] = {
    "BR1": "spectator.br1.lol.pvp.net",
    "EUN1": "spectator.eun1.lol.pvp.net",
    "EUW1": "spectator.euw1.lol.pvp.net",
    "JP1": "spectator.jp1.lol.pvp.net",
    "KR": "spectator.kr.lol.pvp.net",
    "LA1": "spectator.la1.lol.pvp.net",
    "LA2": "spectator.la2.lol.pvp.net",
    "ME1": "spectator.me1.lol.pvp.net",
    "NA1": "spectator.na1.lol.pvp.net",
    "OC1": "spectator.oc1.lol.pvp.net",
    "PH2": "spectator.ph2.lol.pvp.net",
    "RU": "spectator.ru.lol.pvp.net",
    "SG2": "spectator.sg2.lol.pvp.net",
    "TH2": "spectator.th2.lol.pvp.net",
    "TR1": "spectator.tr1.lol.pvp.net",
    "TW2": "spectator.tw2.lol.pvp.net",
    "VN2": "spectator.vn2.lol.pvp.net",
}

#: El servidor de espectadores habla su protocolo en este puerto, en **HTTP
#: plano**. Pedirlo por HTTPS devuelve `WRONG_VERSION_NUMBER`, que parece un
#: problema de certificados y es solo el protocolo equivocado.
PUERTO = 8080


def servidor_de(platform: str) -> str:
    """El `host:puerto` del servidor de espectadores de una plataforma.

    Se centraliza aquí porque antes se construía a mano en `active_match_embed`
    y la tabla de regiones ya existía en el grabador: dos listas que se
    desincronizan sin que nadie se entere. Una plataforma desconocida no rompe
    nada — se construye el nombre igual, que es lo que hace Riot.
    """
    plataforma = (platform or "").strip().upper()
    host = HOSTS.get(plataforma) or f"spectator.{plataforma.lower()}.lol.pvp.net"
    return f"{host}:{PUERTO}"


# --------------------------------------------------------------------------- #
#  Detección de la instalación (solo tiene sentido en el PC del usuario)
# --------------------------------------------------------------------------- #


def _es_instalacion(ruta: str | os.PathLike) -> bool:
    """¿Esta carpeta es la del cliente? Tiene que estar el ejecutable."""
    return Path(ruta, "Game", "League of Legends.exe").is_file()


def _desde_json_de_riot() -> str | None:
    """La fuente buena: el fichero que usa el propio Riot Client.

    `RiotClientInstalls.json` guarda, en `associated_client`, la carpeta de cada
    juego instalado. Es lo que consulta Riot cuando abres un juego desde el
    lanzador, así que no puede estar mal aunque el usuario lo haya instalado en
    una unidad rara o con un nombre de carpeta cambiado.
    """
    candidatos = []
    for base in (
        os.environ.get("ProgramData"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
    ):
        if base:
            candidatos.append(Path(base, "Riot Games", "RiotClientInstalls.json"))

    for fichero in candidatos:
        try:
            datos = json.loads(fichero.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        asociados = datos.get("associated_client") or {}
        for ruta in asociados:
            limpia = str(ruta).replace("/", "\\").rstrip("\\")
            if _es_instalacion(limpia):
                return limpia
    return None


def _desde_registro() -> str | None:
    """El registro de Windows, por si está y el JSON no.

    No siempre está: en el PC del dueño la clave de Riot no existe, y por eso
    esto es una fuente más y no la única.
    """
    try:
        import winreg
    except ImportError:
        return None

    claves = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Riot Games, Inc\League of Legends"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Riot Games, Inc\League of Legends"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Riot Games, Inc\League of Legends"),
    )
    for raiz, sub in claves:
        try:
            with winreg.OpenKey(raiz, sub) as clave:
                valor, _ = winreg.QueryValueEx(clave, "Location")
        except OSError:
            continue
        if _es_instalacion(valor):
            return valor
    return None


def _unidades() -> list[str]:
    """Todas las letras de unidad que existen, no solo de la C a la K."""
    letras: list[str] = []
    try:
        import ctypes

        mascara = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if mascara & (1 << i):
                letras.append(chr(ord("A") + i))
    except Exception:
        pass
    if not letras:
        letras = list("CDEFGHIJKLMNOPQRSTUVWXYZ")
    return letras


def _por_barrido() -> str | None:
    """Barrido de unidades y carpetas habituales. Lo último, y lo más lento."""
    for letra in _unidades():
        for sub in SUBCARPETAS:
            candidata = f"{letra}:\\{sub}"
            if _es_instalacion(candidata):
                return candidata
    return None


def ruta_del_cliente() -> str | None:
    """La carpeta de instalación del cliente, o `None` si no aparece.

    **Esto solo funciona en el PC del usuario.** En Render (Linux) devuelve
    `None` por definición, y por eso el `.bat` ya no depende de este resultado:
    lo usa como pista y vuelve a buscar por su cuenta.
    """
    de_entorno = os.environ.get(VARIABLE)
    if de_entorno and _es_instalacion(de_entorno):
        return de_entorno

    for fuente in (_desde_json_de_riot, _desde_registro, _por_barrido):
        ruta = fuente()
        if ruta:
            return ruta
    return None


def fuente_del_cliente() -> tuple[str | None, str]:
    """Lo mismo que `ruta_del_cliente`, pero diciendo **de dónde** sale.

    Sirve para el diagnóstico: cuando alguien dice «no me lo encuentra», lo
    primero que hay que saber es qué fuente falló.
    """
    de_entorno = os.environ.get(VARIABLE)
    if de_entorno and _es_instalacion(de_entorno):
        return de_entorno, f"variable {VARIABLE}"

    for nombre, fuente in (
        ("RiotClientInstalls.json", _desde_json_de_riot),
        ("registro de Windows", _desde_registro),
        ("barrido de unidades", _por_barrido),
    ):
        ruta = fuente()
        if ruta:
            return ruta, nombre
    return None, "ninguna fuente"


# --------------------------------------------------------------------------- #
#  El .bat
# --------------------------------------------------------------------------- #

_PLANTILLA = r"""@echo off
setlocal enabledelayedexpansion
title League of Legends - partida {match_id}

:: ------------------------------------------------------------------
::  Partida {match_id} de {region}
::  Generado por el bot. La clave es de ESTA partida y caduca.
::
::  Este fichero busca el League of Legends en el PC donde se
::  ejecuta: no lleva la ruta de nadie escrita a mano.
::
::  No pide administrador y no para Vanguard. Vanguard tiene que
::  estar EN MARCHA: el juego no arranca sin el.
:: ------------------------------------------------------------------

set "SERVER={server}"
set "KEY={key}"
set "MATCH_ID={match_id}"
set "REGION={region}"

:: 1) Variable de entorno, si alguien la puso a mano.
if defined LOL_PATH (
  if exist "%LOL_PATH%\Game\League of Legends.exe" goto :ruta_lista
)
set "LOL_PATH="

:: 2) La pista del bot. Solo vale si el .bat se genero en este PC.
call :probar "{pista}"
if defined LOL_PATH goto :ruta_lista

:: 3) RiotClientInstalls.json, la fuente que usa el propio cliente.
call :desde_json
if defined LOL_PATH goto :ruta_lista

:: 4) El registro de Windows.
call :desde_registro
if defined LOL_PATH goto :ruta_lista

:: 5) Barrido de todas las unidades.
call :escanear
if defined LOL_PATH goto :ruta_lista

goto :preguntar


:probar
:: Valida una carpeta candidata y, si sirve, la deja en LOL_PATH.
:: Se recortan barras y espacios del final porque el JSON de Riot y la salida
:: de `reg query` no siempre vienen limpios, y un espacio de mas hace que
:: `exist` falle y la ruta se descarte sin decir nada.
::
:: Ojo con el orden: primero se copia a CAND y se pregunta `if not defined`.
:: Comparar el argumento entre comillas (`"%~1"==""`) parece lo natural y es un
:: error: si la ruta llega con comillas, la comparacion queda con tres comillas
:: seguidas, cmd no la puede analizar y **aborta el .bat entero** con el codigo
:: 255 en vez de descartar la ruta.
set "CAND=%~1"
if not defined CAND exit /b 0
:: Las comillas se quitan de una pasada (sustitucion, no comparacion): asi el
:: resto del bloque puede comparar el ultimo caracter sin que cmd se atragante.
set CAND=!CAND:"=!
:limpiar
if not defined CAND exit /b 0
:: Se recortan las dos barras. `RiotClientInstalls.json` guarda las rutas con
:: barra normal y barra final (`D:/Riot Games/League of Legends/`), asi que
:: recortar solo la invertida deja `.../\Game\...` y `exist` falla sin decir
:: nada: la fuente buena se descartaba siempre.
if "!CAND:~-1!"=="\" ( set "CAND=!CAND:~0,-1!" & goto :limpiar )
if "!CAND:~-1!"=="/" ( set "CAND=!CAND:~0,-1!" & goto :limpiar )
if "!CAND:~-1!"==" " ( set "CAND=!CAND:~0,-1!" & goto :limpiar )
if not exist "!CAND!\Game\League of Legends.exe" exit /b 0
set "LOL_PATH=!CAND!"
exit /b 0


:desde_json
set "RIOT_JSON=%ProgramData%\Riot Games\RiotClientInstalls.json"
if not exist "%RIOT_JSON%" set "RIOT_JSON=%LOCALAPPDATA%\Riot Games\RiotClientInstalls.json"
if not exist "%RIOT_JSON%" exit /b 0
:: El `|` va SIN escapar. La costumbre de escaparlo (`^|`) vale cuando el
:: comando no va entre comillas, pero aqui si lo van: cmd respeta las comillas y
:: el `^` se colaba hasta PowerShell, que contestaba «no se encuentra ningun
:: parametro de posicion que acepte el argumento '^'» y dejaba la fuente muda.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; (Get-Content -Raw -LiteralPath '%RIOT_JSON%' | ConvertFrom-Json).associated_client.PSObject.Properties.Name"`) do (
  call :probar "%%P"
  if defined LOL_PATH exit /b 0
)
exit /b 0


:desde_registro
for /f "tokens=2*" %%A in ('reg query "HKLM\SOFTWARE\WOW6432Node\Riot Games, Inc\League of Legends" /v Location 2^>nul') do call :probar "%%B"
if defined LOL_PATH exit /b 0
for /f "tokens=2*" %%A in ('reg query "HKLM\SOFTWARE\Riot Games, Inc\League of Legends" /v Location 2^>nul') do call :probar "%%B"
if defined LOL_PATH exit /b 0
for /f "tokens=2*" %%A in ('reg query "HKCU\SOFTWARE\Riot Games, Inc\League of Legends" /v Location 2^>nul') do call :probar "%%B"
exit /b 0


:escanear
for %%D in (C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
  call :probar "%%D:\Riot Games\League of Legends"
  if defined LOL_PATH exit /b 0
  call :probar "%%D:\Program Files\Riot Games\League of Legends"
  if defined LOL_PATH exit /b 0
  call :probar "%%D:\Program Files (x86)\Riot Games\League of Legends"
  if defined LOL_PATH exit /b 0
  call :probar "%%D:\Games\Riot Games\League of Legends"
  if defined LOL_PATH exit /b 0
  call :probar "%%D:\Riot\League of Legends"
  if defined LOL_PATH exit /b 0
)
exit /b 0


:preguntar
echo.
echo   No se encontro League of Legends en este PC.
echo   League of Legends was not found on this PC.
echo.
echo   Buscado en RiotClientInstalls.json, en el registro y en todas
echo   las unidades (C:, D:, E: ...).
echo.
echo   Escribe la carpeta que contiene la subcarpeta Game.
echo   Type the folder that contains the Game subfolder.
echo.
set "LOL_PATH="
set /p "LOL_PATH=Carpeta / Folder: "
if not defined LOL_PATH goto :fin_sin_ruta
call :probar "%LOL_PATH%"
if not defined LOL_PATH goto :fin_sin_ruta
goto :ruta_lista

:fin_sin_ruta
echo.
echo   Sin ruta no se puede abrir la partida.
echo   Without the path the game cannot be opened.
pause
exit /b 1


:ruta_lista
set "GAME_DIR=%LOL_PATH%\Game"
set "EXE_PATH=%GAME_DIR%\League of Legends.exe"

if not exist "%EXE_PATH%" goto :preguntar

:: --- Avisos previos: no bloquean, pero explican el fallo antes de que pase ---

:: Vanguard: se comprueba que este en marcha. No se arranca ni se para.
tasklist /FI "IMAGENAME eq vgc.exe" 2>nul | find /i "vgc.exe" >nul
if errorlevel 1 (
  echo.
  echo   Vanguard no esta corriendo.
  echo   Vanguard is not running.
  echo.
  echo   El juego no arranca sin Vanguard, y abrirlo igual deja el
  echo   cliente a medias. Abre Riot Client, espera a que el icono se
  echo   ponga rojo y vuelve a ejecutar este archivo.
  echo.
  echo   The game cannot start without Vanguard. Open Riot Client, wait
  echo   for the icon to turn red, then run this file again.
  echo.
  pause
  exit /b 1
)

:: Dos partidas a la vez no caben: si ya hay una, esto no haria nada.
tasklist /FI "IMAGENAME eq League of Legends.exe" 2>nul | find /i "League of Legends.exe" >nul
if not errorlevel 1 (
  echo.
  echo   Ya hay una partida abierta en este PC.
  echo   A game is already open on this PC.
  echo.
  echo   Cierra esa ventana antes de espectar otra.
  echo   Close it before spectating another one.
  echo.
  pause
  exit /b 1
)

:: El servidor de espectadores, si se puede comprobar sin depender de nada.
where curl >nul 2>&1
if not errorlevel 1 (
  curl -s -o nul --max-time 6 "http://%SERVER%/" >nul 2>&1
  if errorlevel 1 (
    echo.
    echo   Aviso: no responde el servidor de espectadores %SERVER%.
    echo   Warning: spectator server %SERVER% is not responding.
    echo.
    echo   Puede ser tu conexion o que la partida ya no exista.
    echo.
    timeout /t 7 /nobreak >nul 2>&1
  )
)

echo.
echo   Abriendo la partida %MATCH_ID% (%REGION%)...
echo   Opening game %MATCH_ID% (%REGION%)...
echo.

cd /d "%GAME_DIR%"
start "" "%EXE_PATH%" "spectator %SERVER% %KEY% %MATCH_ID% %REGION%" "-Product=LoL" "-GameBaseDir=%LOL_PATH%"

:: El juego tarda unos segundos en aparecer. Si no aparece, es que murio al
:: arrancar, y eso antes se veia como una ventana que se cierra y nada mas.
timeout /t 12 /nobreak >nul 2>&1
tasklist /FI "IMAGENAME eq League of Legends.exe" 2>nul | find /i "League of Legends.exe" >nul
if errorlevel 1 (
  echo.
  echo   El juego no llego a arrancar.
  echo   The game did not start.
  echo.
  echo   Mira el ultimo log, ahi dice el motivo exacto:
  echo     %LOL_PATH%\Logs\GameLogs
  echo.
  echo   Si dice algo de la version, actualiza el cliente.
  echo   If it mentions the version, update the client.
  echo.
  pause
  exit /b 1
)

exit /b 0
"""


def generar_bat_spectate(server, key, match_id, region):
    """Escribe el `.bat` y devuelve su ruta.

    Se le pasa el servidor de espectadores de la región, la clave de cifrado de
    **esa** partida (`observers.encryptionKey`, que es distinta de la de los
    metadatos), el identificador y la región.

    `pista` es la ruta detectada **aquí**. En Render siempre estará vacía, y no
    pasa nada: el `.bat` busca por su cuenta cuando se ejecuta en el PC.
    """
    pista = ruta_del_cliente() or ""

    contenido = _PLANTILLA.format(
        server=server,
        key=key,
        match_id=match_id,
        region=region,
        pista=pista,
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bat", mode="w",
                                     encoding="utf-8", newline="\r\n") as f:
        f.write(contenido)
        return f.name

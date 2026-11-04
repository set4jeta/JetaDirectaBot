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

Vanguard: el juego solo lo abre el cliente
------------------------------------------
Lanzar `League of Legends.exe` a mano **ya no funciona**, y no es cosa del
`.bat`. Medido el 04-11-2026 con el sandbox del agente **desactivado**, con el
usuario real y con las ACL del fichero normales (sin ninguna denegación):

* `League of Legends.exe`  → `CreateProcess` devuelve **acceso denegado (5)**.
* `LeagueCrashHandler64.exe`, en la misma carpeta → **acceso denegado (5)**.
* un `notepad.exe` **copiado a esa misma carpeta** → arranca sin problema.

No es la ruta ni los permisos del fichero: es el binario. Lo bloquea Vanguard
(`vgk`), que solo deja arrancar el juego al cliente. Por eso el `.bat` **no
intenta lanzarlo directamente**: pide al cliente que lo abra.

Cómo se le pide al cliente (esto es lo que costó)
-------------------------------------------------
El endpoint "oficial" `POST /lol-spectator/v1/spectate/launch` **no vale para
esto**: por dentro llama a `/lol-gameflow/v2/spectate/launch`, que resuelve la
partida contra el *shard* del cliente. Si el cliente está en `LA2` y la partida
es de `NA1`, contesta `404 NOT_FOUND`; con `puuid`+`spectatorKey`, `500`. Un
cliente **nunca** puede espectar una partida de otra plataforma por ahí.

El que sí vale es el lanzador de la función **Watch** del cliente:

    POST /lol-gameflow/v1/watch/launch
    ["spectator spectator.na1.lol.pvp.net:8080 <clave> <gameId> <PLATAFORMA>"]

El cuerpo es **un vector de argumentos**, no un objeto: con `{}` contesta
«Couldn't assign value to 'args' of type vector». Con el array, **204** y el
cliente arranca el juego él mismo —con sus propios argumentos (`-Region=…`,
`-PlatformID=…`, `-Locale=…`)—, así que Vanguard lo autoriza. Y **funciona
entre plataformas**: el 04-11-2026 se abrió así una partida de `NA1` desde un
cliente `LA2` (el log del juego lo confirma: `Starting Multiplayer Session:
GridSpectator GameID(5673587648) ServerURL(spectator.na1.lol.pvp.net:8080)`).

Consecuencia práctica: **el cliente de LoL tiene que estar abierto**. Sin
cliente no hay partida, y el `.bat` lo dice en vez de intentar lo imposible.

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

:: ------------------------------------------------------------------
:: 1) Dos partidas a la vez no caben: si ya hay una, esto no haria nada.
:: ------------------------------------------------------------------
tasklist /FI "IMAGENAME eq League of Legends.exe" /NH 2>nul | findstr /I /C:"League of Legends.exe" >nul
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

:: ------------------------------------------------------------------
:: 2) El puerto y la contrasena de la API del cliente estan en
::    `lockfile`, que el cliente reescribe al arrancar y borra al
::    cerrarse. Si no esta, el cliente no esta abierto.
:: ------------------------------------------------------------------
set "LOCK=%LOL_PATH%\lockfile"
set "LCU_PUERTO="
if exist "%LOCK%" for /f "usebackq tokens=2,3,4 delims=:" %%A in ("%LOCK%") do (
  set "LCU_PID=%%A"
  set "LCU_PUERTO=%%B"
  set "LCU_CLAVE=%%C"
)
if defined LCU_PUERTO (
  rem El lockfile sobrevive a un cierre sucio: hay que mirar si el pid vive.
  tasklist /FI "PID eq %LCU_PID%" /NH 2>nul | findstr /I /C:"%LCU_PID%" >nul
  if errorlevel 1 set "LCU_PUERTO="
)
if not defined LCU_PUERTO goto :sin_cliente
where curl >nul 2>&1
if errorlevel 1 goto :sin_curl

:: ------------------------------------------------------------------
:: 3) El servidor de espectadores, si se puede comprobar. Solo avisa.
:: ------------------------------------------------------------------
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

:: ------------------------------------------------------------------
:: 4) Que la abra el CLIENTE.
::
::    Es el unico camino. Vanguard solo deja arrancar el juego al
::    cliente: `League of Legends.exe` lanzado desde fuera contesta
::    acceso denegado (error 5), y tambien `LeagueCrashHandler64.exe`,
::    mientras que un notepad copiado a esa carpeta arranca sin
::    problema. No es la ruta ni los permisos: es el binario.
::
::    Se usa el lanzador de la funcion Watch del cliente, que recibe
::    los argumentos del juego tal cual. El endpoint
::    /lol-spectator/v1/spectate/launch NO vale: resuelve la partida
::    contra el shard del cliente y una partida de otra plataforma le
::    contesta 404.
::
::    El cuerpo es un vector de argumentos, no un objeto. Por eso el
::    JSON va a un fichero temporal: escribirlo con -d entre comillas
::    dentro de un .bat es pedirle perlas a cmd.
:: ------------------------------------------------------------------
echo.
echo   El cliente esta abierto: se le pide a el que abra la partida...
echo   The client is open: asking it to open the game...
echo.

set "CUERPO=%TEMP%\lolprotrackr_espectar.json"
set "LCU_RESP=%TEMP%\lolprotrackr_espectar.txt"
> "%CUERPO%" echo ["spectator %SERVER% %KEY% %MATCH_ID% %REGION%"]
curl -k -s -o nul -w "%%{{http_code}}" --max-time 25 -u "riot:!LCU_CLAVE!" -X POST -H "Content-Type: application/json" --data-binary "@%CUERPO%" "https://127.0.0.1:!LCU_PUERTO!/lol-gameflow/v1/watch/launch" > "%LCU_RESP%" 2>nul
set "LCU_CODIGO="
set /p LCU_CODIGO=<"%LCU_RESP%"
if "!LCU_CODIGO!"=="200" goto :abierta
if "!LCU_CODIGO!"=="204" goto :abierta
goto :cliente_rechazo


:sin_cliente
echo.
echo   El cliente de League of Legends no esta abierto.
echo   The League of Legends client is not open.
echo.
echo   El juego ya no se puede abrir desde fuera: Vanguard solo deja
echo   que lo abra el cliente. Abre el cliente, espera a que cargue y
echo   vuelve a ejecutar este archivo.
echo.
echo   The game cannot be opened from outside: only the client may
echo   launch it. Open the client, wait for it to load and run this
echo   file again.
echo.
pause
exit /b 1


:sin_curl
echo.
echo   No se encontro curl en este PC.
echo   curl was not found on this PC.
echo.
echo   Viene con Windows 10 y 11. Si falta, actualiza Windows.
echo   It ships with Windows 10 and 11. If it is missing, update Windows.
echo.
pause
exit /b 1


:cliente_rechazo
echo.
echo   El cliente no abrio la partida (HTTP !LCU_CODIGO!).
echo   The client did not open the game (HTTP !LCU_CODIGO!).
echo.
echo   Lo mas habitual:
echo     - el cliente esta en la pantalla de entrar
echo     - la partida ya termino; los avisos llevan hasta 2 min de retraso
echo     - el cliente se esta actualizando
echo.
echo   Vuelve a ejecutar este archivo cuando el cliente este en el menu.
echo   Run this file again when the client is at the main menu.
echo.
pause
exit /b 1



:abierta
echo.
echo   La partida se esta abriendo.
echo   The game is opening.
echo.
echo   Tarda unos segundos, y luego aplica el retardo del espectador:
echo   al principio se ve la carga y nada mas. Es normal.
echo.
echo   It takes a few seconds, then the spectator delay applies: at first
echo   you only see the loading screen. That is expected.
echo.
timeout /t 10 /nobreak >nul 2>&1
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

#utils/spectate_bat.py
"""El `.bat` que abre la partida de un pro en el cliente de League of Legends.

Dos cosas cambiaron el 30-09-2026, y las dos por evidencia medida esa noche:

1. **Ya no para Vanguard.** Durante toda esa noche se abrieron partidas con
   `vgtray.exe` corriendo y **funcionaron**: el cliente arranca igual. Parar
   Vanguard era lo único que obligaba a ejecutar el `.bat` **como
   administrador**, así que quitarlo convierte «clic derecho → ejecutar como
   administrador» en un doble clic. Lo que parecía un problema de Vanguard era en
   realidad el lanzamiento desde bash, que pierde las comillas vacías de `start`
   y no arranca nada, sin dar error.

2. **La ruta del cliente se detecta, no se escribe a mano.** Estaba fijada a
   `C:\\Riot Games\\League of Legends`, que es la ruta del instalador por defecto
   pero **no la de todo el mundo**: en el PC del dueño está en `D:`. Y un `.bat`
   con la ruta equivocada no dice nada útil — se abre una consola, no encuentra el
   ejecutable y se cierra antes de que dé tiempo a leer nada.

Si algún día hay que volver a parar Vanguard, el motivo tendrá que ser uno nuevo:
el que había (que el cliente no arrancaba) era falso.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

#: Dónde suele estar el cliente. Se prueban todas las letras de unidad porque no
#: hay forma de saber en cuál lo instaló cada uno, y el registro de Windows **no**
#: siempre tiene la clave de Riot: en el PC del dueño no está.
SUBCARPETAS = (
    r"Riot Games\League of Legends",
    r"Program Files\Riot Games\League of Legends",
    r"Program Files (x86)\Riot Games\League of Legends",
)

#: Variable de entorno para forzar la ruta, si alguien tiene una instalación rara.
VARIABLE = "LOL_PATH"


def ruta_del_cliente() -> str | None:
    """La carpeta de instalación del cliente, o `None` si no aparece.

    Se busca, en este orden: la variable de entorno `LOL_PATH`, las rutas
    habituales en cada letra de unidad, y el registro de Windows. Lo primero es
    lo que permite arreglarlo sin tocar código cuando la detección falle.
    """
    de_entorno = os.environ.get(VARIABLE)
    if de_entorno and Path(de_entorno, "Game", "League of Legends.exe").is_file():
        return de_entorno

    for letra in "CDEFGHIJK":
        for sub in SUBCARPETAS:
            candidata = Path(f"{letra}:\\") / sub
            if (candidata / "Game" / "League of Legends.exe").is_file():
                return str(candidata)

    # El registro, por si está y las rutas habituales no.
    try:
        import winreg

        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\Riot Games, Inc\League of Legends",
                        r"SOFTWARE\WOW6432Node\Riot Games, Inc\League of Legends"):
                try:
                    with winreg.OpenKey(raiz, sub) as clave:
                        valor, _ = winreg.QueryValueEx(clave, "Location")
                        if Path(valor, "Game", "League of Legends.exe").is_file():
                            return valor
                except OSError:
                    continue
    except ImportError:
        pass

    return None


def generar_bat_spectate(server, key, match_id, region):
    """Escribe el `.bat` y devuelve su ruta.

    Se le pasa el servidor de espectadores de la región, la clave de cifrado de
    **esa** partida (`observers.encryptionKey`, que es distinta de la de los
    metadatos), el identificador y la región.
    """
    ruta = ruta_del_cliente()
    if ruta:
        arranque = f'set "LOL_PATH={ruta}"'
        comprobacion = ""
    else:
        # Sin ruta detectada se avisa **antes** de intentar nada: el fallo de
        # antes era abrir una consola que se cerraba sola, sin decir por qué.
        arranque = 'set "LOL_PATH="'
        comprobacion = f"""
echo League of Legends no encontrado / not found.
echo.
echo Edita la linea de LOL_PATH en este fichero con la ruta correcta.
echo Set the path by hand on the LOL_PATH line of this file.
echo.
echo Tambien vale la variable de entorno {VARIABLE}.
echo The {VARIABLE} environment variable works too.
pause
exit /b 1
"""

    contenido = f"""@echo off
setlocal enabledelayedexpansion
title League of Legends - spectate

:: Abre la partida {match_id} de {region} en el cliente de League of Legends.
:: Lo genera el bot; la clave es de esta partida y cambia cada vez.
::
:: No para Vanguard ni pide permisos de administrador: no hace falta. El cliente
:: arranca perfectamente con Vanguard en marcha.

{arranque}
{comprobacion}
set "GAME_DIR=%LOL_PATH%\\Game"
set "EXE_PATH=%GAME_DIR%\\League of Legends.exe"

if not exist "%EXE_PATH%" (
  echo League of Legends no encontrado en / not found at:
  echo   %EXE_PATH%
  echo.
  echo Edita la linea de LOL_PATH en este fichero.
  echo Edit the LOL_PATH line of this file.
  pause
  exit /b 1
)

set "SERVER={server}"
set "KEY={key}"
set "MATCH_ID={match_id}"
set "REGION={region}"

cd /d "%GAME_DIR%"
start "" "%EXE_PATH%" "spectator %SERVER% %KEY% %MATCH_ID% %REGION%" "-UseRads" "-GameBaseDir=.."

:: La partida tarda en cargar y el aviso del bot ya lo explica. Esta ventana se
:: puede cerrar: el cliente sigue abierto.
exit /b 0
"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bat", mode="w",
                                     encoding="utf-8", newline="\r\n") as f:
        f.write(contenido)
        return f.name

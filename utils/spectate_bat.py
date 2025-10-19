#utils/spectate_bat.py
import tempfile

def generar_bat_spectate(server, key, match_id, region):
    bat_content = f"""@echo off
setlocal enabledelayedexpansion

:: 1. Detener Vanguard
echo Deteniendo Vanguard...
net stop vgc >nul 2>&1
net stop vgk >nul 2>&1
taskkill /IM vgtray.exe /F >nul 2>&1

:: 2. Configuración EXACTA para tu partida
set "SERVER={server}"
set "KEY={key}"
set "MATCH_ID={match_id}"
set "REGION={region}"

:: 3. Ruta CORREGIDA del LOL (cambia si es diferente en tu PC)
set "LOL_PATH=C:\\Riot Games\\League of Legends"
set "GAME_DIR=%LOL_PATH%\\Game"
set "EXE_PATH=%GAME_DIR%\\League of Legends.exe"

:: 4. Comando de espectador (ASÍ lo hace OP.GG)
echo Iniciando modo espectador...
cd /d "%GAME_DIR%"
start "" "%EXE_PATH%" "spectator %SERVER% %KEY% %MATCH_ID% %REGION%" "-UseRads" "-GameBaseDir=.."

:: 5. Reiniciar Vanguard después
echo Esperando 15 segundos...
timeout /t 15 >nul

echo Reiniciando Vanguard...
net start vgc >nul 2>&1
net start vgk >nul 2>&1
if exist "C:\\Program Files\\Riot Vanguard\\vgtray.exe" (
    start "" "C:\\Program Files\\Riot Vanguard\\vgtray.exe"
)

echo Proceso completado. Verifica el cliente de League.
pause
"""
    # Guarda el archivo en un temporal
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bat", mode="w", encoding="utf-8") as f:
        f.write(bat_content)
        return f.name
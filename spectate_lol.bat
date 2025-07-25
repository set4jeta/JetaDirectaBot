@echo off
setlocal enabledelayedexpansion

:: 1. Detener Vanguard
echo Deteniendo Vanguard...
net stop vgc >nul 2>&1
net stop vgk >nul 2>&1
taskkill /IM vgtray.exe /F >nul 2>&1

:: 2. Configuración EXACTA para tu partida
set "SERVER=spectator.na1.lol.pvp.net:8080"
set "KEY=ihe032dBCD5Qw4F9PQbdy02FPyzjz72O"
set "MATCH_ID=5314428655"
set "REGION=NA1"

:: 3. Ruta CORREGIDA del LOL (cambia si es diferente en tu PC)
set "LOL_PATH=C:\Riot Games\League of Legends"
set "GAME_DIR=%LOL_PATH%\Game"
set "EXE_PATH=%GAME_DIR%\League of Legends.exe"

:: 4. Comando de espectador 
echo Iniciando modo espectador...
cd /d "%GAME_DIR%"
start "" "%EXE_PATH%" "spectator %SERVER% %KEY% %MATCH_ID% %REGION%" "-UseRads" "-GameBaseDir=.."

:: 5. Reiniciar Vanguard después
echo Esperando 15 segundos...
timeout /t 15 >nul

echo Reiniciando Vanguard...
net start vgc >nul 2>&1
net start vgk >nul 2>&1
if exist "C:\Program Files\Riot Vanguard\vgtray.exe" (
    start "" "C:\Program Files\Riot Vanguard\vgtray.exe"
)

echo Proceso completado. Verifica el cliente de League.
pause
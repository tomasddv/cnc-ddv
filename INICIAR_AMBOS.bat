@echo off
setlocal
cd /d "%~dp0"
title CNC DDV - ABRIR DOS TABLEROS
if not exist "CNC_DDV_LOCAL\app.py" goto error
if not exist "CNC_Promotores_DDV\app.py" goto error
if not exist "datos_compartidos" mkdir "datos_compartidos"
echo.
echo  INICIANDO LOS DOS TABLEROS CNC DDV
echo ===========================================
echo  Principal:  http://localhost:8515
echo  Promotores: http://localhost:8520
echo.
echo  Cada uno se abrira en su propia ventana.
echo  NO cierres esas dos ventanas mientras trabajes.
echo.
start "Tablero CNC DDV" "%~dp0CNC_DDV_LOCAL\INICIAR_CNC_LOCAL.bat"
start "Relevamiento promotores DDV" "%~dp0CNC_Promotores_DDV\INICIAR_PROMOTORES_LOCAL.bat"
echo Listo. Revisa las ventanas de cada aplicacion.
pause
exit /b 0
:error
echo ERROR: No estan las dos carpetas. Extrae el ZIP completo.
pause
exit /b 1

@echo off
setlocal EnableExtensions
title CNC DDV - SUPERVISORES Y LICENCIA CZA - 05-11-2026
cd /d "%~dp0"
set "CNC_RELEVAMIENTOS_DB=%~dp0..\datos_compartidos\relevamientos.sqlite"
set "LOG=%~dp0diagnostico_inicio.txt"
set "CNC_PORT=8515"

> "%LOG%" echo CNC DDV - Diagnostico de inicio
>> "%LOG%" echo Fecha: %date% %time%
>> "%LOG%" echo Carpeta: %CD%
echo.
echo =====================================================
echo    DDV - CNC - SUPERVISORES Y LICENCIA CZA
echo =====================================================
echo.
echo La ventana quedara abierta. Si algo falla,
echo lee el error o envia diagnostico_inicio.txt
echo.
if not exist "app.py" goto error_zip
if not exist "data\clientes.csv.gz" goto error_datos
if not exist "data\ventas_resumen.csv.gz" goto error_datos
if not exist "data\force_respuestas.csv.gz" goto error_datos

echo [1/4] Comprobando Python...
set "BASEPY="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >> "%LOG%" 2>&1
    if not errorlevel 1 set "BASEPY=py -3"
)
if defined BASEPY goto python_ok
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >> "%LOG%" 2>&1
    if not errorlevel 1 set "BASEPY=python"
)
if not defined BASEPY goto error_python
:python_ok
%BASEPY% --version
%BASEPY% --version >> "%LOG%" 2>&1

if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Creando entorno virtual...
    %BASEPY% -m venv ".venv" >> "%LOG%" 2>&1
    if errorlevel 1 goto error_venv
)
if not exist ".venv\Scripts\python.exe" goto error_venv

echo [3/4] Verificando dependencias...
".venv\Scripts\python.exe" -c "import streamlit, pandas, sqlalchemy" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo Instalando Streamlit y pandas. Debes tener Internet.
    echo Los detalles se guardan en diagnostico_inicio.txt
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --prefer-binary -r "requirements-local.txt" >> "%LOG%" 2>&1
    if errorlevel 1 goto error_pip
)
".venv\Scripts\python.exe" -c "import streamlit, pandas, sqlalchemy" >> "%LOG%" 2>&1
if errorlevel 1 goto error_pip

echo Comprobando si el puerto 8515 esta libre...
powershell -NoProfile -Command "$l=$null;try{$l=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,8515);$l.Start();$l.Stop();exit 0}catch{if($l){$l.Stop()};exit 1}" >nul 2>&1
if errorlevel 1 (
    echo Puerto 8515 ocupado: se usara 8516.
    set "CNC_PORT=8516"
    powershell -NoProfile -Command "$l=$null;try{$l=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,8516);$l.Start();$l.Stop();exit 0}catch{if($l){$l.Stop()};exit 1}" >nul 2>&1
    if errorlevel 1 goto error_puerto
)

echo [4/4] Iniciando servidor en http://localhost:%CNC_PORT%
echo NO cierres esta ventana mientras uses el tablero.
echo El navegador se abrira solo CUANDO el servidor este listo.
echo.
set "CNC_LOCAL=1"
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ABRIR_NAVEGADOR_CNC.ps1" -Port %CNC_PORT%
".venv\Scripts\python.exe" -m streamlit run "app.py" --server.address=127.0.0.1 --server.port=%CNC_PORT% --server.headless=true >> "%LOG%" 2>&1
echo.
echo El servidor se detuvo. Revisa diagnostico_inicio.txt.
type "%LOG%"
goto salir

:error_zip
echo ERROR: Abriste el BAT dentro del ZIP o faltan archivos.
echo Primero: click derecho al ZIP, Extraer todo. Luego abre
echo la carpeta CNC_DDV_LOCAL y ejecuta el BAT de ahi.
>> "%LOG%" echo ERROR: falta app.py; no se extrajo todo el ZIP.
goto salir
:error_datos
echo ERROR: Faltan los datos de la carpeta data.
echo Vuelve a extraer el ZIP completo, sin mover archivos sueltos.
>> "%LOG%" echo ERROR: no estan los archivos de datos esperados.
goto salir
:error_python
echo ERROR: No se encontro Python 3.10 o superior.
echo Instala Python desde https://www.python.org/downloads/
echo Al instalar, marca la opcion "Add python.exe to PATH".
>> "%LOG%" echo ERROR: Python no encontrado o version anterior a 3.10.
goto salir
:error_venv
echo ERROR: No fue posible crear el entorno de Python.
echo Revisa diagnostico_inicio.txt.
>> "%LOG%" echo ERROR: fallo la creacion del entorno virtual.
goto salir
:error_pip
echo ERROR: La instalacion de Streamlit o pandas fallo.
echo Comprueba Internet. Mira diagnostico_inicio.txt.
>> "%LOG%" echo ERROR: fallaron las dependencias.
goto salir
:error_puerto
echo ERROR: Puertos 8515 y 8516 ocupados.
echo Cierra otros tableros Streamlit e intenta nuevamente.
>> "%LOG%" echo ERROR: 8515 y 8516 ocupados.
goto salir
:salir
echo.
echo IMPORTANTE: Si sigue sin abrir, enviame diagnostico_inicio.txt.
pause

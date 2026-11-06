@echo off
setlocal
cd /d "%~dp0"
set "CNC_RELEVAMIENTOS_DB=%~dp0..\datos_compartidos\relevamientos.sqlite"
set "LOCAL_DEMO=1"
set "DATABASE_URL="
echo ==============================================
echo   CNC DDV - RELEVAMIENTO PARA PROMOTORES
 echo ==============================================
where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo No se encontro Python. Instalar Python 3.11 o superior.
    pause
    exit /b 1
  )
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo Preparando entorno virtual...
  %PY% -m venv .venv
  if errorlevel 1 (echo Error creando el entorno.& pause& exit /b 1)
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip show streamlit >nul 2>&1
if errorlevel 1 (
   echo Instalando componentes la primera vez...
   "%VPY%" -m pip install -r requirements.txt
   if errorlevel 1 (echo Error instalando paquetes.& pause& exit /b 1)
)
echo.
echo Abri en tu navegador: http://localhost:8520
 echo Si el navegador no abre solo, copia esa direccion.
echo Para cerrar la app, cierra esta ventana.
start "" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ABRIR_CUANDO_LISTO.ps1" -Port 8520
"%VPY%" -m streamlit run app.py --server.port 8520 --server.headless true
pause

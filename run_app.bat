@echo off
:: Ir al directorio donde está el script .bat
cd /d "%~dp0"

echo [1/3] Verificando entorno virtual...
if not exist "venv" (
    echo [AVISO] No se encontró la carpeta venv. 
    echo Creando entorno virtual con Python...
    python -m venv venv
    
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual automáticamente. 
        echo Asegúrate de tener Python instalado y en tu variable PATH.
        pause
        exit /b
    )
    echo ✅ Entorno virtual creado.
)

echo [2/3] Instalando / Actualizando dependencias...
echo Instalar dependencias de requirements.txt...
.\venv\Scripts\python -m pip install --upgrade pip
.\venv\Scripts\pip install -r requirements.txt

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Error al instalar dependencias de requirements.txt.
    pause
    exit /b
)
echo [AVISO] Dependencias actualizadas.

echo [2.5/3] Limpiando procesos en puerto 8080...
powershell -Command "$p = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id $p.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo [3/3] Iniciando Servidor Web (FastAPI)...
start "" "http://localhost:8080"
.\venv\Scripts\python app_backend.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [AVISO] Hubo un problema al ejecutar la aplicación.
    pause
)

pause

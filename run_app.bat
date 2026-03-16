@echo off
:: Ir al directorio donde está el script .bat
cd /d "%~dp0"

echo [1/2] Verificando entorno virtual...
if not exist ".venv" (
    echo [ERROR] No se encuentra la carpeta .venv.
    echo Por favor, crea el entorno primero.
    pause
    exit /b
)

echo [2/2] Iniciando Streamlit...
:: Usamos python -m streamlit para evitar que el script se cierre
.\.venv\Scripts\python -m streamlit run app.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [AVISO] Hubo un problema al ejecutar la aplicación.
    pause
)

pause

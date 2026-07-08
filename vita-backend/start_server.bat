@echo off
echo ================================================================
echo  VITA Backend — Server Startup
echo ================================================================
echo.

echo [1/3] Detecting local IP and patching config.h files...
python ..\vita-esp32\find_server_ip.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: find_server_ip.py failed. Is Python installed?
    pause
    exit /b 1
)

echo [2/3] Running diagnostic check...
python diagnose.py
echo.

echo [3/3] Starting Uvicorn on 0.0.0.0:8000 (reachable from ESP32)...
echo       Press Ctrl+C to stop.
echo ================================================================
echo.

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause

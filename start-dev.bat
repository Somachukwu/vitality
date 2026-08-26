@echo off
title Vitality Local Development Launcher
echo ===================================================
echo           Starting Vitality Platform (Dev)
echo ===================================================
echo.

cd /d "%~dp0"

echo [1/2] Launching Backend API on http://localhost:8000...
if exist "vita-backend\.venv\Scripts\activate.bat" (
    start "Vita Backend API" cmd /k "cd /d vita-backend && call .venv\Scripts\activate && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
) else (
    start "Vita Backend API" cmd /k "cd /d vita-backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
)

echo [2/2] Launching Frontend Server on http://localhost:8080...
start "Vita Frontend Web" cmd /k "cd /d vita-frontend && python -m http.server 8080"

echo.
echo ===================================================
echo Vitality is running!
echo   * Frontend:    http://localhost:8080
echo   * Backend API: http://localhost:8000
echo   * API Docs:    http://localhost:8000/docs
echo ===================================================
echo.
pause

@echo off
echo Stopping any server on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo Starting Vitality backend...
cd /d "%~dp0"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause

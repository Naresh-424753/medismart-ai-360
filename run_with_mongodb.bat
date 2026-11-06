@echo off
REM Starts MongoDB, backend and frontend in separate windows.
start "MongoDB" "%~dp0start-mongo.bat"
timeout /t 5 >nul
start "MediSmart Backend" "%~dp0start-backend.bat"
start "MediSmart Frontend" "%~dp0start-frontend.bat"
echo Backend: http://localhost:8000   Frontend: http://localhost:5173

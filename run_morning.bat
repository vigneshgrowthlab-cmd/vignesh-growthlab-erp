@echo off
title Wholesale ERP - Morning Launcher
color 0B

echo ========================================================
echo   Wholesale ERP - Starting System Services
echo ========================================================
echo.

REM 1. Start MariaDB on Port 3307
echo [1/3] Starting MariaDB Server on port 3307...
start "MariaDB 12.3 (Port 3307)" cmd /c ""C:\Program Files\MariaDB 12.3\bin\mysqld.exe" --defaults-file="C:\Program Files\MariaDB 12.3\data\my.ini" --port=3307 --console"
timeout /t 4 /nobreak >nul

REM 2. Start FastAPI Backend
echo [2/3] Starting Backend API Server (Port 8000)...
start "Wholesale ERP - Backend (:8000)" cmd /k "cd /d D:\BOOMERM\GTF-main\backend && call .venv\Scripts\activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
timeout /t 4 /nobreak >nul

REM 3. Start React Frontend
echo [3/3] Starting Frontend Vite Server (Port 5173)...
start "Wholesale ERP - Frontend (:5173)" cmd /k "cd /d D:\BOOMERM\GTF-main\frontend && npm run dev -- --host 0.0.0.0 --port 5173"
timeout /t 3 /nobreak >nul

REM 4. Open Browser
echo Opening Browser at http://localhost:5173 ...
start "" "http://localhost:5173"

echo.
echo ========================================================
echo   Wholesale ERP is Online!
echo   Frontend: http://localhost:5173
echo   API Docs: http://localhost:8000/api/docs
echo   Login:    admin / Admin@1234
echo ========================================================
pause

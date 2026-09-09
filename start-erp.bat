@echo off
title Wholesale ERP Launcher
color 0A

echo.
echo  ============================================
echo   Wholesale ERP - Starting Application
echo  ============================================
echo.

REM ── Find MariaDB bin path ─────────────────────────────────────
set MARIADB_BIN=
for /d %%i in ("C:\Program Files\MariaDB*") do (
    if exist "%%i\bin\mysql.exe" set MARIADB_BIN=%%i\bin
)

if "%MARIADB_BIN%"=="" (
    echo  ERROR: MariaDB installation not found in C:\Program Files\
    echo  Please check your MariaDB installation.
    pause
    exit /b 1
)

echo  Found MariaDB at: %MARIADB_BIN%
echo.

REM ── Start MariaDB service ─────────────────────────────────────
echo [1/4] Starting MariaDB service...
net start MariaDB >nul 2>&1
timeout /t 3 /nobreak >nul
echo  MariaDB service started.
echo.

REM ── Check DB connection ───────────────────────────────────────
echo [2/4] Checking database connection...
"%MARIADB_BIN%\mysql.exe" -u erp_user -perp_password -h 127.0.0.1 wholesale_erp -e "SELECT 1;" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Cannot connect to database.
    echo.
    echo  Please open a new Command Prompt as Administrator and run:
    echo.
    echo  "%MARIADB_BIN%\mysql.exe" -u root -p
    echo.
    echo  Then paste these SQL commands:
    echo  CREATE DATABASE IF NOT EXISTS wholesale_erp;
    echo  CREATE USER IF NOT EXISTS 'erp_user'@'localhost' IDENTIFIED BY 'erp_password';
    echo  CREATE USER IF NOT EXISTS 'erp_user'@'127.0.0.1' IDENTIFIED BY 'erp_password';
    echo  GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'localhost';
    echo  GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'127.0.0.1';
    echo  FLUSH PRIVILEGES;
    echo.
    pause
    exit /b 1
)
echo  Database connected successfully.
echo.

REM ── Start Backend ─────────────────────────────────────────────
echo [3/4] Starting Backend API server...
start "Wholesale ERP - Backend" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate && echo. && echo  Backend: http://localhost:8000 && echo  API Docs: http://localhost:8000/api/docs && echo. && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo  Waiting for backend to initialize...
timeout /t 5 /nobreak >nul

REM ── Start Frontend ────────────────────────────────────────────
echo [4/4] Starting Frontend...
start "Wholesale ERP - Frontend" cmd /k "cd /d %~dp0frontend && echo. && echo  Frontend: http://localhost:5173 && echo. && npm run dev"

echo  Waiting for frontend to initialize...
timeout /t 6 /nobreak >nul

REM ── Open Browser ──────────────────────────────────────────────
echo  Opening browser...
start "" "http://localhost:5173"

echo.
echo  ============================================
echo   ERP is running!
echo  ============================================
echo.
echo   App:      http://localhost:5173
echo   API Docs: http://localhost:8000/api/docs
echo.
echo   Login:    admin / Admin@1234
echo.
echo   To stop: Close the Backend and Frontend windows
echo  ============================================
echo.
pause
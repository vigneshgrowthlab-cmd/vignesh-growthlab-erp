@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

echo ============================================================
echo  Wholesale ERP - Windows Setup Script
echo ============================================================
echo.

:: ── Step 1: Check Python ────────────────────────────────────
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo [ERROR] Python not found. Download from https://python.org ^(3.11+^)
    pause & exit /b 1
)
echo [OK] Python found

:: ── Step 2: Check Node ──────────────────────────────────────
node --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo [ERROR] Node.js not found. Download from https://nodejs.org ^(18+^)
    pause & exit /b 1
)
echo [OK] Node.js found

:: ── Step 3: MariaDB Instructions ────────────────────────────
echo.
echo ── MariaDB Setup ─────────────────────────────────────────
echo  1. Download MariaDB: https://mariadb.org/download/
echo     Choose: Windows x86_64 MSI Installer
echo  2. During install: set root password, enable as service
echo  3. After install, open Command Prompt and run:
echo.
echo     mysql -u root -p
echo     CREATE DATABASE wholesale_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
echo     CREATE USER 'erp_user'@'localhost' IDENTIFIED BY 'erp_password';
echo     GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'localhost';
echo     FLUSH PRIVILEGES;
echo     EXIT;
echo.
set /p DBREADY="Have you completed MariaDB setup? (y/n): "
IF /I NOT "%DBREADY%"=="y" (
    echo Please complete MariaDB setup first, then re-run this script.
    pause & exit /b 0
)

:: ── Step 4: Backend setup ────────────────────────────────────
echo.
echo ── Setting up backend ────────────────────────────────────
cd backend

IF NOT EXIST ".env" (
    copy .env.example .env
    echo [OK] .env created from .env.example
    echo [!!] Edit backend\.env with your DB credentials and secret key before continuing
    notepad .env
    set /p ENVDONE="Press Enter after editing .env to continue..."
) ELSE (
    echo [OK] .env already exists
)

IF NOT EXIST "venv" (
    echo Creating virtual environment...
    python -m venv venv
)
echo [OK] Virtual environment ready

call venv\Scripts\activate.bat
echo [OK] Virtual environment activated

echo Installing Python packages...
pip install -r requirements.txt --quiet
IF ERRORLEVEL 1 (
    echo [ERROR] pip install failed. Check your internet connection.
    pause & exit /b 1
)
echo [OK] Python packages installed

echo Running database migrations...
alembic upgrade head
IF ERRORLEVEL 1 (
    echo [ERROR] Migration failed. Check DB credentials in .env
    pause & exit /b 1
)
echo [OK] Database migrated

echo Seeding database with default data...
python seed.py
echo [OK] Database seeded

cd ..

:: ── Step 5: Frontend setup ───────────────────────────────────
echo.
echo ── Setting up frontend ───────────────────────────────────
cd frontend

IF NOT EXIST "package.json" (
    echo Initialising React project...
    call npm create vite@latest . -- --template react
)

echo Installing Node packages...
call npm install
IF ERRORLEVEL 1 (
    echo [ERROR] npm install failed.
    pause & exit /b 1
)
echo [OK] Node packages installed

IF NOT EXIST ".env" (
    echo VITE_API_URL=http://localhost:8000 > .env
    echo [OK] Frontend .env created
)

cd ..

:: ── Done ─────────────────────────────────────────────────────
echo.
echo ============================================================
echo  Setup complete! Start the application:
echo.
echo  Terminal 1 (Backend):
echo    cd backend
echo    venv\Scripts\activate
echo    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
echo.
echo  Terminal 2 (Frontend):
echo    cd frontend
echo    npm run dev
echo.
echo  Open browser: http://localhost:5173
echo  API docs:     http://localhost:8000/api/docs
echo  Login:        admin / Admin@1234
echo ============================================================
pause

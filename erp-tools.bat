@echo off
title Wholesale ERP - Tools
color 0A

:MENU
cls
echo.
echo  ============================================
echo   Wholesale ERP - Admin Tools
echo  ============================================
echo.
echo   1. Reset Database (drop and recreate all tables)
echo   2. Seed Default Data (admin user, warehouse, accounts)
echo   3. Reset User Password
echo   4. Reset Database + Seed (full fresh start)
echo   5. Start ERP Application
echo   6. Exit
echo.
echo  ============================================
echo.
set /p CHOICE="  Enter your choice (1-6): "

if "%CHOICE%"=="1" goto RESET_DB
if "%CHOICE%"=="2" goto SEED
if "%CHOICE%"=="3" goto RESET_PASSWORD
if "%CHOICE%"=="4" goto FULL_RESET
if "%CHOICE%"=="5" goto START_ERP
if "%CHOICE%"=="6" goto EXIT

echo.
echo  Invalid choice. Please enter 1 to 6.
timeout /t 2 /nobreak >nul
goto MENU


REM ── Option 1 — Reset Database ─────────────────────────────────
:RESET_DB
cls
echo.
echo  ============================================
echo   Reset Database
echo  ============================================
echo.
echo  WARNING: This will DROP all tables and recreate them.
echo  ALL DATA WILL BE LOST.
echo.
set /p CONFIRM="  Type YES to confirm: "
if /i not "%CONFIRM%"=="YES" (
    echo.
    echo  Cancelled.
    timeout /t 2 /nobreak >nul
    goto MENU
)
echo.
echo  Resetting database...
cd /d %~dp0backend
call venv\Scripts\activate
python reset_db.py
echo.
echo  Done.
echo.
pause
goto MENU


REM ── Option 2 — Seed Data ──────────────────────────────────────
:SEED
cls
echo.
echo  ============================================
echo   Seed Default Data
echo  ============================================
echo.
echo  This will create:
echo   - Admin user (admin / Admin@1234)
echo   - Main warehouse
echo   - Chart of accounts
echo   - Invoice sequences
echo.
cd /d %~dp0backend
call venv\Scripts\activate
python seed.py
echo.
pause
goto MENU


REM ── Option 3 — Reset Password ─────────────────────────────────
:RESET_PASSWORD
cls
echo.
echo  ============================================
echo   Reset User Password
echo  ============================================
echo.
cd /d %~dp0backend
call venv\Scripts\activate
python reset_password.py
echo.
goto MENU


REM ── Option 4 — Full Reset ─────────────────────────────────────
:FULL_RESET
cls
echo.
echo  ============================================
echo   Full Fresh Start
echo  ============================================
echo.
echo  WARNING: This will DROP all tables, recreate them,
echo  and seed default data. ALL DATA WILL BE LOST.
echo.
set /p CONFIRM="  Type YES to confirm: "
if /i not "%CONFIRM%"=="YES" (
    echo.
    echo  Cancelled.
    timeout /t 2 /nobreak >nul
    goto MENU
)
echo.
echo  Step 1 - Resetting database...
cd /d %~dp0backend
call venv\Scripts\activate
python reset_db.py
echo.
echo  Step 2 - Seeding default data...
python seed.py
echo.
echo  Full reset complete!
echo  Login with: admin / Admin@1234
echo.
pause
goto MENU


REM ── Option 5 — Start ERP ──────────────────────────────────────
:START_ERP
cls
echo.
echo  Starting ERP Application...
echo.
call %~dp0start-erp.bat
goto MENU


REM ── Exit ──────────────────────────────────────────────────────
:EXIT
cls
echo.
echo  Goodbye!
echo.
timeout /t 2 /nobreak >nul
exit
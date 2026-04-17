@echo off
setlocal

:: =====================================================
::  Hotel & Event Management App Updater
:: =====================================================

:: === CONFIG ===
set FRONTEND_PROJECT=C:\Users\KLOUNGE\Documents\HEMS-PROJECT\react-frontend
set BACKEND_PROJECT=C:\Users\KLOUNGE\Documents\HEMS-PROJECT\app
set INSTALL_DIR=C:\Program Files\Hotel and Event Management App
set POWERSHELL_EXE=C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe

echo "=== Hotel & Event Management App Updater ==="

:: === STEP 1: Build React with PowerShell (safe path) ===
echo Building React frontend with PowerShell...
"%POWERSHELL_EXE%" -ExecutionPolicy Bypass -NoProfile -Command ^
    "cd '%FRONTEND_PROJECT%'; npm install; npm run build"

if errorlevel 1 (
    echo [ERROR] Build failed. Aborting update.
    pause
    exit /b 1
)

:: === STEP 2: Remove old frontend build ===
if exist "%INSTALL_DIR%\react-frontend\build" (
    echo Removing old frontend build...
    rmdir /s /q "%INSTALL_DIR%\react-frontend\build"
)

:: === STEP 3: Copy new frontend build ===
echo Copying new frontend build...
xcopy /E /I /Y "%FRONTEND_PROJECT%\build" "%INSTALL_DIR%\react-frontend\build"

if errorlevel 1 (
    echo [ERROR] Frontend copy failed!
    pause
    exit /b 1
)

:: === STEP 4: Update backend files ===
echo Updating backend files...
xcopy /E /I /Y "%BACKEND_PROJECT%" "%INSTALL_DIR%\app"
xcopy /Y "C:\Users\KLOUNGE\Documents\HEMS-PROJECT\start.py" "%INSTALL_DIR%\start.py"

echo [OK] Update complete! Frontend + Backend updated successfully.
pause

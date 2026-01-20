@echo off
setlocal

REM ==============================================================
REM Manual Receiving ATC - DEBUG START
REM Runs with console visible so you can see errors.
REM ==============================================================

if not exist atc_env\Scripts\python.exe (
  echo [ERROR] Virtual env not found. Run "Step 1 - INSTALL.bat" first.
  pause
  exit /b 1
)

echo [INFO] Starting ATC in DEBUG mode...
call atc_env\Scripts\python.exe manual_receiving_atc.py

echo.
echo [INFO] ATC exited.
pause

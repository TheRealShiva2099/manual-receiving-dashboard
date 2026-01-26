@echo off
setlocal

REM ==============================================================
REM Manual Receiving ATC - Step 2 START (Silent)
REM Runs via VBScript so there’s no console window.
REM ==============================================================

if not exist atc_env\Scripts\python.exe (
  echo [ERROR] Virtual env not found. Run "Step 1 - INSTALL.bat" first.
  pause
  exit /b 1
)

cscript //nologo start_atc_hidden.vbs

REM No output by design.
exit /b 0

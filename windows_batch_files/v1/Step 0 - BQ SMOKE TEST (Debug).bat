@echo off
setlocal

REM ==============================================================
REM BigQuery CLI smoke test
REM Proves bq CLI can run a trivial query and shows which account
REM ==============================================================

if not exist atc_env\Scripts\python.exe (
  echo [ERROR] Virtual env not found. Run "Step 1 - INSTALL.bat" first.
  pause
  exit /b 1
)

echo [INFO] Running BigQuery smoke test...
call atc_env\Scripts\python.exe bq_smoke_test.py

echo.
pause

@echo off
setlocal enabledelayedexpansion

REM ==============================================================
REM Manual Receiving ATC - Step 1 INSTALL (Walmart-friendly)
REM - Logs everything to install.log
REM - Creates venv in .\atc_env using uv
REM - Installs deps from requirements_atc.txt using Walmart PyPI mirror
REM - Verifies bq CLI exists
REM ==============================================================

set "BASE_DIR=%~dp0"
set "LOGFILE=%BASE_DIR%install.log"
set "INDEX_URL=https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple"

> "%LOGFILE%" echo ==============================================================
>>"%LOGFILE%" echo INSTALL START %DATE% %TIME%
>>"%LOGFILE%" echo ==============================================================

call :main >>"%LOGFILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"

>>"%LOGFILE%" echo.
>>"%LOGFILE%" echo ==============================================================
>>"%LOGFILE%" echo INSTALL END %DATE% %TIME%  (exit=%EXITCODE%)
>>"%LOGFILE%" echo ==============================================================

echo.
echo [INFO] Install finished with exit=%EXITCODE%
echo [INFO] Log written to: %LOGFILE%
echo.
pause
exit /b %EXITCODE%

:main

echo.
echo [INIT] Manual Receiving ATC - INSTALL
echo.

echo [INFO] Checking for uv...
where uv
if errorlevel 1 (
  echo [ERROR] uv not found on PATH.
  echo You need uv available to install deps in this environment.
  echo.
  echo If your org doesn’t ship uv by default, we can fall back to pip+mirror.
  exit /b 1
)

echo [INFO] Checking requirements file...
if not exist "%BASE_DIR%requirements_atc.txt" (
  echo [ERROR] Missing requirements_atc.txt
  exit /b 1
)

echo [INFO] Creating virtual environment (uv venv) if needed...
if not exist "%BASE_DIR%atc_env\Scripts\python.exe" (
  uv venv "%BASE_DIR%atc_env"
  if errorlevel 1 (
    echo [ERROR] Failed to create venv via uv.
    exit /b 1
  )
) else (
  echo [INFO] venv already exists.
)

echo.
echo [INFO] Installing dependencies via uv + Walmart PyPI mirror...
set "HTTP_PROXY=http://sysproxy.wal-mart.com:8080"
set "HTTPS_PROXY=http://sysproxy.wal-mart.com:8080"

uv pip install --python "%BASE_DIR%atc_env\Scripts\python.exe" -r "%BASE_DIR%requirements_atc.txt" --index-url "%INDEX_URL%" --allow-insecure-host pypi.ci.artifacts.walmart.com
if errorlevel 1 (
  echo [ERROR] Dependency install failed.
  exit /b 1
)

echo.
echo [INFO] Smoke test: importing Flask + plyer...
"%BASE_DIR%atc_env\Scripts\python.exe" -c "import flask; import plyer; print('imports-ok')"
if errorlevel 1 (
  echo [ERROR] Import smoke test failed. Dependencies are not installed correctly.
  exit /b 1
)

echo.
echo [INFO] Checking for BigQuery CLI (bq)...
where bq
if errorlevel 1 (
  echo [ERROR] bq CLI not found.
  echo Install Google Cloud SDK and ensure bq is on PATH.
  exit /b 1
)

echo.
echo [OK] Installation complete!
echo Next: run "Step 2 - START ATC (Silent).bat"
exit /b 0

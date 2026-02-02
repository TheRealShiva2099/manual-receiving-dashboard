@echo off
setlocal

REM Start ATC and bind the dashboard server to all interfaces so other devices on the LAN can reach it.
REM Use: http://<your-ip>:5000/

cd /d "%~dp0"

set ATC_HOST=0.0.0.0
set ATC_PORT=5000

echo [INFO] Starting ATC in LAN HOST mode...
echo [INFO] Dashboard will be reachable at: http://YOUR-IP:%ATC_PORT%/
echo [INFO] Make sure Windows Firewall allows inbound TCP %ATC_PORT%.
echo.

call "%~dp0atc_env\Scripts\activate.bat"
python manual_receiving_atc.py

endlocal

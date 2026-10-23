@echo off
rem Double-click to start TownshipFix on Windows. Close this window to stop the app. (Run "git pull" first to update.)
title TownshipFix
cd /d "%~dp0"
echo.
echo  Checking what the app needs (the first time takes a few minutes)...
python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo  Could not install the requirements. Is Python installed and on PATH?
  pause
  exit /b 1
)
echo.
echo  Opening the resident app and the staff dashboard (PIN 1234) in your browser.
echo  Your browser will warn about the certificate: click Advanced, then Proceed.
echo  For your phone, use the "On a phone" address shown below, on the same Wi-Fi.
start "" /min cmd /c "timeout /t 5 /nobreak >nul && start https://localhost:8000/staff && start https://localhost:8000/"
python run.py --https
echo.
echo  The app has stopped.
pause

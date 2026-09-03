@echo off
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title AIComposer Telegram CLI bot
cd /d "%~dp0\.."

echo.
echo  Telegram CLI listener (manual remote control)
echo  Do NOT run this if run_telegram_client.bat is already open (409 conflict).
echo  Close this window to stop remote control.
echo.

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m cli bot %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cli bot %*
) else (
    python -m cli bot %*
)

set RC=%ERRORLEVEL%
if %RC%==3 exit /b 0
echo.
echo  Bot exited, code %RC%
pause
exit /b %RC%

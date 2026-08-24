@echo off
REM Hermes: run this file only. Always pops a visible listener unless one is live.
setlocal EnableExtensions
cd /d "%~dp0\.."
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -c "from utility.telegram_cli import cli_bot_already_running; raise SystemExit(0 if cli_bot_already_running() else 1)"
) else (
    python -c "from utility.telegram_cli import cli_bot_already_running; raise SystemExit(0 if cli_bot_already_running() else 1)"
)
if %ERRORLEVEL%==0 (
    echo listener already running
    exit /b 0
)
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0run_bot.bat' -WorkingDirectory '%~dp0\..' -WindowStyle Normal"
exit /b 0

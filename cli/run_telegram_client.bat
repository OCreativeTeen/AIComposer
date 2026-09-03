@echo off
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title AIComposer Hermes Telegram client
cd /d "%~dp0\.."

echo.
echo  Hermes Telegram client
echo  Runs the story-video pipeline on this PC.
echo  Pipeline: pick -> scn -> scnvs -> scnlm -> ... -> itc -> grv -> vc (auto scn if SCENE closed)
echo  Scene pick: reply 1/2/3... after scnvs then scnlm lists (this client polls; do NOT run run_bot).
echo  If nbif times out: Chrome stays open; run cli\run_telegram_client_resume.bat after manual check.
echo  Close this window to stop. Do not open run_bot.bat at the same time.
echo.

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m cli.telegram_bot_client --telegram-inbox %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cli.telegram_bot_client --telegram-inbox %*
) else (
    python -m cli.telegram_bot_client --telegram-inbox %*
)

set RC=%ERRORLEVEL%
echo.
echo  Client exited, code %RC%
pause
exit /b %RC%

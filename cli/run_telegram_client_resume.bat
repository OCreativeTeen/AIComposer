@echo off
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title AIComposer Hermes Telegram client — resume nbif
cd /d "%~dp0\.."

echo.
echo  Hermes Telegram client — RESUME nbif
echo  Finds nbif-timeout item, connects to OPEN Chrome (no kill/relaunch), downloads 3 covers.
echo  Then: cover pick 1/2/3 -^> auto scn if needed -^> grv
echo.

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m cli.telegram_bot_client --resume --once %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cli.telegram_bot_client --resume --once %*
) else (
    python -m cli.telegram_bot_client --resume --once %*
)

set RC=%ERRORLEVEL%
echo.
if %RC%==2 (
    echo  Resume exited: nbif still not ready — check NotebookLM and run this bat again.
) else if %RC%==0 (
    echo  Resume OK — pipeline continued past nbif.
) else (
    echo  Resume failed, code %RC%
)
pause
exit /b %RC%

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
echo  Pipeline: pick -^> scn -^> lm -^> gem -^> scnsave (was pst+save) -^> nbi ...
echo  Story pick: next = first pending, or auto pick 1 if queue has only in-progress/done.
echo  Cover pick: reply 1 / 2 / 3 in Telegram (client polls if run_bot is off).
echo  Close this window to stop.
echo.

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m cli.telegram_bot_client %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cli.telegram_bot_client %*
) else (
    python -m cli.telegram_bot_client %*
)

set RC=%ERRORLEVEL%
echo.
echo  Client exited, code %RC%
pause
exit /b %RC%

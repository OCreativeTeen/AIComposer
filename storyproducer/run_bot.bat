@echo off
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title StoryProducer bot (no GUI)
cd /d "%~dp0\.."

echo.
echo  StoryProducer Telegram 听筒（无 GUI）
echo  Do NOT run this together with cli\run_bot.bat or cli\run_telegram_client.bat
echo  (same TELEGRAM_CLI token = 409 conflict).
echo  Close this window to stop.
echo.

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m storyproducer bot %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m storyproducer bot %*
) else (
    python -m storyproducer bot %*
)

set RC=%ERRORLEVEL%
echo.
echo  Bot exited, code %RC%
pause
exit /b %RC%

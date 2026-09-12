@echo off
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title StoryProducer client (no GUI)
cd /d "%~dp0\.."

echo.
echo  StoryProducer 流水线（无 GUI）
echo  启动时 Telegram 选目标：1=仅场景  2=到封面  3=全程 clips
echo  断点续传：workflow.stage；封面生成中可跳过本条处理下一条。
echo  Do NOT run cli\run_bot.bat or cli\run_telegram_client.bat at the same time.
echo.

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m storyproducer client %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m storyproducer client %*
) else (
    python -m storyproducer client %*
)

set RC=%ERRORLEVEL%
echo.
echo  Client exited, code %RC%
pause
exit /b %RC%

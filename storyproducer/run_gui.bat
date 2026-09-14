@echo off

setlocal EnableExtensions

chcp 65001 >nul

set PYTHONIOENCODING=utf-8

set PYTHONUTF8=1

title StoryProducer GUI review (vc)

cd /d "%~dp0\.."



echo.

echo  StoryProducer GUI 审阅（run_client 之后）

echo  逐条打开 STORY，自动载入各场景 clip 审阅窗（等同 vc）。

echo  在窗口内裁剪/确认生成成片，可发 vp 发布。

echo  启动后 Telegram 回复 1/2/3 选故事；审阅完发 n；再选下一条（可重复）。

echo  Do NOT run cli\run_telegram_client.bat at the same time.

echo.



if exist "venv\Scripts\python.exe" (

    "venv\Scripts\python.exe" -m storyproducer gui %*

) else if exist ".venv\Scripts\python.exe" (

    ".venv\Scripts\python.exe" -m storyproducer gui %*

) else (

    python -m storyproducer gui %*

)



set RC=%ERRORLEVEL%

echo.

echo  GUI review exited, code %RC%

pause

exit /b %RC%


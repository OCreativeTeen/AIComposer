@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
rem 取下一条视频选择并打开摘要编辑（等同: python -m aiagent.pick_video_choice next --with-detail --json）
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m aiagent.pick_video_choice next --with-detail --json %*
    goto :after_run
)
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m aiagent.pick_video_choice next --with-detail --json %*
    goto :after_run
)
python -m aiagent.pick_video_choice next --with-detail --json %*

:after_run
exit /b %ERRORLEVEL%

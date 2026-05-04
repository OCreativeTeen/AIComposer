@echo off
setlocal EnableExtensions
cd /d "%~dp0"
rem 优先使用项目虚拟环境（需已安装依赖，含 matplotlib）
rem 创建示例: py -3.11 -m venv .venv
rem 然后: .venv\Scripts\python.exe -m pip install -r requirements.txt
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" GUI_wf.py %*
    goto :after_run
)
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" GUI_wf.py %*
    goto :after_run
)

:after_run
exit /b 0

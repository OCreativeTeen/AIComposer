@echo off
REM 夜间批量图像生成脚本
REM 用于Windows任务计划程序调度

echo ======================================
echo 夜间批量图像生成开始
echo 启动时间: %date% %time%
echo ======================================

REM 切换到脚本目录
cd /d "%~dp0"

REM 激活虚拟环境（如果使用）
if exist "venv\Scripts\activate.bat" (
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat
)

REM 检查批处理配置文件是否存在
if not exist "night_batch_config.json" (
    echo 错误: 找不到配置文件 night_batch_config.json
    echo 请先创建配置文件或运行: python run_image_generator.py --create-sample
    pause
    exit /b 1
)

REM 运行批量图像生成
echo 开始批量处理...
python run_image_generator.py --batch night_batch_config.json --log-level INFO

REM 检查退出码
if %errorlevel% equ 0 (
    echo ======================================
    echo 批量处理成功完成
    echo 完成时间: %date% %time%
    echo ======================================
) else (
    echo ======================================
    echo 批量处理出现错误，错误码: %errorlevel%
    echo 完成时间: %date% %time%
    echo ======================================
)

REM 如果在交互模式下运行，暂停以查看结果
if /I "%1"=="interactive" pause

exit /b %errorlevel% 
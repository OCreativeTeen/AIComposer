@echo off
REM =====================================================
REM YouTube Cookies 导出工具
REM =====================================================
echo.
echo ========================================
echo YouTube Cookies 导出工具
echo ========================================
echo.
echo 请选择导出方法:
echo.
echo 1. 从 Chrome 浏览器导出
echo 2. 从 Edge 浏览器导出
echo 3. 从 Firefox 浏览器导出
echo 4. 手动下载 cookies (推荐)
echo 5. 退出
echo.
set /p choice=请输入选项 (1-5): 

if "%choice%"=="1" goto chrome
if "%choice%"=="2" goto edge
if "%choice%"=="3" goto firefox
if "%choice%"=="4" goto manual
if "%choice%"=="5" goto end
goto invalid

:chrome
echo.
echo ⚠️ 重要: 请先完全关闭所有 Chrome 浏览器窗口！
echo.
pause
echo.
echo 正在从 Chrome 导出 cookies...
yt-dlp --cookies-from-browser chrome --cookies www.youtube.com_cookies.txt "https://www.youtube.com"
if errorlevel 1 (
    echo.
    echo ❌ 导出失败！
    echo.
    echo 可能的原因:
    echo 1. Chrome 浏览器未完全关闭
    echo 2. Chrome 未登录 YouTube
    echo 3. 权限问题 ^(尝试以管理员身份运行^)
    echo.
    echo 建议: 使用方法 4 ^(手动下载^)
    pause
    goto end
)
goto success

:edge
echo.
echo ⚠️ 重要: 请先完全关闭所有 Edge 浏览器窗口！
echo.
pause
echo.
echo 正在从 Edge 导出 cookies...
yt-dlp --cookies-from-browser edge --cookies www.youtube.com_cookies.txt "https://www.youtube.com"
if errorlevel 1 (
    echo.
    echo ❌ 导出失败！
    echo 建议: 使用方法 4 ^(手动下载^)
    pause
    goto end
)
goto success

:firefox
echo.
echo ⚠️ 重要: 请先完全关闭所有 Firefox 浏览器窗口！
echo.
pause
echo.
echo 正在从 Firefox 导出 cookies...
yt-dlp --cookies-from-browser firefox --cookies www.youtube.com_cookies.txt "https://www.youtube.com"
if errorlevel 1 (
    echo.
    echo ❌ 导出失败！
    echo 建议: 使用方法 4 ^(手动下载^)
    pause
    goto end
)
goto success

:manual
echo.
echo ========================================
echo 手动导出 Cookies 步骤 ^(推荐^)
echo ========================================
echo.
echo 1. 安装浏览器扩展:
echo    Chrome/Edge: 搜索 "Get cookies.txt LOCALLY"
echo    链接: https://chrome.google.com/webstore/search/get%%20cookies.txt
echo.
echo 2. 访问 YouTube 并登录:
echo    https://www.youtube.com
echo.
echo 3. 点击扩展图标，选择导出 cookies
echo.
echo 4. 保存文件为: www.youtube.com_cookies.txt
echo.
echo 5. 将文件放入项目文件夹
echo.
echo ========================================
echo.
pause
goto end

:success
echo.
echo ========================================
echo ✅ Cookies 导出成功！
echo ========================================
echo.
echo 文件位置: %CD%\www.youtube.com_cookies.txt
echo.
echo 现在可以重新运行程序了。
echo ========================================
echo.
pause
goto end

:invalid
echo.
echo ❌ 无效的选项！
pause
goto end

:end

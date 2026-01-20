# =====================================================
# YouTube Cookies 导出工具 (PowerShell)
# =====================================================

Write-Host ""
Write-Host "========================================"
Write-Host "YouTube Cookies 导出工具"
Write-Host "========================================"
Write-Host ""
Write-Host "请选择导出方法:"
Write-Host ""
Write-Host "1. 从 Chrome 浏览器导出"
Write-Host "2. 从 Edge 浏览器导出"
Write-Host "3. 从 Firefox 浏览器导出"
Write-Host "4. 手动下载 cookies (推荐)"
Write-Host "5. 退出"
Write-Host ""

$choice = Read-Host "请输入选项 (1-5)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "⚠️ 重要: 请先完全关闭所有 Chrome 浏览器窗口！" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "按 Enter 继续"
        Write-Host ""
        Write-Host "正在从 Chrome 导出 cookies..."
        
        try {
            & yt-dlp --cookies-from-browser chrome --cookies www.youtube.com_cookies.txt "https://www.youtube.com"
            
            if (Test-Path "www.youtube.com_cookies.txt") {
                Write-Host ""
                Write-Host "========================================"
                Write-Host "✅ Cookies 导出成功！" -ForegroundColor Green
                Write-Host "========================================"
                Write-Host ""
                Write-Host "文件位置: $PWD\www.youtube.com_cookies.txt"
                Write-Host ""
                Write-Host "现在可以重新运行程序了。"
                Write-Host "========================================"
            } else {
                throw "文件未创建"
            }
        } catch {
            Write-Host ""
            Write-Host "❌ 导出失败！" -ForegroundColor Red
            Write-Host ""
            Write-Host "可能的原因:"
            Write-Host "1. Chrome 浏览器未完全关闭"
            Write-Host "2. Chrome 未登录 YouTube"
            Write-Host "3. 权限问题 (尝试以管理员身份运行)"
            Write-Host ""
            Write-Host "建议: 使用方法 4 (手动下载)" -ForegroundColor Yellow
        }
    }
    
    "2" {
        Write-Host ""
        Write-Host "⚠️ 重要: 请先完全关闭所有 Edge 浏览器窗口！" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "按 Enter 继续"
        Write-Host ""
        Write-Host "正在从 Edge 导出 cookies..."
        
        try {
            & yt-dlp --cookies-from-browser edge --cookies www.youtube.com_cookies.txt "https://www.youtube.com"
            
            if (Test-Path "www.youtube.com_cookies.txt") {
                Write-Host ""
                Write-Host "✅ Cookies 导出成功！" -ForegroundColor Green
                Write-Host "文件位置: $PWD\www.youtube.com_cookies.txt"
            } else {
                throw "文件未创建"
            }
        } catch {
            Write-Host "❌ 导出失败！建议使用方法 4 (手动下载)" -ForegroundColor Red
        }
    }
    
    "3" {
        Write-Host ""
        Write-Host "⚠️ 重要: 请先完全关闭所有 Firefox 浏览器窗口！" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "按 Enter 继续"
        Write-Host ""
        Write-Host "正在从 Firefox 导出 cookies..."
        
        try {
            & yt-dlp --cookies-from-browser firefox --cookies www.youtube.com_cookies.txt "https://www.youtube.com"
            
            if (Test-Path "www.youtube.com_cookies.txt") {
                Write-Host ""
                Write-Host "✅ Cookies 导出成功！" -ForegroundColor Green
                Write-Host "文件位置: $PWD\www.youtube.com_cookies.txt"
            } else {
                throw "文件未创建"
            }
        } catch {
            Write-Host "❌ 导出失败！建议使用方法 4 (手动下载)" -ForegroundColor Red
        }
    }
    
    "4" {
        Write-Host ""
        Write-Host "========================================"
        Write-Host "手动导出 Cookies 步骤 (推荐)"
        Write-Host "========================================"
        Write-Host ""
        Write-Host "1. 安装浏览器扩展:"
        Write-Host "   Chrome/Edge: 搜索 'Get cookies.txt LOCALLY'"
        Write-Host "   链接: https://chrome.google.com/webstore" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "2. 访问 YouTube 并登录:"
        Write-Host "   https://www.youtube.com" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "3. 点击扩展图标，选择导出 cookies"
        Write-Host ""
        Write-Host "4. 保存文件为: www.youtube.com_cookies.txt"
        Write-Host ""
        Write-Host "5. 将文件放入项目文件夹:"
        Write-Host "   $PWD" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "========================================"
    }
    
    "5" {
        Write-Host "退出"
        return
    }
    
    default {
        Write-Host ""
        Write-Host "❌ 无效的选项！" -ForegroundColor Red
    }
}

Write-Host ""
Read-Host "按 Enter 退出"

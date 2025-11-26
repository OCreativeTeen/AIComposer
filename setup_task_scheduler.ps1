# PowerShell脚本：设置Windows任务计划程序进行夜间批量图像生成
# 需要管理员权限运行

param(
    [string]$TaskName = "MovieMaker_NightBatch",
    [string]$StartTime = "00:00",  # 午夜开始
    [string]$ScriptPath = $PSScriptRoot + "\run_night_batch.bat"
)

Write-Host "======================================" -ForegroundColor Green
Write-Host "设置夜间批量图像生成任务计划" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green

# 检查是否以管理员身份运行
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")

if (-not $isAdmin) {
    Write-Host "错误: 此脚本需要管理员权限才能创建任务计划" -ForegroundColor Red
    Write-Host "请右键点击PowerShell，选择'以管理员身份运行'" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 1
}

# 检查批处理脚本是否存在
if (-not (Test-Path $ScriptPath)) {
    Write-Host "错误: 找不到批处理脚本: $ScriptPath" -ForegroundColor Red
    exit 1
}

try {
    # 删除已存在的任务（如果有）
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Host "删除现有任务: $TaskName" -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # 创建任务操作
    $action = New-ScheduledTaskAction -Execute $ScriptPath

    # 创建触发器（每天在指定时间运行）
    $trigger = New-ScheduledTaskTrigger -Daily -At $StartTime

    # 创建任务设置
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    # 创建任务主体（使用当前用户）
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType ServiceAccount

    # 注册任务
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "夜间批量图像生成任务 - Movie Maker"

    Write-Host "✅ 任务计划创建成功!" -ForegroundColor Green
    Write-Host "任务名称: $TaskName" -ForegroundColor Cyan
    Write-Host "执行时间: 每天 $StartTime" -ForegroundColor Cyan
    Write-Host "脚本路径: $ScriptPath" -ForegroundColor Cyan
    
    # 显示任务信息
    $task = Get-ScheduledTask -TaskName $TaskName
    Write-Host "`n任务状态: " -NoNewline
    Write-Host $task.State -ForegroundColor Green
    
    Write-Host "`n管理选项:" -ForegroundColor Yellow
    Write-Host "- 查看任务: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host "- 手动运行: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host "- 删除任务: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host "- 打开任务计划程序: taskschd.msc" -ForegroundColor Gray

} catch {
    Write-Host "❌ 创建任务计划失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n⚠️ 重要提醒:" -ForegroundColor Yellow
Write-Host "1. 确保已创建 'night_batch_config.json' 配置文件" -ForegroundColor White
Write-Host "2. 确保稳定扩散服务器在运行时间内可用" -ForegroundColor White
Write-Host "3. 检查磁盘空间是否足够" -ForegroundColor White
Write-Host "4. 建议先手动测试一次批处理流程" -ForegroundColor White

Read-Host "`n按回车键退出" 
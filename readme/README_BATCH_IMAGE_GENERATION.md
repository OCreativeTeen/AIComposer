# 批量图像生成工具使用指南

## 概述

批量图像生成工具允许您在夜间或其他空闲时间批量处理多个项目的图像生成任务。这是整个工作流程中最耗时的部分，通过调度到非工作时间可以大大提升工作效率。

## 功能特点

- ✅ 支持单个项目和批量项目处理
- ✅ 完整的日志记录和错误处理
- ✅ 详细的处理报告生成
- ✅ Windows任务计划程序集成
- ✅ 自动检查项目文件完整性
- ✅ 支持自定义图像生成参数
- ✅ 项目间延迟控制，避免资源争抢

## 前置条件

在使用批量图像生成之前，确保以下文件已准备就绪：

### 必需文件
- `{pid}_scenes.json` - 场景数据文件
- `{pid}_paragraphs.json` - 段落数据文件  
- `{pid}.aac` - 音频文件
- `{pid}_{language}.srt` - 字幕文件

### 生成这些文件的方法
```bash
# 通过音频转录生成所需文件
python magic_workflow.py create_script_from_audio --pid your_project_id --audio path/to/audio.wav
```

## 使用方法

### 1. 单个项目处理

```bash
# 基本用法
python run_image_generator.py --pid project001 --language zh --channel world_zh

# 自定义参数
python run_image_generator.py \
    --pid project001 \
    --language zh \
    --channel world_zh \
    --description "historical documentary style" \
    --cfg-scale 8 \
    --negative-prompt "cartoon, anime, low quality"
```

### 2. 批量处理

#### 创建配置文件
```bash
# 创建示例配置文件
python run_image_generator.py --create-sample
```

这会生成 `batch_config_sample.json` 文件：

```json
{
  "description": "夜间批量图像生成配置文件",
  "default_settings": {
    "language": "zh",
    "channel": "world_zh", 
    "description": "ultra-realistic, 35mm photograph, natural lighting",
    "cfg_scale": 7,
    "negative_prompt": "low quality, blurry, cartoon, anime",
    "delay_between_projects": 10
  },
  "projects": [
    {
      "pid": "project001",
      "description": "historical documentary style"
    },
    {
      "pid": "project002",
      "channel": "strange_zh",
      "description": "mysterious atmosphere"
    }
  ]
}
```

#### 运行批量处理
```bash
# 使用配置文件批量处理
python run_image_generator.py --batch night_batch_config.json
```

### 3. 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--pid` | 项目ID | - |
| `--language` | 语言代码 | zh |
| `--channel` | 频道配置 | world_zh |
| `--description` | 图像描述 | "" |
| `--cfg-scale` | CFG Scale值 | 7 |
| `--negative-prompt` | 负面提示词 | "" |
| `--batch` | 批处理配置文件 | - |
| `--log-level` | 日志级别 | INFO |
| `--report` | 报告文件路径 | 自动生成 |

## 夜间调度设置

### Windows系统

#### 方式1：使用PowerShell脚本自动设置

1. **以管理员身份运行PowerShell**
2. **设置执行策略**（如果需要）：
   ```powershell
   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
3. **运行设置脚本**：
   ```powershell
   .\setup_task_scheduler.ps1
   ```

#### 方式2：手动设置任务计划程序

1. 打开"任务计划程序" (`taskschd.msc`)
2. 创建基本任务
3. 设置触发器：每天午夜（00:00）
4. 设置操作：启动程序 `run_night_batch.bat`
5. 配置条件和设置

#### 方式3：使用批处理脚本

```bash
# 直接运行批处理脚本
run_night_batch.bat

# 交互模式（显示结果）
run_night_batch.bat interactive
```

### Linux/Mac系统

使用cron调度：

```bash
# 编辑crontab
crontab -e

# 添加调度任务（每天午夜运行）
0 0 * * * cd /path/to/Movie_Maker && python run_image_generator.py --batch night_batch_config.json
```

## 配置文件详解

### 批处理配置文件结构

```json
{
  "description": "配置文件描述",
  "default_settings": {
    "language": "zh",           // 默认语言
    "channel": "world_zh",      // 默认频道
    "description": "...",       // 默认图像描述
    "cfg_scale": 7,            // 默认CFG Scale
    "negative_prompt": "...",   // 默认负面提示词
    "delay_between_projects": 10 // 项目间延迟（秒）
  },
  "projects": [
    {
      "pid": "project001",                    // 必需：项目ID
      "language": "en",                       // 可选：覆盖默认语言
      "channel": "travel_zh",                 // 可选：覆盖默认频道
      "description": "travel photography",    // 可选：覆盖默认描述
      "cfg_scale": 8,                        // 可选：覆盖默认CFG Scale
      "negative_prompt": "cartoon",          // 可选：覆盖默认负面提示词
      "delay_between_projects": 15           // 可选：覆盖默认延迟
    }
  ]
}
```

### 频道配置

可用的频道选项（在 `config.py` 中定义）：
- `strange_zh` - 聊斋新语
- `spirit_zh` - 默观深省  
- `travel_zh` - 旅途故事
- `world_zh` - 观往晓来
- `heart_zh` - 家常有道

## 日志和报告

### 日志文件

运行时会自动生成日志文件：
- 位置：`logs/image_generator_YYYYMMDD_HHMMSS.log`
- 包含：详细的处理过程、错误信息、时间戳

### 处理报告

每次运行结束会生成：

1. **控制台摘要报告**：显示总体统计信息
2. **详细JSON报告**：`logs/batch_report_YYYYMMDD_HHMMSS.json`

示例报告内容：
```
🎨 图像生成批处理完成报告
==================================================
⏰ 处理时间: 2024-01-15 00:00:00 - 2024-01-15 06:30:00
⏱️ 总耗时: 6.50 小时 (23400 秒)
📊 项目统计: 总计 5 个，成功 4 个，失败 1 个
📈 成功率: 80.0%
🎨 图像统计: 总计生成 245 张图像

✅ 成功项目:
   • project001: 65 张图像 (3600秒)
   • project002: 48 张图像 (2800秒)
   • project003: 72 张图像 (4200秒)
   • project004: 60 张图像 (3500秒)

❌ 失败项目:
   • project005: 缺少文件: scenes.json
```

## 故障排除

### 常见问题

#### 1. 缺少必需文件
```
错误: 项目 project001 不满足要求，缺少文件: scenes.json
```

**解决方案**：
- 确保已运行 `create_script_from_audio` 生成所需文件
- 检查文件路径和命名是否正确

#### 2. SD服务器连接失败
```
错误: 所有SD服务器都不可用
```

**解决方案**：
- 确保Stable Diffusion WebUI正在运行
- 检查 `--api` 参数是否已添加
- 验证服务器地址和端口配置

#### 3. 内存不足
```
错误: CUDA out of memory
```

**解决方案**：
- 减少并发处理的项目数
- 增加项目间延迟时间
- 检查GPU内存使用情况

#### 4. 磁盘空间不足
```
错误: No space left on device
```

**解决方案**：
- 清理旧的图像文件
- 检查可用磁盘空间
- 考虑使用外部存储

### 调试技巧

1. **启用详细日志**：
   ```bash
   python run_image_generator.py --batch config.json --log-level DEBUG
   ```

2. **测试单个项目**：
   ```bash
   python run_image_generator.py --pid test_project --language zh
   ```

3. **检查项目文件**：
   ```bash
   # 验证必需文件是否存在
   ls /Projects/media/program/data/project001/
   ```

## 性能优化建议

### 1. 硬件优化
- 使用高性能GPU（RTX 3080及以上）
- 确保足够的GPU内存（建议12GB+）
- 使用SSD存储提升I/O性能

### 2. 软件优化
- 调整项目间延迟时间平衡速度和稳定性
- 批量处理时避免同时运行其他GPU密集型任务
- 定期清理临时文件和旧的生成结果

### 3. 调度优化
- 选择系统负载较低的时间段
- 避免在系统备份或维护期间运行
- 监控系统资源使用情况

## 最佳实践

1. **准备工作**：
   - 批量处理前，先测试1-2个项目确保配置正确
   - 检查所有项目的必需文件是否完整
   - 确保有足够的磁盘空间

2. **配置管理**：
   - 为不同类型的项目创建不同的配置文件
   - 使用版本控制管理配置文件
   - 定期备份重要的配置

3. **监控和维护**：
   - 定期检查日志文件了解处理情况
   - 监控系统资源使用避免过载
   - 及时清理旧的日志和报告文件

4. **安全考虑**：
   - 定期备份重要的项目数据
   - 监控磁盘空间避免系统满载
   - 设置合理的超时和重试机制 
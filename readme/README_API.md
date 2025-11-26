# Magic Video API 使用说明

这是一个将视频制作工作流程转换为REST API的服务，支持异步音频转录、图像生成和视频合成。

## 功能特性

- 🎵 音频文件上传和处理
- 🎤 音频转录（支持多语言）
- 📝 智能内容摘要
- 🖼️ AI图像生成（基于Stable Diffusion）
- 🎬 视频合成和输出
- ⚡ 异步任务处理
- 📊 实时进度监控
- 🔄 任务管理和文件清理

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务

```bash
python api_server.py
```

服务将在 `http://localhost:8000` 启动

## API文档

启动服务后，访问以下URL查看自动生成的API文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API端点

### 1. 处理视频 (POST /process-video)

上传音频文件并启动视频处理流程。

**请求参数：**
- `audio_file`: 音频文件 (必需，支持WAV/MP3/M4A/AAC格式)
- `pid`: 项目ID (可选，自动生成)
- `language`: 音频语言 (默认: zh)
- `positive`: 正向提示词 (用于图像生成)
- `negative`: 负向提示词 (用于图像生成)
- `quick_test`: 快速测试模式 (跳过转录和摘要)

**响应示例：**
```json
{
    "task_id": "123e4567-e89b-12d3-a456-426614174000",
    "message": "任务已创建，开始处理",
    "status_url": "/status/123e4567-e89b-12d3-a456-426614174000"
}
```

### 2. 获取任务状态 (GET /status/{task_id})

查询任务的当前状态和进度。

**响应示例：**
```json
{
    "task_id": "123e4567-e89b-12d3-a456-426614174000",
    "status": "processing",
    "progress": 65,
    "message": "正在生成图像...",
    "created_at": "2024-01-15T10:30:00",
    "completed_at": null,
    "result_path": null,
    "error": null
}
```

**状态说明：**
- `pending`: 等待处理
- `processing`: 正在处理
- `completed`: 处理完成
- `failed`: 处理失败

### 3. 下载视频 (GET /download/{task_id})

下载处理完成的视频文件。

### 4. 获取所有任务 (GET /tasks)

获取所有任务的状态列表。

### 5. 删除任务 (DELETE /task/{task_id})

删除任务记录和相关文件。

## 使用示例

### cURL 示例

```bash
# 1. 上传音频文件并开始处理
curl -X POST "http://localhost:8000/process-video" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "audio_file=@audio.wav" \
  -F "language=zh" \
  -F "positive=christian monk, catholic church" \
  -F "negative=buddhist temple"

# 2. 查询任务状态
curl -X GET "http://localhost:8000/status/{task_id}"

# 3. 下载完成的视频
curl -X GET "http://localhost:8000/download/{task_id}" \
  --output "result.mp4"
```

### Python 客户端示例

```python
from api_client_example import MagicVideoClient

# 创建客户端
client = MagicVideoClient("http://localhost:8000")

# 处理视频
result = client.process_video(
    "audio.wav",
    language="zh",
    positive="christian monk, catholic church",
    negative="buddhist temple"
)

task_id = result['task_id']

# 等待完成
status = client.wait_for_completion(task_id)

# 下载视频
client.download_video(task_id, "output.mp4")
```

## 配置说明

### 环境要求

- Python 3.8+
- CUDA支持的GPU (用于AI图像生成)
- FFmpeg (用于音视频处理)
- Stable Diffusion WebUI (用于图像生成)

### 目录结构

```
.
├── api_server.py           # API服务器
├── api_client_example.py   # 客户端示例
├── Magic_Video_Workflow.py # 原始工作流程
├── requirements.txt        # 依赖文件
├── uploads/               # 上传文件目录
├── data/                  # 工作数据目录
└── /Projects/Channel/media/program/publish/  # 输出视频目录
```

## 错误处理

API使用标准HTTP状态码：

- `200`: 成功
- `400`: 请求错误（如不支持的文件格式）
- `404`: 资源不存在（如任务ID无效）
- `500`: 服务器内部错误

## 性能建议

1. **文件大小**: 建议音频文件小于100MB
2. **并发处理**: 服务器根据资源情况限制并发任务数
3. **存储空间**: 确保有足够的磁盘空间存储临时文件和输出视频
4. **GPU内存**: 图像生成需要大量GPU内存，建议8GB+

## 监控和日志

- 服务日志输出到控制台
- 任务状态和错误信息通过API返回
- 可以通过 `/tasks` 端点监控所有任务状态

## 部署建议

### 开发环境
```bash
python api_server.py
```

### 生产环境
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 1
```

### Docker 部署
可以创建Dockerfile进行容器化部署，需要注意GPU支持和依赖环境配置。

## 故障排除

1. **CUDA不可用**: 检查GPU驱动和CUDA安装
2. **Stable Diffusion连接失败**: 确保WebUI服务正常运行
3. **音频转录失败**: 检查Whisper模型下载和语言设置
4. **文件权限错误**: 确保服务有读写权限

## 技术支持

如遇问题，请检查：
1. 服务日志输出
2. 任务状态错误信息
3. 系统资源使用情况
4. 依赖服务状态 
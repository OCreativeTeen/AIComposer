# 谈话内容摘要和视频制作工具

这个工具可以将语音识别得到的文字内容智能分段，并使用ChatGPT API生成适合视频制作的摘要。每个段落都会标注开始和结束时间，方便后续的视频制作。

## 功能特点

- 🎯 **智能分段**: 根据句子结构和长度自动将长文本分成合理的段落
- 🤖 **AI摘要**: 使用ChatGPT API生成生动、具体的摘要，适合用作图像生成提示词
- ⏰ **时间戳计算**: 自动计算每段的开始和结束时间
- 📊 **结构化输出**: 生成JSON格式的结构化数据，便于后续处理
- 📝 **视频脚本**: 自动生成视频制作脚本文件
- 🔧 **灵活配置**: 支持自定义模型、时长等参数

## 安装依赖

```bash
pip install -r requirements.txt
```

## 快速开始

最简单的使用方法：

```bash
python quick_start.py your_talk.txt --api-key YOUR_OPENAI_API_KEY
```

这将自动完成文本分段、摘要生成和视频项目创建的整个流程。

## 使用方法

### 快速开始脚本

```bash
python quick_start.py input.txt --api-key YOUR_OPENAI_API_KEY [选项]
```

#### 快速开始参数

- `text_file`: 输入的文本文件路径（必需）
- `--api-key`: OpenAI API密钥（必需）
- `--audio`: 音频文件路径（可选）
- `--duration`: 总时长（分钟）（可选）
- `--project`: 项目名称（可选）

### 命令行使用

```bash
python summerize_talk.py input.txt --api-key YOUR_OPENAI_API_KEY [选项]
```

#### 参数说明

- `input_file`: 输入的文本文件路径（必需）
- `--api-key`: OpenAI API密钥（必需）
- `--output`: 输出JSON文件路径（可选，默认为输入文件名_summary.json）
- `--duration`: 总时长（分钟）（可选，不提供则自动估算）
- `--model`: GPT模型（可选，默认为gpt-3.5-turbo）
- `--script`: 视频脚本输出路径（可选，默认为video_script.md）

#### 使用示例

```bash
# 基本使用
python summerize_talk.py talk.txt --api-key sk-your-api-key-here

# 指定总时长为10分钟
python summerize_talk.py talk.txt --api-key sk-your-api-key-here --duration 10

# 使用GPT-4模型并指定输出文件
python summerize_talk.py talk.txt --api-key sk-your-api-key-here --model gpt-4 --output my_summary.json

# 完整参数示例
python summerize_talk.py talk.txt \
  --api-key sk-your-api-key-here \
  --duration 15 \
  --model gpt-3.5-turbo \
  --output talk_summary.json \
  --script talk_script.md
```

### 编程使用

```python
from summerize_talk import TalkSummarizer

# 创建摘要器
summarizer = TalkSummarizer(api_key="your-api-key", model="gpt-3.5-turbo")

# 处理文件
result = summarizer.process_talk(
    input_file="talk.txt",
    output_file="summary.json",
    total_duration_minutes=10.0
)

# 生成视频脚本
summarizer.generate_video_script(result, "script.md")
```

## 输出格式

### JSON输出文件结构

```json
{
  "metadata": {
    "input_file": "talk.txt",
    "total_segments": 5,
    "total_duration": "00:10:00",
    "processed_at": "2024-01-01T12:00:00",
    "model_used": "gpt-3.5-turbo"
  },
  "segments": [
    {
      "segment_id": 1,
      "start_time": "00:00:00",
      "end_time": "00:02:00",
      "original_text": "原始文本内容...",
      "summary": "适合视频制作的摘要内容...",
      "character_count": 150
    }
  ]
}
```

### 视频脚本文件

生成的Markdown格式脚本文件包含：
- 每个段落的时间范围
- 图像生成提示（摘要）
- 原始文本预览

## 工作流程

1. **文本读取**: 读取输入的文本文件
2. **智能分段**: 根据标点符号和长度将文本分成段落
3. **时间计算**: 根据字符数比例或指定时长计算每段时间
4. **摘要生成**: 调用ChatGPT API为每段生成适合视觉化的摘要
5. **结果保存**: 保存JSON格式的结构化数据和视频脚本

## 后续视频制作建议

1. **图像生成**: 使用生成的摘要作为提示词，通过DALL-E、Midjourney等工具生成图像
2. **视频合成**: 根据时间戳将图像按顺序合成视频
3. **音频同步**: 将原始音频与生成的视频进行同步

## 注意事项

- 需要有效的OpenAI API密钥
- API调用会产生费用，建议先用短文本测试
- 程序会在API调用间添加1秒延迟以避免频率限制
- 建议使用UTF-8编码的文本文件

## 错误处理

程序包含完善的错误处理机制：
- 文件读取失败
- API调用失败
- 网络连接问题
- 无效的API密钥

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request来改进这个工具！ 
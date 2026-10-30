# AIComposer（魔法工作流）

Windows 上的视频制作工具：从 YouTube / 文本 / PDF 取素材 → LLM 写故事和分镜 → 生成图片、配音、视频片段 → 合成剪辑 → 封面 → 发布到 YouTube。
界面是 Python Tkinter；浏览器里的 Gemini / Grok / NotebookLM 通过 Chrome CDP（Playwright）自动操作。

## 目录

| 路径 | 内容 |
|---|---|
| `GUI_wf.py` | 主工作流界面（`start_gui.bat` 启动它） |
| `GUI_pm.py` / `GUI_topic.py` | 项目管理 / 选题下载界面 |
| `magic_workflow.py`, `magic_workflow_episodes.py` | 工作流核心：场景、分集（episode） |
| `gui/workflow/` | 主工作流各面板（wf_*） |
| `gui/dl/` | 下载、选题、场景编辑、演员面板等 |
| `utility/` | LLM（llm_api）、TTS（voicebox）、转写、ffmpeg、Gemini/Grok/NotebookLM CDP 等 |
| `cli/` | Hermes Telegram 客户端与浏览器任务（browser_tasks），见 `cli/CLI_REFERENCE.md` |
| `config.py` | 全局配置：路径、服务地址、Chrome 账号、频道；读取 `.env` |
| `config_prompt.py`, `config_channel.py` | 提示词与频道配置 |
| `workflow/` | ComfyUI 工作流 JSON |
| `storyproducer/` | 独立的故事生成模块（见其 README） |
| `main.py` | 旧的工具启动器（部分模块已不存在，会提示改用 GUI_wf.py） |

## 安装

```bat
py -3.11 -m venv venv
venv\Scripts\activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
playwright install chromium
```

另外需要：ffmpeg 在 PATH 里；Google Chrome；Node.js（见 `install_nodejs.md`，CLI 用）。

## 配置 `.env`

```bat
copy .env.example .env
```

然后填 API key、Telegram token、Chrome 账号（`CHROME_PROFILES_JSON`）等。`.env` 不进 git；所有 key 名见 `.env.example`。
服务地址（Strata、Voicebox、转写、ComfyUI/WAN 等）在 `config.py` 的「服务地址」段，都可以用 `.env` 覆盖。

## 媒体目录 `AI_MEDIA_ROOT`

默认 `D:/AI_MEDIA`（`.env` 里 `AI_MEDIA_ROOT` 可改）：

```
AI_MEDIA/
  working/   临时文件、content.pdf / actor.pdf、NotebookLM 下载、pdf_pages、_trash
  program/   各频道的项目与列表
  avatar/    演员 / 讲员形象、voices.json
  aiagent/   CLI / Hermes 运行状态（队列、剪贴板、Chrome profile 记录）
  publish/   发布产物
  font/ effect/ default/ input/
```

旧项目 JSON 里存的 `/AI_MEDIA/...` 路径：根目录不变时原样可用；换了根目录可用 `config.resolve_media_path()` 换算。

## 运行

```bat
start_gui.bat            :: 主工作流（GUI_wf.py）
python GUI_pm.py         :: 项目管理
cli\run_telegram_client.bat  :: Hermes Telegram 客户端
```

## 外部服务

- **Strata**（本机 OpenAI 兼容 LLM，`STRATA_BASE_URL`）：纯文字调用
- **Gemini / Grok / NotebookLM**：Chrome CDP 自动操作网页（手动窗口里的「CLI自动」）
- **Voicebox**（`VOICEBOX_BASE_URL`）：TTS / ASR
- **ComfyUI / WAN**（已停用）
- **YouTube Data API**：OAuth client_secret 放 `config/`（不进 git）

## 注意

- 不要把 `.env`、`client_secret*.json`、调试截图、`_patch_*.py` 等提交进来（`.gitignore` 已覆盖）。

# StoryProducer（无 GUI）

独立于现有 `gui/downloader.py`、`cli/run_bot.bat`、`cli/run_telegram_client.bat`。
**不要改、也不要同时跑**那一套（同一 `TELEGRAM_CLI_BOT_TOKEN` 会 409）。

StoryProducer 没有 Tk 窗口，也没有 GUI bridge 轮询。Telegram bot 和引擎在**同一进程**里调函数。队列与媒体路径仍用原来的：

- 待处理队列：`D:\AI_MEDIA\aiagent\video_choice_queue.json`（指向频道「故事列表」JSON + 行）
- 封面 / 场景图 / clip / 成片：`\\AI_MEDIA\\publish\\gen_video\\`
- 进度回写到**原 list JSON** 该行的 `scene_content`（含 `clip` / `clip_start` / `clip_end` / `clip_speed`）、`cover_image`、`video`、`workflow`

## 入口

```bat
storyproducer\run_client.bat     :: 无 GUI 自动流水线（grv + grvc → scene_content[].clip）
storyproducer\run_gui.bat        :: run_client 之后：打开 GUI，逐条载入 clip 审阅窗（vc）
storyproducer\run_bot.bat        :: 听筒：你在 Telegram 发 CLI
```

```bash
python -m storyproducer client
python -m storyproducer gui
python -m storyproducer gui --pick 2 --once
python -m storyproducer client --target FULL_PROCESS
python -m storyproducer bot
python -m storyproducer pick next
```

启动时选目标，然后**整批只问一次** Visual Style / Narrator；若队列里还有 INIT 故事才问 LM 提示。后续每条故事自动复用，不再重复询问。

`--target` 可选 `GEMINI_ONLY` / `INFOGRAPHIC_ONLY` / `FULL_PROCESS`。不填则启动时用 Telegram 询问。

## workflow 节点

每个故事（list 里的 item / video-detail）带一个 `workflow`：

```json
"workflow": {
  "stage": "INIT",
  "infographic_status": "NONE",
  "selected_infographic_image": null
}
```

| `stage` | 含义 |
|---------|------|
| `INIT` | 尚无场景描述 |
| `GEMINI_DONE` | 已选定 `scene_content` |
| `INFOGRAPHIC_PENDING` | 已提交 NotebookLM，尚未确认/下载 |
| `INFOGRAPHIC_DONE` | 已选定封面，写入 `cover_image` |
| `COMPLETED` | 各场 `scene_content[].clip` 已生成 |

`infographic_status`：`NONE` / `SUBMITTED` / `COMPLETED` / `FAILED`。

场景 clip 字段：`clip`（未生成时为 `null`），生成后先拷到 `gen_video\\….mp4`，并带 `clip_start` / `clip_end` / `clip_speed`。同时仍写 `grok_clip` 以便旧读取。

封面写入 `cover_image`（`gen_video/<id>.webp`）。审阅拼接后的成片写入 `video`（`gen_video/<id>.mp4`）。

旧字段 `gen_video_clip_segments` 打开审阅窗时仍能读；保存后迁到 `scene_content`。

## 三大阶段

启动时选目标：

1. **GEMINI_ONLY** — 生成 3 套场景 JSON，Telegram 选 1 套后写入 `scene_content`，停。
2. **INFOGRAPHIC_ONLY** — 再提交 NotebookLM 出 3 张封面，选 1 张写入 `cover_image`，停。
3. **FULL_PROCESS** — 继续 Grok 出场景图 + Video Clip，标 `COMPLETED`。

智能跳转（按该 Story 自己的 `workflow.stage`，队列里各条进度可以不同）：

- 已有场景描述：问是否跳过阶段一。
- `INFOGRAPHIC_PENDING`：`1` 检查下载 / `2` 重新生成 / `3` 跳过该 Story（去下一条）。
- nbif 轮询超时：本条保持 PENDING，**不退出 client**，改处理下一条。
- `INFOGRAPHIC_DONE` 且目标是阶段三：直接 Grok。

队列 `status: done` 只在 `COMPLETED`（全程 clips）时标记。只做到阶段一/二的条目保持未完成，下次换目标可以接着做。

## CLI（bot 或终端）

| 命令 | 作用 |
|------|------|
| `pick` / `pick next` / `pick N` | 取队列故事 |
| `scnlm` `[N]` | LM 提示 |
| `scnvs` `[N]` | Visual Style |
| `nar` `[N]` | narrator（画外音，不出镜） |
| `scnge` | Gemini 生成场景 JSON |
| `scnsave` | 保存 `scene_content`，stage → `GEMINI_DONE` |
| `nbp 1` | NotebookLM 封面提示词 → 剪贴板 |
| `nbi N` | 开 NotebookLM Generate ×3，stage → `INFOGRAPHIC_PENDING` |
| `nbif` | 是否 ready |
| `itc` / `itcs` / `itc N` | 下载或选封面 → `cover_image`，stage → `INFOGRAPHIC_DONE` |
| `nbv N` | Grok video 提示词变体 |
| `grv` | 出图出片并写入 `clip`，stage → `COMPLETED` |
| `status` | 当前故事与 stage |

浏览器自动化复用 `cli/browser_tasks.py`，不经过 SCENE Tk bridge。

## GUI 审阅阶段（run_gui）

`run_client.bat` 跑完后，各场景 clip 已写入 `scene_content[].clip`。再跑：

```bat
storyproducer\run_gui.bat
```

流程（等同原 `cli\run_telegram_client.bat` 里的 vc 步骤）：

1. 扫描队列，找**全部场景都有 clip** 的故事（`--partial` 可放宽）
2. 用 `ensure_gui_for_queue_item` 打开 STORY（与 `pick` 相同机制）
3. 自动发 `vc`，把各场景 mp4 载入审阅窗（裁剪/排序/确认 → 拼接+水印成片）
4. 你在 GUI 内操作；可 Telegram 发 `vp` 发布
5. 发 `next` / `continue` / `完成` — 关闭 GUI，本条标为 **GUI已审阅**
6. 再发 `1` / `2` / `3` 选下一条（**可重复**选已审阅的）；`list` 刷新列表；`exit` 结束

不要与 `cli\run_telegram_client.bat` 同时跑（同一 Telegram token）。

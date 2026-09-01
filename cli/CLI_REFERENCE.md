# AIComposer CLI 操作员手册

Telegram 听筒、Hermes、或本机终端均可发这些命令。

**入口**

```bash
python -m cli <命令> [参数]
python -m cli help          # 简短帮助
python -m cli bot           # 启动 Telegram 听筒
```

发命令前可用 `win` / `sync` 看当前在哪个窗口。听筒进窗后会主动推送「可发：…」列表。

---

## 1. 窗口对照

| 听筒短名 | 内部名 | 窗口标题示例 | 说明 |
|---------|--------|-------------|------|
| `story` | `story_root` | `STORY \| …` | 摘要窗：分析、诗歌、点「场景」进 SCENE |
| `scene` | `story_scene` | `SCENE \| …` | 分镜窗：选 LM、Gemini、Grok、保存 |
| `list` | `video_list` | `LIST \| …` | 热门视频列表 |
| `yt` | `yt_tools` | `YT 工具` | YT 工具选择 |
| `none` | `none` | — | 没有识别到 STORY/SCENE |

**注意：** `story` 是**窗名**，不是命令。打开分镜用 `scn`，不要用 `story`。

---

## 2. 各窗口可发的 CLI

### SCENE（`story_scene`）

听筒同步里常见：

`lm` `sty` `snp` `prf` `gem` `scnsave` `nbp` `nbi` `nbif` `itc` `igp` `grv` `gvd` `nbv` `vc` `vp` `sync`

### STORY（`story_root`）

`scn` `save` `pub` `ana` `poe` `scr` `sty` `cov` `vc` `vp` `sync`

### LIST / YT / none

通常只有 `sync`；`none` 且为队列会话时还可 `pick` / `pick 1` …

### 任意时刻

`win` `sync` `help` `status` `pick`（队列会话）

---

## 3. 典型流水线（一条故事）

```
pick next          # 或 pick 3；队列里取下一条
scn                # STORY → 打开 SCENE
lm 4               # 选「4 Step Story」，长 prompt 上剪贴板
gem                # Gemini 生成 4 场 JSON → 剪贴板
scnsave             # 剪贴板 JSON → scene_content + 保存到频道列表（不关窗）
nbp 1              # 选 NotebookLM 导出类型（先无参看列表）
nbi 1              # 选 Chrome 号，开 NotebookLM，Generate ×3 后立刻返回（不等待）
nbif               # 查询三张新 infographic 是否 ready
itc                # 拷最上边三张并发 Telegram 请选
itc 2              # 选第 2 张封面（Telegram 直接回 2 也可以）
grv 1 3             # 选 Chrome 号 + video 变体 3；全自动出图+出片+每场景下载
                   # 省略变体时用 session 已存值（默认 3）
grv 1               # 同上，用已存变体
gvd                # （可选）补下载全部 mp4（grv 已含下载时通常不必再发）
vc                 # 拼接成片
vp default         # 上传 YouTube
pick next          # 下一条
```

**Grok 全自动：** `grv 1 [1…8]` 一轮完成开标签、贴封面、场景出图、video 出片，并在每个标签出片后**立刻 CDP 下载 mp4**（与 `gvd` 同路数）。封面须先 `itc pick`。

---

## 4. 命令详解（按功能）

### 4.1 听筒 / 状态

| 短名 | 长名 | 窗口 | 参数 | 作用 |
|------|------|------|------|------|
| `win` | `screen` | 任意 | 无 | 当前窗口：`story` / `scene` / `list` / `yt` / `none` |
| `sync` | `where`, `here` | 任意 | 无 | 同听筒同步：当前窗 + 可发命令列表 |
| `help` | `commands`, `start` | 任意 | 无 | 简短命令列表 |
| `status` | — | 任意 | 无 | 调试：hwnd、active_screen 等 |

---

### 4.2 队列（pick）

| 短名 | 长名 | 窗口 | 参数 | 作用 |
|------|------|------|------|------|
| `pick` | `story_pickup` | 队列会话 | 见下 | 列出或选取队列里的故事 |

**参数**

| 参数 | 含义 |
|------|------|
| （无） | 列出全部 `pick 1` `pick 2` … |
| `next` / `n` / `下一条` | 取下一条**未处理**（没有未处理时会列出全部，不要硬 next） |
| `1` `2` `3` … | 按序号打开（**已完成的也能重做**） |
| `exit` / `停` / `quit` | 结束本轮 pickup |
| `choice_id` 或标题片段 | 按 ID / 标题匹配 |

**限制：** `GUI_pm` 手工开的 GUI 会关掉 `pick`；听筒只跟窗口同步。

---

### 4.3 开窗 / 导航

| 短名 | 长名 | 窗口 | 参数 | 作用 |
|------|------|------|------|------|
| `scn` | `scene`, `go`, `flow` | STORY（或已有 SCENE） | 无 | 打开并置前 **SCENE**；已在 SCENE 则直接 ok |
| `save` | — | STORY 或 SCENE | 无 | 点「保存」 |
| `pub` | `publish` | STORY | 无 | 审阅发布 |
| `ana` | `analyze` | STORY | 无 | 分析 |
| `poe` | `poem` | STORY | 无 | 诗歌 |
| `scr` | `script` | STORY | 无 | 脚本 |
| `cov` | `cover` | STORY | 无 | 封面提示 |
| `sty` | `style` | STORY / SCENE | 见 choice | Visual Style 下拉 |
| `folder` | — | STORY | 无 | 打开成片文件夹 |
| `clips` | — | STORY | 无 | 编辑成片片段 |
| `cover_copy` | — | STORY | 无 | 封面复制 |
| `project` | — | STORY | 无 | 打开项目 |

---

### 4.4 SCENE — 选 LM / 字段

| 短名 | 长名 | GUI 字段 | 参数 | 作用 |
|------|------|----------|------|------|
| `lm` | `prompt_choice`, `pc`, `prompt` | 选LM提示 | 见下 | 切换 LM 模板；**成功时长 prompt 上剪贴板** |
| `sty` | `style`, `visual` | Visual Style | 序号或名称 | 画面风格 |
| `snp` | `snippet` | 插入片段 | 序号或名称 | 插入导向片段 |
| `instruction` | `guide`, `导向说明` | 导向说明 | 文本 | 读/写 `{instruction}` |
| `content` | `scene_content`, `json` | scene_content | JSON 文本 | 读/写场景 JSON |
| `gen` | `generate` | 智能生成 | 无 | 用当前 LM 在 GUI 内生成（本地 LLM） |
| `cx` | `cancel` | 取消 | 无 | 关闭 SCENE（不保存） |

#### `lm` 常见选项（频道配置，以 `lm` 无参列表为准）

典型编号（心理咨询频道示例）：

| 序号 | 名称 | 常用 |
|------|------|------|
| 1 | Short Story | |
| 2 | 2 Step Story | |
| 3 | 3 Step Story | |
| 4 | **4 Step Story** | **故事视频流水线用这个** |
| 5 | Mini Story | |
| 6 | Long Story | |
| 7 | Content to Scenes | |
| 8 | Talk | |
| 9 | Conversation | |

**用法：** 先 `lm` 看列表，再 `lm 4` 或 `lm 4 Step Story`。

**成功标志：** SCENE 里「选LM提示」变成该项，「提示词预览」变长（约 400+ 字），剪贴板同步更新。**没变不要发 `gem`。**

#### `sty` 常见选项（`config.VISUAL_STYLE_OPTIONS`）

1. pixar-art cartoon + realistic  
2. pixar-art cartoon  
3. realistic  
4. cartoon  
5. 中国画(水墨/花鸟/山水)  
6. pixar-art cartoon + 中国画(水墨/花鸟/山水)  
7. realistic + 中国画(水墨/花鸟/山水)  

**用法：** `sty` → `sty 1` 或 `sty realistic`

---

### 4.5 Gemini（分镜 JSON）

| 短名 | 长名 | 窗口 | 参数 | 作用 |
|------|------|------|------|------|
| `gem` | `gemini` | SCENE（逻辑上） | 无 | 剪贴板长 prompt → CDP 开 Gemini → 生成 → **4 场 JSON 写回剪贴板** |
| `fetch` | `gemini_copy`, `copyjson` | 同左 | 无 | 不重新生成；从当前 Gemini 页读已有 JSON → 剪贴板 |
| `scnsave` | `scene_save` | SCENE | 无 | 剪贴板 JSON → scene_content → 写入 video_detail（不关窗） |

**`gem` 前置：** 已 `lm 4`，剪贴板或「提示词预览」有长 prompt。

**`gem` 成功后：** 回复 `gem ok — 4 scenes on clipboard` → 发 `scnsave`。

**Chrome：** 使用专用 CDP 配置（`HermesChromeCDP`），与日常 Chrome 可并存；首次需在该窗口登录 Google。

**HermesChromeCDP 账号（`prf` / `nbi N` / `grv N` / `itc N` 共用编号）：**

| # | 邮箱 | `--profile-directory` |
|---|------|------------------------|
| 1 | `ocreativeteen@gmail.com` | `Profile 2` |
| 2 | `creative4teen@gmail.com` | `Profile 3` |
| 3 | `triumphdt777@gmail.com` | `Default` |
| 4 | `myhomefun@gmail.com` | `Profile 4` |
| 5 | `mindstoryroom@gmail.com` | `Profile 5` |
| 6 | `bjtombj2023@gmail.com` | `Profile 6` |

启动示例（profile 6）：

```text
chrome.exe --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\HermesChromeCDP" --profile-directory="Profile 6"
```

| 短名 | 长名 | 参数 | 作用 |
|------|------|------|------|
| `prf` | `profile` | 序号或邮箱 | 选 Gemini 用 Chrome 账号（`gem`/`nbi`/`grv` 前常选） |

---

### 4.6 NotebookLM

| 短名 | 长名 | 参数 | 作用 |
|------|------|------|------|
| `nbp` | `notebooklm` | 见下 | 选导出类型，拷贝 prompt 到剪贴板（prompts） |
| `nbi` | `open_notebooklm` | Chrome 序号 | 开 NotebookLM，Generate ×3，立刻返回（不等待、不拷图） |
| `nbif` | `notebooklm_ready` | 无 | 查询 Studio：三张新 infographic ready 还是仍在 Generating |
| `itc` | `whole_story_pick` | 无参 / Chrome 号 / `pick N` | 无参：当前窗口拷最上边三张并发 Telegram；`itc N`：用 Chrome 号 N 重开 notebook 再拷图；选封面用 Telegram `1/2/3` 或 `itc pick N` |


#### `nbp` 选项结构（先 `nbp` 看编号）

四大类 × 子项（`config_prompt.NOTEBOOKLM_EXPORT_VARIANTS`）：

| 类 | 子项 | 别名示例 |
|----|------|----------|
| Image 幻灯片 | 单图 | `单图`, `image/single` |
| Image 幻灯片 | 幻灯片 | `slideshow`, `image/slideshow` |
| Video 视频 | 纯画面 | `纯画面`, `video/motion` |
| Video 视频 | 文字动画 | `video/word_in_image` |
| Speaking 主人公 | 念 speaking | `speaking/script` |
| Speaking 主人公 | 只演不讲 | `speaking/acting` |
| Speaking 主人公 | 讲解画面要点 | `speaking/visual_keypoints` |
| Voiceover 旁白 | 旁白讲述 | `voiceover/narration` |
| Voiceover 旁白 | 旁白+主持人 | `voiceover/narration_with_speakingavatar` |
| Voiceover 旁白 | 补充/总结 | `voiceover/supplement` |

**用法：** `nbp` → `nbp 3` 或 `nbp 纯画面`（编号以无参列表为准）。

**与 Grok：** 单场景 video 提示词用 **`nbv` 1…8** 或 **`grv <profile> <1…8>`**（见 §4.7），与上表 Video/Speaking/Voiceover 子项对应，但编号独立（1=纯画面 … 8=补充/总结）。

**`nbi`：** 先 `nbi` 选 Chrome 号 → `nbi 1`；需 SCENE 里已有有效 `scene_content`。与 **`grv` 共用 HermesChromeCDP（端口 9222）**——若 `grv` 已开过 Chrome，`nbi`/`itc` 直接连上去，不再另开普通 Chrome。点完 Generate ×3 立刻返回，不等待。随后用 `nbif` 查询。

**`nbif`：** 看 Studio 右侧。有 “Generating infographic...” 和转圈 = 还没 ready；最上边三张已是中文标题 + `1 source · …` = ready。

**`run_telegram_client.bat`（全自动 client）nbif 轮询：** 每 **60s** 查一次；至少 **5 分钟**、最长约 **40 分钟**。超时后：

- **不关闭 Chrome**（HermesChromeCDP / NotebookLM 留给人工查看）
- **不关闭 STORY/SCENE**（若当时还开着）
- 在 `D:\AI_MEDIA\aiagent\video_choice_queue.json` 当前条写入 `workflow_status: nbif_timeout`
- client **退出**（exit code 2）

人工确认 NotebookLM 三张图 ready 后，双击 **`cli\run_telegram_client_resume.bat`**：**不重开/关闭 Chrome**，**不验证 profile**，只要 9222 能连上就直连下载三张 → 选封面 → grv …

**`itc`：** 须 infographic 已做好。与 **`grv` 同一 HermesChromeCDP（9222）**：已开则直接连，否则自动启动。无参 → 在当前 NotebookLM 逐张打开最上边 3 张，⋮ → Download（失败则拉 lh3 URL），存到 `%USERPROFILE%\\Downloads\\whole_story_image_N_*.png`，Telegram 发 3 张请选。窗口已关掉就发 `itc N`（N 与 `nbi N` 相同的 Chrome 号）重新打开 notebook 再下载。选封面：Telegram 直接回 `1/2/3`，或 CLI 发 `itc pick 2`。选定后记下并拷到剪贴板。（旧别名 `wsp`）

---

### 4.7 Grok Imagine（分镜视频）

**Grok 账号轮换：** 每条故事默认在 **#1 `ocreativeteen`** 与 **#6 `bjtombj2023`** 间切换（`aiagent/chrome_profiles_used.json` → `grok_last`）。`gem` 仍固定 #1。无参 `grv` 自动选下一个；`grv list` 看上次/下次；`grv 6 3` 强制 profile + 变体。

| 短名 | 长名 | 参数 | 作用 |
|------|------|------|------|
| `grv` | `grok_image` | 见下 | **全自动**：开 N 标签 → 贴封面 + 出图 + 出片 + **每场景下载** |
| `gri` | `grok_image_prompt` | — | **已废弃**（并入 `grv`）；发参数会提示改用 `grv` |
| `gvd` / `grvd` | `grok_download` | 无 | 补下载各场景 mp4（`grv` 已含下载；漏了或重做时用） |
| `nbv` | — | `1`…`8` | 切换 Grok **video 提示词变体**（写入 session，供 `grv` 共用） |
| `igp` | `whole_story_image` | 无参或序号 | 贴封面进已有 Grok 标签（`grv` 已含贴封面，少用） |

#### `grv` 全自动四轮（每个 Imagine 标签）

| 轮次 | 动作 |
|------|------|
| Round 1 | 开标签 → Ctrl+V 封面 → 9:16 竖屏 |
| Round 2 | 贴场景 **出图** 提示词 → Image Submit → 等出图 |
| Round 3 | 贴 **video** 提示词 → Video Submit → 等出片 |
| Round 4 | CDP 读 ``<video>.src`` + cookie 直拉 mp4 → Downloads（与 `gvd` 共用代码） |

**前置：** 已 `lm 4`（或对应步数）；`scene_content` 有效；封面已 `itc pick`（或剪贴板有图）。

**Chrome：** 日常 Chrome + 所选 Profile（与 Gemini CDP 分离）；贴图用 Ctrl+V；改代码后重启 `open_listener.bat`。

#### `grv` 参数

| 参数 | 含义 |
|------|------|
| （无） | 自动用轮换环下一个 profile + 已存 video 变体（默认 **3**） |
| `list` / `?` | 列出轮换环、上次/下次 profile、video 变体 |
| `6` `3` | 强制 profile `6` + video 变体 `3` |
| `prep` | 仅向已有标签贴封面（不重新开标签、不出图出片） |

**示例：** `grv`（自动 #1↔#6 轮换 + 变体 3） / `grv 6 5` 强制 bjtombj + 变体 5

**场景数：** `scnsave` 之后以当前条 **`video_detail.scene_content`** 数组长度为准（`grv` / `nbv` 开几个标签都看这个）。`gem` 之前尚无 scene_content 时，从 LM 长 prompt 解析期望条数校验。

#### Video 提示词变体 1…8（`GROK_SCENE_VIDEO_NB_VARIANTS`）

对应 NotebookLM 的 Video / Speaking / Voiceover（**不含** Image）。`grv`、`nbv` 共用；记在 `aiagent/grok_scene_video_nb.json` 的 `video_nb_index`。

| # | 类 | 变体 | 说明 |
|---|-----|------|------|
| 1 | Video | `motion` | 纯画面 · 动作/表情/场景演进（无口播） |
| 2 | Video | `word_in_image` | 文字动画 · 关键词/思想泡泡（无口播） |
| 3 | Speaking | `script` | 念 speaking · 第一人称口播 **（默认）** |
| 4 | Speaking | `acting` | 只演不讲 · 神态/肢体/思考 |
| 5 | Speaking | `visual_keypoints` | 讲解画面要点 · 非念图内文字 |
| 6 | Voiceover | `narration` | 旁白讲述 · 第三人叙述 |
| 7 | Voiceover | `narration_with_speakingavatar` | 旁白讲述 · 主持人说话 |
| 8 | Voiceover | `supplement` | 补充/总结 · 衔接与点评 |

**用法：** `nbv` 看列表 → `nbv 5` 切换；或 `grv 1 5` 一次指定。

#### `gvd` / `grvd`

**补下载**（与 `grv` Round 4 同路数）：等各标签 video 已出片，CDP 读 `<video>.src` + grok.com cookie 直拉 mp4。`grv` 成功后会自动下载并记入 session，通常**不必再发 `gvd`**。

**与 `nbp` 的区别：** `nbp` = Image 类（整篇封面/幻灯片，给 `nbi`）；`grv` Round 3 = 单场景 video 类（上表 1…8）。`nbp` 的 Video/Speaking/Voiceover 子项与 `nbv` 1…8 同源（`NOTEBOOKLM_EXPORT_VARIANTS`），但 **Grok 流水线用 `nbv`/`grv` 的编号**，不是 `nbp` 的平铺序号。

#### `gri`（已并入 `grv`）

场景图提示词（Image to Detail-Single-Step-Image 1…4）现由 `grv` Round 2 自动粘贴。若仍发 `gri 1` 会提示改发 `grv 1`。

---

### 4.8 成片与发布

| 短名 | 长名 | 窗口 | 参数 | 作用 |
|------|------|------|------|------|
| `vc` | `video_concat` | STORY/SCENE | 无 | 按 `gvd` 记录的 clip 拼接 + 水印 → gen_video |
| `vp` | `video_publish` | STORY/SCENE | 见下 | 上传 YouTube（立即 unlisted） |

**`vp` 参数：** `vp` 列描述来源 → `vp 1` 或 `vp default`（用对话框默认素材）。

成功后队列条目标为已完成，听筒会提示下一条 `pick N`。

---

## 5. 短名 ↔ 长名 速查

| 短名 | 长名 |
|------|------|
| `lm` | `prompt_choice` |
| `sty` | `style` |
| `snp` | `snippet` |
| `prf` | `profile` |
| `gem` | `gemini` |
| `fetch` | `gemini_copy` |
| `scnsave` | `scene_save` |
| `nbp` | `notebooklm` |
| `nbi` | `open_notebooklm` |
| `nbif` | `notebooklm_ready` |
| `itc` | `whole_story_pick` |
| `igp` | `whole_story_image` |
| `grv` | `grok_image` |
| `gri` | `grok_image_prompt`（已并入 `grv`） |
| `gvd` / `grvd` | `grok_download` |
| `nbv` | Grok video 变体 1…8（session） |
| `vc` | `video_concat` |
| `vp` | `video_publish` |
| `pick` | `story_pickup` |
| `scn` | `scene` / `go` |
| `pub` | `publish` |
| `ana` | `analyze` |
| `poe` | `poem` |
| `scr` | `script` |
| `cov` | `cover` |
| `gen` | `generate` |
| `cx` | `cancel` |
| `win` | `screen` |

中文别名也可用，例如：`选LM提示`、`保存`、`分析`、`场景`（按钮）、`拼接` 等（见 `cli/commands.py` 的 `_ALIASES`）。

---

## 6. Choice 命令通用规则

适用于：`lm` `sty` `snp` `nbp` `prf` `nbi` `nbif` `itc` `grv` `igp` `nbv` `vp` `pick`

**`grv` 特例：** 第二个数字是 **video 变体 1…8**，不是 Chrome profile 列表项。例：`grv 1 5` = profile 1 + 变体 5。

1. **无参数** → 单列选项，格式：`cmd N: (说明)`，例如 `sty 2: (pixar-art cartoon)`
2. **数字** → 选第 N 项（`1` 起）
3. **名称 / 片段** → 模糊匹配括号里的文字
4. **全角数字** `１` `２` 会自动转成半角  

---

## 7. 常见错误

| 现象 | 处理 |
|------|------|
| `lm` bridge timeout | 关 SCENE 重开；或重启 GUI 后再 `scn` → `lm 4` |
| `lm` 成功但下拉没变 | 没选上，**不要 `gem`** |
| `gem` prompt too short | 先 `lm 4` |
| `scnsave` 不是 JSON | 先 `gem` 或 `fetch` |
| `pick` 已关掉 | 手工 GUI 会话；直接 `scn` 继续 |
| `scn` 打不开 | STORY 要在；勿挡 GUI；再发一次 `scn` |
| `grv` 没有 LM | 先 `lm 4` |
| `grv` 没有封面图 | 先 `itc pick`（或 Copy image 到剪贴板） |
| `grv` video 提示词为空 | 确认 `scnsave` 后 `scene_content` 为有效 JSON；**SCENE 须打开**（client/resume 会在 grv 前自动 `scn`；若 STORY 也关了会从队列重开） |
| `gri` 提示已合并 | 改发 `grv 1`（或 `grv 1 3` 指定变体） |
| `gvd` / `grvd` 没有 mp4 | 先等 `grv` 跑完（已含下载）；或单独 `gvd` 补下 |

---

## 8. 文件位置

| 路径 | 说明 |
|------|------|
| `cli/commands.py` | 命令注册与实现 |
| `cli/gui_session.py` | 听筒「可发」列表 |
| `cli/bridge.py` | CLI ↔ GUI 文件桥 |
| `cli/CLI_REFERENCE.md` | 本文档 |
| `D:\AI_MEDIA\aiagent\Hermes_CLI_Agent_prompt.md` | Hermes 自动化提示词 |

---

*文档随代码生成；选项以各命令无参运行时的实时列表为准。*

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

`lm` `sty` `snp` `prf` `gem` `pst` `save` `nbp` `nbi` `nbif` `itc` `igp` `gr` `gri` `sc` `grv` `grvd` `nbv` `vc` `vp` `sync`

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
pst                # 剪贴板 JSON 写入 scene_content
save               # 保存 SCENE
nbp 1               # 选 NotebookLM 导出类型（先无参看列表）
nbi 1              # 选 Chrome 号，开 NotebookLM，Generate ×3 后立刻返回（不等待）
nbif               # 查询三张新 infographic 是否 ready
itc                # 当前 NotebookLM 窗口拷最上边三张；窗口关了就 itc 1（Chrome 号）
itc pick 2         # 选定第 2 张封面（Telegram 直接回 2 也可以）
igp                # 把已选封面拷剪贴板并贴进所有 Grok 标签
gr 1               # 选 Chrome 号，按 LM 场景数开 Grok Imagine 标签
gri 1 … gri 4      # 各场景 Image 出图（Image 模式）
sc 1 … sc 4        # 场景 i + Video/纯画面 提示词 → 剪贴板（再 grv i）
grv 1 … grv 4      # 各标签 Video 出片
grvd               # 下载全部 mp4 到 Downloads（别名 gvd）
vc                 # 拼接成片
vp default         # 上传 YouTube
pick next          # 下一条
```

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
| `pst` | `paste_scene`, `paste_json` | SCENE | 无 | 剪贴板 JSON → `scene_content` |

**`gem` 前置：** 已 `lm 4`，剪贴板或「提示词预览」有长 prompt。

**`gem` 成功后：** 回复 `gem ok — 4 scenes on clipboard` → 发 `pst`。

**Chrome：** 使用专用 CDP 配置（`HermesChromeCDP`），与日常 Chrome 可并存；首次需在该窗口登录 Google。

| 短名 | 长名 | 参数 | 作用 |
|------|------|------|------|
| `prf` | `profile` | 序号或邮箱 | 选 Gemini 用 Chrome 账号（`gem`/`nbi`/`gr` 前常选） |

---

### 4.6 NotebookLM

| 短名 | 长名 | 参数 | 作用 |
|------|------|------|------|
| `nbp` | `notebooklm` | 见下 | 选导出类型，拷贝 prompt 到剪贴板（prompts） |
| `nbi` | `open_notebooklm` | Chrome 序号 | 开 NotebookLM，Generate ×3，立刻返回（不等待、不拷图） |
| `nbif` | `notebooklm_ready` | 无 | 查询 Studio：三张新 infographic ready 还是仍在 Generating |
| `itc` | `whole_story_pick` | 无参 / Chrome 号 / `pick N` | 无参：当前窗口拷最上边三张并发 Telegram；`itc N`：用 Chrome 号 N 重开 notebook 再拷图；选封面用 Telegram `1/2/3` 或 `itc pick N` |
| `nbv` | — | `纯画面` 等 | 可选：仅重拷 Video·纯画面（`sc i` 已含；场景已选时用） |
| `igp` | `whole_story_image` | 无参或序号 | 无参：贴已选封面进 Grok；`igp N` 选第 N 张并贴 |

#### `nbp` 选项结构（先 `nbp` 看编号）

四大类 × 子项（`config_prompt.NOTEBOOKLM_EXPORT_VARIANTS`）：

| 类 | 子项 | 别名示例 |
|----|------|----------|
| Image 幻灯片 | 单图 | `单图`, `image/single` |
| Image 幻灯片 | 幻灯片 | `slideshow`, `image/slideshow` |
| Video 视频 | 纯画面 | **`纯画面`**, `video/motion`, `nbv` |
| Video 视频 | 文字动画 | |
| Speaking 主人公 | 念 speaking | |
| Speaking 主人公 | 只演不讲 | |
| Speaking 主人公 | 讲解画面要点 | |
| Voiceover 旁白 | 旁白讲述 | |
| Voiceover 旁白 | 旁白+主持人 | |
| Voiceover 旁白 | 补充/总结 | |

**用法：** `nbp` → `nbp 3` 或 `nbp 纯画面`

**`nbi`：** 先 `nbi` 选 Chrome 号 → `nbi 1`；需 SCENE 里已有有效 `scene_content`。点完 Generate ×3 立刻返回，不等待。随后用 `nbif` 查询。

**`nbif`：** 看 Studio 右侧。有 “Generating infographic...” 和转圈 = 还没 ready；最上边三张已是中文标题 + `1 source · …` = ready。

**`itc`：** 须 infographic 已做好。无参 → 用**当前已打开**的 NotebookLM，逐张打开最上边 3 张，右键 Copy image，存到 `D:\AI_MEDIA\working\YYYYMMDDHHMMSS.png`，Telegram 发 3 张请选。窗口已关掉就发 `itc N`（N 与 `nbi N` 相同的 Chrome 号）重新打开已有 notebook 再拷图。选封面：Telegram 直接回 `1/2/3`，或 CLI 发 `itc pick 2`。选定后记下并拷到剪贴板。（旧别名 `wsp`）

**`igp`：** 无参 → 把 `itc` 已选封面贴进所有 Grok 标签；`igp N` 可一步选第 N 张并贴。（旧别名 `wsi`）

---

### 4.7 Grok Imagine（分镜视频）

| 短名 | 长名 | 参数 | 作用 |
|------|------|------|------|
| `gr` | `grok_image` | Chrome 序号 | 按 `lm` 记录的场景数开 N 个 `grok.com/imagine` 标签 |
| `gri` | `grok_image_prompt` | 1–4 或名称 | 场景图 prompt → Image 模式 → 出图（贴字校验 + 等待） |
| `sc` | `scene_choice` | 见下 | 场景 `1/2/…`：底栏按钮 + **Video/纯画面** 拷剪贴板；`all` 只改按钮 |
| `grv` | `grok_video` | `1`…`N` 或 `download` | Video 模式出片（贴字校验 + 等待） |
| `grvd` / `gvd` | — | 无 | 同 `grv download`：各场景 mp4 → Downloads |
| `nbv` | — | `纯画面` | 可选：仅按**当前**场景再拷 Video/纯画面（`sc i` 已含此步） |

#### `gri` 选项（`DIRECT_VIDEO_PROMPT_CHOICES`）

1. Image to Detail-Single-Step-Image 1  
2. Image to Detail-Single-Step-Image 2  
3. Image to Detail-Single-Step-Image 3  
4. Image to Detail-Single-Step-Image 4  
5. Image to Video (protagonist reflection & interaction  
6. Image to Video (narrator voiceover only  
7. Image to Video (atmospheric motion only …  
（完整列表以 `gri` 无参输出为准）

**用法：** `gri 1` … `gri 4` 各场景出图；`sc i` → `grv i` 各场景出片。

#### `sc` 参数

| 值 | 含义 |
|----|------|
| `all` | 底栏切到 All（**不**拷 video 提示词） |
| `1` `2` `3` `4` | 场景按钮切到第 N 场，并拷 **Video / 纯画面** 到剪贴板（等同手工：场景按钮 → NotebookLM ▼ → Video → 纯画面） |

**与 `nbp` 的区别：** `nbp 1` = Image / 单图（整篇封面，给 `nbi`）；`sc i` = 单场景 Video / 纯画面（给 `grv i`）。`nbv` 仍可用，只在已选好场景时单独重拷提示词。

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
| `pst` | `paste_scene` |
| `nbp` | `notebooklm` |
| `nbi` | `open_notebooklm` |
| `nbif` | `notebooklm_ready` |
| `itc` | `whole_story_pick` |
| `igp` | `whole_story_image` |
| `gr` | `grok_image` |
| `gri` | `grok_image_prompt` |
| `sc` | `scene_choice` |
| `grv` | `grok_video` |
| `grvd` / `gvd` | `grv download` |
| `nbv` | `notebooklm 纯画面` |
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

适用于：`lm` `sty` `snp` `nbp` `prf` `nbi` `nbif` `itc` `gr` `igp` `gri` `sc` `grv` `vp` `pick`

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
| `pst` 不是 JSON | 先 `gem` 或 `fetch` |
| `pick` 已关掉 | 手工 GUI 会话；直接 `scn` 继续 |
| `scn` 打不开 | STORY 要在；勿挡 GUI；再发一次 `scn` |
| `gr` 没有 LM | 先 `lm 4` |
| `grvd` / `gvd` 没有 mp4 | 各场景先 `grv 1`…`grv N` 等出完 |

---

## 8. 文件位置

| 路径 | 说明 |
|------|------|
| `cli/commands.py` | 命令注册与实现 |
| `cli/gui_session.py` | 听筒「可发」列表 |
| `cli/bridge.py` | CLI ↔ GUI 文件桥 |
| `cli/CLI_REFERENCE.md` | 本文档 |
| `aiagent/Hermes_CLI_Agent_prompt.md` | Hermes 自动化提示词 |

---

*文档随代码生成；选项以各命令无参运行时的实时列表为准。*

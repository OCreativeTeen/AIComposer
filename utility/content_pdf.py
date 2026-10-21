"""全集生成：把本集各场景写成 NotebookLM 来源文件 content.pdf（场景图 + 勾选的栏目）。

用 PyMuPDF (fitz) 的 Story 排版（同旧「拷贝PDF」用的 fitz），字体用系统微软雅黑，中文可显示。
栏目文字与提示词完全一致：直接取 ``config_prompt.slide_flow_scene_payload`` 的结果，
所以 <N> 去除、讲话 / 场景叙事 / 讲述内容 的名称都和提示词同一套规则。
"""
from __future__ import annotations

import html
import os
import tempfile

CONTENT_PDF_PATH = r"D:\AI_MEDIA\working\content.pdf"
CONTENT_PDF_NAME = "content.pdf"

# 提示词里的英文栏名 → PDF 里的「中文 / English」栏名
FIELD_LABELS = {
    "Keyword hint": "关键词 / Keyword hint",
    "Shown": "场景描述 / Shown",
    "Actors": "人物 / Actors",
    "Silent actors": "人物（不说话，只表演）/ Silent actors",
    "Dialogue": "讲话 / Dialogue",
    "Also dialogue": "讲话（续）/ Also dialogue",
    "Scene narration": "场景叙事 / Scene narration",
    "Narration content": "讲述内容 / Narration content",
}

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
)


def _font_file() -> str:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return ""


def _scene_image(scene: dict) -> str:
    for key in ("clip_image", "clip_image_last"):
        path = scene.get(key) if isinstance(scene, dict) else ""
        if isinstance(path, str) and path and os.path.isfile(path):
            return path
    return ""


def scenes_have_images(scenes: list) -> bool:
    """勾了「场景图片」时，content.pdf 里是否真的会有图（至少一场有 clip_image / clip_image_last 文件）。"""
    return any(_scene_image(s) for s in (scenes or []) if isinstance(s, dict))


def _split_fields(text: str) -> list[tuple[str, str]]:
    """``show_this_content`` 的多行 "Label: text" → [(label, text)]；续行并入上一栏。"""
    out: list[tuple[str, str]] = []
    for line in (text or "").split("\n"):
        hit = next((k for k in FIELD_LABELS if line.startswith(k + ": ")), None)
        if hit:
            out.append((FIELD_LABELS[hit], line[len(hit) + 2:].strip()))
        elif out:
            out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
        elif line.strip():
            out.append(("", line.strip()))
    return out


def build_content_pdf(
    scenes: list,
    *,
    narrative: str = "story",
    use_visual: bool = True,
    use_speaking: bool = True,
    use_actor: bool = False,
    use_image: bool = False,
    keywords: bool = False,
    actor_override: str = "",
    dest: str = CONTENT_PDF_PATH,
    episodes: list | None = None,
) -> str:
    """生成 content.pdf（覆盖），返回路径。

    ``episodes``（和 scenes 等长，每场所属的集名）跨了不止一集时，每集开头加「第N集 / Episode N」分隔标题；
    场景编号始终是 1..M 连续，不按集重新编号。
    """
    import fitz
    from PIL import Image

    import config_prompt

    scenes = [s for s in (scenes or []) if isinstance(s, dict)]
    if not scenes:
        raise ValueError("本集没有场景")
    has_speaker = config_prompt._prompt_has_speaker(narrative, use_actor, scenes)
    silent = (not has_speaker) and config_prompt.prompt_silent_cast(narrative, use_actor, scenes)
    payload = config_prompt.slide_flow_scene_payload(
        scenes,
        use_visual=use_visual,
        use_speaking=use_speaking,
        use_actor=has_speaker,
        keywords=keywords,
        narrative=narrative,
        silent_cast=silent,
    )
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="aicomposer_content_")
    font = _font_file()
    css = (
        (f"@font-face {{font-family: cjk; src: url({os.path.basename(font)});}}\n" if font else "")
        + "* {font-family: cjk, sans-serif;}\n"
        "body {font-size: 11pt; line-height: 1.45;}\n"
        "h1 {font-size: 18pt; margin: 18pt 0 4pt 0; color: #444444;}\n"
        "h2 {font-size: 15pt; margin: 14pt 0 6pt 0;}\n"
        "p.label {font-weight: bold; margin: 6pt 0 1pt 0;}\n"
        "p.text {margin: 0 0 4pt 0;}\n"
        "img {width: 100%;}\n"
    )
    parts = ["<body>"]
    override = (actor_override or "").strip()
    groups = [str(g or "").strip() for g in (episodes or [])]
    multi = len(groups) == len(scenes) and len(set(groups)) > 1
    last_group = None
    for n, (scene, item) in enumerate(zip(scenes, payload), start=1):
        if multi and groups[n - 1] != last_group:
            last_group = groups[n - 1]
            parts.append(f"<h1>第{html.escape(last_group)}集 / Episode {html.escape(last_group)}</h1>")
        parts.append(f"<h2>场景 {n} / Scene {n}</h2>")
        if use_image:
            src = _scene_image(scene)
            if src:
                name = f"scene_{n}.jpg"
                with Image.open(src) as im:
                    rgb = im.convert("RGB")
                    rgb.thumbnail((1600, 1600))
                    rgb.save(os.path.join(tmp, name), "JPEG", quality=85)
                parts.append(f'<p><img src="{name}"/></p>')
        fields = _split_fields(item.get("show_this_content", ""))
        if override and (has_speaker or silent):
            fields.append(("换成 / People override", f"draw every person as {override}"))
        for label, text in fields:
            if label:
                parts.append(f'<p class="label">{html.escape(label)}:</p>')
            body = html.escape(text).replace("\n", "<br/>")
            parts.append(f'<p class="text">{body}</p>')
    parts.append("</body>")
    archive = fitz.Archive(tmp)
    if font:
        archive.add(fitz.Archive(os.path.dirname(font)))
    story = fitz.Story(html="".join(parts), user_css=css, archive=archive)
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (50, 50, -50, -50)
    import io

    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    # ??????????????? 19 MB?
    doc = fitz.open("pdf", buf.getvalue())
    try:
        doc.subset_fonts()
        data = doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()
    part = dest + ".part"
    with open(part, "wb") as f:
        f.write(data)
    os.replace(part, dest)
    try:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass
    return dest


# ---------------------------------------------------------------------------
# actor.pdf：本集出场人物（全名 + 形象图），给 NotebookLM 对照人物外貌。
# ---------------------------------------------------------------------------
ACTOR_PDF_PATH = r"D:\AI_MEDIA\working\actor.pdf"
ACTOR_PDF_NAME = "actor.pdf"


def portrait_stem(name: str) -> str:
    """同 ``wf_actors._portrait_stem``：/ 换成 _，去掉文件名不允许的字符。"""
    stem = (name or "").strip().replace("\\", "/").replace("/", "_")
    for ch in '<>:"|?*':
        stem = stem.replace(ch, "_")
    return stem.strip(" .")


def _style_or_current(style) -> str:
    if style is not None:
        return style
    try:
        import project_manager

        return project_manager.current_visual_style()
    except Exception:
        return ""


def actor_portrait_path(role: str, name: str, avatar_dir: str = "", style: str | None = None) -> str:
    """同 ``wf_actors._actor_entry_portrait``：讲员在 config.AVATAR_PATH，人物在项目 avatar 目录。找不到返回 ""。"""
    import config

    name = (name or "").strip()
    if not name:
        return ""
    style = _style_or_current(style)
    if role == "host":
        # 讲员：avatar/<风格>/ → avatar/Realistic/ → avatar/，每一层先全名、再前三段。
        names = [name]
        bits = [b for b in name.split("/") if b]
        if len(bits) >= 3:
            names.append("/".join(bits[:3]))
        return config.find_avatar_png([portrait_stem(n) for n in names], style)
    # 项目人物：<项目>/avatar/<风格>/ → <项目>/avatar/ → 故事预览存图的 avatar/story/<风格>/ → avatar/story/。
    # （故事预览里项目还没有 avatar 目录时，人物图贴进 AVATAR_PATH/story；不退到通用头像库。）
    stem = portrait_stem(name)
    if not stem:
        return ""
    token = config.visual_style_token(style)
    story_dir = os.path.join(config.AVATAR_PATH, "story")
    folders = []
    for base in ([avatar_dir] if avatar_dir else []) + [story_dir]:
        folders += ([os.path.join(base, token)] if token else []) + [base]
    for folder in folders:
        path = config.find_image_by_stem(folder, stem)  # .png / .jpg / .jpeg / .webp，.png 优先
        if path:
            return path
    return ""


# 「换成」覆盖 → D:\AI_MEDIA\avatar\<gender>_<era>_<ethnicity>.png（例：中国人 · 民国 + woman → woman_民国_chinese.png）。
# 族裔沿用头像库已有的词：chinese / english（西方人）；新加 japanese / black / tribal。
OVERRIDE_ETHNICITY = {"中国人": "chinese", "日本人": "japanese", "西方人": "english", "黑人": "black", "原始部落人": "tribal"}


def override_label_short(label: str) -> str:
    """'中国人 · 民国' → '中国人·民国'（提示词里用）。"""
    return "".join((label or "").split())


def override_portrait_tokens(label: str) -> tuple[str, str]:
    """「换成」选项 → (era, ethnicity) 文件名片段；不覆盖 / 不认识返回 ("", "")。"""
    short = override_label_short(label)
    if not short:
        return "", ""
    if "·" in short:
        people, era = short.split("·", 1)
    else:
        people, era = short, ""
    eth = OVERRIDE_ETHNICITY.get(people, "")
    if not eth:
        return "", ""
    if not era:
        era = people[:-1] if people.endswith("人") else people  # 原始部落人 → 原始部落
    return era, eth


def override_portrait_path(name: str, override_label: str, style: str | None = None) -> tuple[str, str]:
    """覆盖时这个人的形象图：返回 (找到的路径或 "", 期望的文件名)。性别取名字第一段 man / woman。

    「现代」先找 ``<gender>_现代_<eth>.png``，没有再找按名字年龄段的 ``<gender>_<age>_<eth>.png``（头像库原有的现代人像）。
    """
    import config

    era, eth = override_portrait_tokens(override_label)
    bits = [b.strip().lower() for b in (name or "").split("/") if b.strip()]
    gender = bits[0] if bits and bits[0] in ("man", "woman") else ""
    if not era or not gender:
        return "", ""
    exts = config.AVATAR_IMAGE_EXTS_LABEL
    tries = [f"{gender}_{era}_{eth}"]
    if era == "现代" and len(bits) >= 2:
        tries.append(f"{gender}_{bits[1]}_{eth}")
    expected = f"{tries[0]}.{exts}"
    # 每一层（avatar/<风格>/ → Realistic/ → 根目录）先试时代图，再试「现代」的年龄段图；每个 stem 接受四种格式。
    path = config.find_avatar_image(tries, _style_or_current(style))
    if path:
        return os.path.abspath(path), expected
    return "", " 或 ".join(f"{t}.{exts}" for t in tries)


def actor_image_for(role: str, name: str, avatar_dir: str = "", override_label: str = "", style: str | None = None) -> str:
    """人物形象图：有「换成」覆盖时按覆盖查头像库（找不到就没有图，并记下期望的文件名），否则同人物栏。"""
    import config

    if override_portrait_tokens(override_label)[0]:
        path, expected = override_portrait_path(name, override_label, style)
        if not path:
            where = " → ".join(config.avatar_style_dirs(_style_or_current(style)))
            print(f"[portrait] 换成 {override_label_short(override_label)}：{name} 没有形象图，期望 "
                  f"{expected or '(名字里没有 man / woman，无法确定性别)'}（找过 {where}）")
        return path
    return actor_portrait_path(role, name, avatar_dir, style)


MAX_INPUT_IMAGES = 5  # Grok Imagine 编辑最多 5 张输入图（xAI 文档：image edit up to 5 source images）


def scene_actor_reference_images(
    scene: dict, avatar_dir: str = "", base_image: str = "", max_actors: int = 4, override_label: str = "",
    style: str | None = None,
) -> list:
    """图片提示：当前场景 Actors（按顺序，最多 4 位）各自的形象图，查法同 actor.pdf / 人物栏。

    返回 [{label, role, name, image, image_no}]。``image_no`` 是这张图在发出去的图里的序号（从 1 起）：
    有基础图时基础图是第 1 张，人物从第 2 张起；没有形象图的人 image 为 ""、image_no 为 0（不占序号）。
    两个人用的是同一个文件时共用一个序号。总数不超过 ``MAX_INPUT_IMAGES``，超出的人当作没有图。
    ``override_label``（「换成」选项，如 '中国人 · 民国'）不为空时，形象图按覆盖从头像库查，每行带 ``override``。
    """
    short = override_label_short(override_label) if override_portrait_tokens(override_label)[0] else ""
    import project_manager

    if not isinstance(scene, dict):
        return []
    text = project_manager.actor_text_for_generation(scene.get("actor") or "")
    rows = []
    for row in project_manager.active_actor_entries(text):
        body, _motion = project_manager.split_actor_motion((row.get("body") or "").strip())
        body = body.strip()
        if not body or project_manager.actor_is_absent(body):
            continue
        role = "host" if row.get("role") == "host" else "person"
        rows.append({"label": "讲员" if role == "host" else (row.get("label") or "人物"), "role": role, "name": body,
                     "override": short})
        if len(rows) >= max_actors:
            break
    sent = [os.path.abspath(base_image)] if base_image and os.path.isfile(base_image) else []
    for row in rows:
        path = actor_image_for(row["role"], row["name"], avatar_dir, override_label, style)
        row["image"] = ""
        row["image_no"] = 0
        if not path:
            continue
        path = os.path.abspath(path)
        if path in sent:
            row["image"], row["image_no"] = path, sent.index(path) + 1
            continue
        if len(sent) >= MAX_INPUT_IMAGES:
            continue
        sent.append(path)
        row["image"], row["image_no"] = path, len(sent)
    return rows


def _write_pdf(stories_html: list, css: str, archive) -> bytes:
    """每段 html 从新的一页开始（一人一页，名字和图不分开）。"""
    import io

    import fitz

    mediabox = fitz.paper_rect("a4")
    where = mediabox + (50, 50, -50, -50)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    for body in stories_html:
        story = fitz.Story(html=body, user_css=css, archive=archive)
        more = True
        while more:
            dev = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(dev)
            writer.end_page()
    writer.close()
    doc = fitz.open("pdf", buf.getvalue())
    try:
        doc.subset_fonts()
        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()


def build_actor_pdf(
    scenes: list, *, avatar_dir: str = "", dest: str = ACTOR_PDF_PATH, override_label: str = "",
    style: str | None = None,
) -> tuple[str, list]:
    """本集所有场景里出现的人物写成 actor.pdf（覆盖）：一人一页，全名标题 + 形象图（没有图就注明 no image）。

    ``override_label``（「换成」选项）不为空时，形象图按覆盖从头像库查（同图片提示），每页注明换成什么。
    人物按全名去重（名字和 content.pdf「人物 / Actors」栏里的一样）。没有人物就不生成，返回 ("", [])，
    并删掉旧的 actor.pdf，免得上传过期文件。返回 (路径, [{name, role, label, image}])。
    """
    import fitz
    from PIL import Image

    import config_prompt

    cast = config_prompt.episode_actor_cast(scenes)
    if not cast:
        try:
            if os.path.isfile(dest):
                os.remove(dest)
        except OSError:
            pass
        return "", []
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="aicomposer_actor_")
    font = _font_file()
    css = (
        (f"@font-face {{font-family: cjk; src: url({os.path.basename(font)});}}\n" if font else "")
        + "* {font-family: cjk, sans-serif;}\n"
        "body {font-size: 12pt; line-height: 1.45;}\n"
        "h1 {font-size: 20pt; margin: 0 0 4pt 0;}\n"
        "p.role {color: #555555; margin: 0 0 10pt 0;}\n"
        "p.note {color: #aa0000; margin: 10pt 0 0 0;}\n"
        "img {width: 70%;}\n"
    )
    pages = []
    out = []
    for n, row in enumerate(cast, start=1):
        image = actor_image_for(row["role"], row["name"], avatar_dir, override_label, style)
        role_line = "讲员 / Host (narrator)" if row["role"] == "host" else "人物 / Person"
        if override_portrait_tokens(override_label)[0]:
            role_line += f"　（换成{override_label_short(override_label)} / overridden to {override_label_short(override_label)}）"
        parts = [
            "<body>",
            f"<h1>{html.escape(row['name'])}</h1>",
            f'<p class="role">{html.escape(role_line)}</p>',
        ]
        if image:
            fname = f"actor_{n}.jpg"
            with Image.open(image) as im:
                rgb = im.convert("RGB")
                rgb.thumbnail((1200, 1200))
                rgb.save(os.path.join(tmp, fname), "JPEG", quality=88)
            parts.append(f'<p><img src="{fname}"/></p>')
        else:
            parts.append('<p class="note">no image（没有形象图）</p>')
        # 一人一页（每段 html 另起一页），名字和图在同一页，不再补空行。
        parts.append("</body>")
        pages.append("".join(parts))
        out.append({**row, "image": image})
    archive = fitz.Archive(tmp)
    if font:
        archive.add(fitz.Archive(os.path.dirname(font)))
    data = _write_pdf(pages, css, archive)
    part = dest + ".part"
    with open(part, "wb") as f:
        f.write(data)
    os.replace(part, dest)
    try:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass
    return dest, out


# ---------------------------------------------------------------------------
# 节目生成（STORY 窗口）：把分析内容写成 NotebookLM 来源 content.pdf（纯文字）。
# ---------------------------------------------------------------------------
def build_text_pdf(text: str, *, title: str = "", dest: str = CONTENT_PDF_PATH) -> str:
    """分析内容 → PDF（覆盖），返回路径。Markdown 的 # 标题行变成小标题，其余按段落排，空行分段。"""
    import re

    import fitz

    body = (text or "").strip()
    if not body:
        raise ValueError("还没有分析内容。")
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    font = _font_file()
    css = (
        (f"@font-face {{font-family: cjk; src: url({os.path.basename(font)});}}\n" if font else "")
        + "* {font-family: cjk, sans-serif;}\n"
        "body {font-size: 11pt; line-height: 1.5;}\n"
        "h1 {font-size: 17pt; margin: 0 0 10pt 0;}\n"
        "h2 {font-size: 14pt; margin: 12pt 0 4pt 0;}\n"
        "p {margin: 0 0 6pt 0;}\n"
    )
    parts = ["<body>"]
    if (title or "").strip():
        parts.append(f"<h1>{html.escape(title.strip())}</h1>")
    para: list[str] = []

    def flush() -> None:
        if para:
            parts.append("<p>" + "<br/>".join(html.escape(x) for x in para) + "</p>")
            para.clear()

    for line in body.splitlines():
        s = line.rstrip()
        m = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", s)
        if m:
            flush()
            parts.append(f"<h2>{html.escape(m.group(1).strip())}</h2>")
        elif not s.strip():
            flush()
        else:
            para.append(s)
    flush()
    parts.append("</body>")
    archive = fitz.Archive(os.path.dirname(font)) if font else fitz.Archive()
    data = _write_pdf(["".join(parts)], css, archive)
    part = dest + ".part"
    with open(part, "wb") as f:
        f.write(data)
    os.replace(part, dest)
    return dest

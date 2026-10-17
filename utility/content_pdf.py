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
) -> str:
    """生成 content.pdf（覆盖），返回路径。"""
    import fitz
    from PIL import Image

    import config_prompt

    scenes = [s for s in (scenes or []) if isinstance(s, dict)]
    if not scenes:
        raise ValueError("本集没有场景")
    has_speaker = config_prompt._prompt_has_speaker(narrative, use_actor, scenes)
    payload = config_prompt.slide_flow_scene_payload(
        scenes,
        use_visual=use_visual,
        use_speaking=use_speaking,
        use_actor=has_speaker,
        keywords=keywords,
        narrative=narrative,
    )
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="aicomposer_content_")
    font = _font_file()
    css = (
        (f"@font-face {{font-family: cjk; src: url({os.path.basename(font)});}}\n" if font else "")
        + "* {font-family: cjk, sans-serif;}\n"
        "body {font-size: 11pt; line-height: 1.45;}\n"
        "h2 {font-size: 15pt; margin: 14pt 0 6pt 0;}\n"
        "p.label {font-weight: bold; margin: 6pt 0 1pt 0;}\n"
        "p.text {margin: 0 0 4pt 0;}\n"
        "img {width: 100%;}\n"
    )
    parts = ["<body>"]
    override = (actor_override or "").strip()
    for n, (scene, item) in enumerate(zip(scenes, payload), start=1):
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
        if override and has_speaker:
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

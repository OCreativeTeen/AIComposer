"""t277: STORY 窗材料行下面那一行小字提示：跟着选中的东西变（PDF / 分析报告 / 图片 / 音频 / 视频 / 文字稿 / 什么都没选），
而且总是一行放得下（窗口约 1000 像素宽时量字宽，放不下就从后往前去掉「 · 」分开的小段，再不行截断加「…」）。

步数和「共 N 集」之间不再放任何说明（t273 那行「PDF 一页一个场景，步数不用」去掉了），要说的话放到这一行。
"""
from __future__ import annotations

from typing import Callable

SEP = " · "

NONE = "把 PDF / 图片 / 音频 / mp4 拖到这里 · 单击选作材料 · 双击打开 · 右键更多 · Delete 删除"
ANALYZED = "分析报告：可直接改 · 再双击「分析报告」重新分析 · 点「材料」看 PDF / 图片 / 音视频"
PDF_PAGE_STEPS = "PDF：一页一个场景，步数不用 · 右边选开始/结束页 · 双击查看 · 右键「抽图对场景」"
PDF_PAGE = "PDF：一页一个场景 · 右边选开始/结束页 · 双击查看 · 右键「抽图对场景」"
PDF_TEXT = "PDF 当文字内容（整份当故事读）· 右边选开始/结束页 · 双击查看 · 右键「抽图对场景」"
IMAGE = "图片：第一张是封面 · 拖动排序 · 双击看图 · 右键设封面 / 移除 · Delete 删除（文件保留）"
AUDIO = "音频：▶ 播放 · 双击打开 · 右键转录 · 拖新音频 / mp4 换掉它"
VIDEO = "视频：▶ 播放 · 双击打开 · 右键转录 / 抽幻灯片对场景 · 拖新音频 / mp4 换掉它"
AUDIO_OVERVIEW = "语音概览：单击选作材料 · ▶ 播放 · 双击打开 · 右键拷到剪贴板"
VIDEO_OVERVIEW = "视频概览：单击选作材料 · ▶ 播放 · 双击打开 · 右键「抽幻灯片对场景」"
TRANSCRIPT = "文字稿：双击打开 · 右键拷到剪贴板 / 只分析这一项 / 重新转录"

HINTS = {
    "none": NONE,
    "analyzed": ANALYZED,
    "pdf_page_steps": PDF_PAGE_STEPS,
    "pdf_page": PDF_PAGE,
    "pdf_text": PDF_TEXT,
    "image": IMAGE,
    "audio": AUDIO,
    "video": VIDEO,
    "audio_overview": AUDIO_OVERVIEW,
    "video_overview": VIDEO_OVERVIEW,
    "transcript": TRANSCRIPT,
}


def state_for(material: str, entry: dict | None = None, *, pdf_mode: str = "page", dialogue: bool = False) -> str:
    """``material`` = STORY 窗的 material_var（analyzed / pdf / image / media）；``entry`` = 材料列表里最后点中的那一行。
    ``pdf_mode`` = 这一条记下的 PDF 用法（page / text）；``dialogue`` = 叙事方式是故事对话（步数只对它有意义）。"""
    material = (material or "").strip()
    if material == "analyzed":
        return "analyzed"
    e = entry if isinstance(entry, dict) else {}
    if e.get("select") and material and e.get("select") != material:
        e = {}  # 最后点中的那一行跟现在选的材料对不上（比如按了别的按钮）：不用它
    kind = "" if e.get("placeholder") else (e.get("kind") or "")
    if not kind:
        kind = {"pdf": "pdf", "image": "image"}.get(material, "")
    if kind == "pdf":
        if (pdf_mode or "page") == "text":
            return "pdf_text"
        return "pdf_page_steps" if dialogue else "pdf_page"
    if kind in ("audio", "video"):
        pk = e.get("program_kind") or ""
        if pk in ("audio_overview", "video_overview"):
            return pk
        return kind
    if kind in ("image", "transcript"):
        return kind
    return "none"


def text_for(state: str) -> str:
    return HINTS.get(state or "", NONE)


def fit_text(text: str, measure: Callable[[str], int], width: int) -> str:
    """放进一行：量出来比 ``width`` 宽就从后往前去掉「 · 」小段；只剩一段还放不下就截断加「…」。"""
    text = text or ""
    if width <= 0 or measure(text) <= width:
        return text
    parts = text.split(SEP)
    while len(parts) > 1:
        parts.pop()
        cand = SEP.join(parts)
        if measure(cand) <= width:
            return cand
    cand = parts[0]
    while cand and measure(cand + "…") > width:
        cand = cand[:-1]
    return (cand + "…") if cand else ""
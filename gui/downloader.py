import os
import sys
import time
import yt_dlp
import subprocess
import shutil
import json
import re
import string
import threading
import glob
import copy

import config
import config_prompt
import config_channel
from datetime import datetime, timedelta, timezone

import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from utility.ffmpeg_audio_processor import FfmpegAudioProcessor
from utility.ffmpeg_processor import FfmpegProcessor, resolve_watermark_for_channel
from utility import llm_api
from utility.audio_transcriber import AudioTranscriber
from utility.file_util import (
    write_json,
    safe_copy_overwrite,
    safe_remove,
    parse_json,
    make_safe_file_name,
    safe_clipboard_json_copy,
    show_auto_close_popup,
)
from gui.choice_dialog import askchoice
from gui.publish_metadata_dialog import (
    ask_publish_metadata_then_schedule,
    scene_content_list_for_publish,
)
from gui.reference_editor_dialog import ReferenceEditorDialog
from gui.summary_mp4_review_dialog import (
    ask_summary_mp4_review_segments,
    run_trim_concat_watermark_worker,
)
from gui.tag_picker_menu import build_tag_cascade_menu, post_menu_below_widget
from utility.tags_text import merge_tag_pick, parse_tags_list
import project_manager

try:
    from tkcalendar import Calendar as TkCalendar
except ImportError:
    TkCalendar = None

try:
    from tkinterdnd2 import DND_FILES
    import tkinterdnd2 as _tkinterdnd2

    _TKINTER_DND_TK = _tkinterdnd2.Tk
    _TK_DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    _tkinterdnd2 = None  # type: ignore
    _TKINTER_DND_TK = None
    _TK_DND_AVAILABLE = False

# 导入所需模块
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
import tkinter.simpledialog as simpledialog
from tkinter import filedialog


def _format_nb_prompt_template(template: str, **kwargs) -> str:
    """对模板中 ``{name}`` 占位符填入 kwargs（``content`` / ``story`` / ``instruction`` 等）。"""
    names = set()
    for _, field_name, _, _ in string.Formatter().parse(template):
        if not field_name:
            continue
        names.add(field_name.split("!")[0].split(":")[0].strip())
    safe = {k: kwargs.get(k, "") for k in names}
    return template.format(**safe)


def _scenes_prompt_choices(channel_key: str) -> list[tuple[str, str]]:
    """从频道 config 读取 ``scenes_prompt_choices``。"""
    cfg = config_channel.get_channel_config(channel_key) or {}
    return [
        (lbl, tpl)
        for lbl, tpl in (cfg.get("scenes_prompt_choices") or [])
        if (tpl or "").strip()
    ]


def _story_prompt_choices(channel_key: str) -> list[tuple[str, str]]:
    """从频道 config 读取 ``story_prompt_choices``。"""
    cfg = config_channel.get_channel_config(channel_key) or {}
    return [
        (lbl, tpl)
        for lbl, tpl in (cfg.get("story_prompt_choices") or [])
        if (tpl or "").strip()
    ]


def _instruction_snippet_choices(channel_key: str) -> list[tuple[str, str]]:
    """从频道 config 读取导向说明可插入片段（无则使用全局默认）。"""
    return config_channel.get_instruction_snippet_choices(channel_key)


def _append_instruction_snippet(text_widget, snippet: str) -> None:
    snippet = (snippet or "").strip()
    if not snippet:
        return
    current = (text_widget.get("1.0", tk.END) or "").rstrip()
    new_text = f"{current}\n\n{snippet}" if current else snippet
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", new_text)


def _build_instruction_snippet_combo(
    parent,
    channel_key: str,
    instruction_tx,
    *,
    on_changed=None,
) -> None:
    """在导向说明框旁添加「插入片段」下拉，选中后追加到文本末尾（空一行）。"""
    choices = _instruction_snippet_choices(channel_key)
    if not choices:
        return
    placeholder = "— 选择片段插入 —"
    row = ttk.Frame(parent)
    row.pack(fill=tk.X, pady=(0, 4))
    ttk.Label(row, text="插入片段").pack(side=tk.LEFT, padx=(0, 5))
    combo_var = tk.StringVar(value=placeholder)
    combo = ttk.Combobox(
        row,
        textvariable=combo_var,
        values=[placeholder] + [lbl for lbl, _ in choices],
        state="readonly",
        width=36,
    )
    combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
    label_to_text = {lbl: text for lbl, text in choices}

    def on_select(_event=None):
        sel = (combo_var.get() or "").strip()
        if not sel or sel == placeholder or sel not in label_to_text:
            return
        _append_instruction_snippet(instruction_tx, label_to_text[sel])
        combo_var.set(placeholder)
        if on_changed:
            on_changed()

    combo.bind("<<ComboboxSelected>>", on_select)


def _pick_prompt_label_from_choices(
    choices: list[tuple[str, str]], *candidates: str
) -> str:
    """在 ``[(label, template), ...]`` 中按 label 精确或子串匹配。"""
    labels = [
        (lbl or "").strip()
        for lbl, _ in choices
        if (lbl or "").strip()
    ]
    for want in candidates:
        want = (want or "").strip()
        if not want:
            continue
        for lbl in labels:
            if lbl == want:
                return lbl
        want_lower = want.lower()
        for lbl in labels:
            if want_lower in lbl.lower():
                return lbl
    return ""


def _default_notebooklm_prompt_label(channel_key: str) -> str:
    """场景智能生成等内部使用的默认提示 label。"""
    for lbl, _ in _scenes_prompt_choices(channel_key):
        if (lbl or "").strip() in ("Story", "Scenes"):
            return lbl
        if "Scene" in (lbl or ""):
            return lbl
    choices = _scenes_prompt_choices(channel_key)
    return choices[0][0] if choices else ""


def _pick_notebooklm_prompt_label(channel_key: str, *candidates: str) -> str:
    """在频道 config 的 scenes_prompt_choices 中按 label 精确或子串匹配。"""
    return _pick_prompt_label_from_choices(
        _scenes_prompt_choices(channel_key), *candidates
    )


def _pick_story_prompt_label(channel_key: str, *candidates: str) -> str:
    """在频道 config 的 story_prompt_choices 中按 label 精确或子串匹配。"""
    return _pick_prompt_label_from_choices(
        _story_prompt_choices(channel_key), *candidates
    )


def _video_detail_has_story_content(video_detail: dict) -> bool:
    if not isinstance(video_detail, dict):
        return False
    return bool(project_manager.story_field_flat_text(video_detail.get("story")))


def _default_scene_editor_prompt_label(video_detail: dict, channel_key: str) -> str:
    """场景窗「选LM提示」默认项：有 story → Story to Scenes，否则 Content to Scenes。"""
    if _video_detail_has_story_content(video_detail):
        picked = _pick_notebooklm_prompt_label(channel_key, "Story to Scenes")
        if picked:
            return picked
    picked = _pick_notebooklm_prompt_label(
        channel_key, "Content to Scenes", "Content to Scene"
    )
    if picked:
        return picked
    return _default_notebooklm_prompt_label(channel_key)


def _default_story_editor_prompt_label(channel_key: str) -> str:
    """Story 窗「选提示」默认项：按频道类型匹配首项。"""
    cfg = config_channel.get_channel_config(channel_key) or {}
    channel_id = (cfg.get("channel_id") or channel_key or "").strip()
    if channel_id in ("music_story", "broadway"):
        for want in ("Lyrics to Story", "2 Layers Story"):
            picked = _pick_story_prompt_label(channel_key, want)
            if picked:
                return picked
    for want in ("4 Step Story", "2 Step Story", "3 Step Story", "Mini Story", "Short Story", "Long Story"):
        picked = _pick_story_prompt_label(channel_key, want)
        if picked:
            return picked
    choices = _story_prompt_choices(channel_key)
    return choices[0][0] if choices else ""


def _story_entry_heading(entry: dict) -> str:
    """Story 条目标题：``title`` 或 MV 的 ``caption``。"""
    if not isinstance(entry, dict):
        return ""
    return (entry.get("title") or entry.get("caption") or "").strip()


def _resolve_story_prompt_template(
    channel_key: str,
    *,
    label: str | None = None,
    index: int = 0,
) -> tuple[str, str, int]:
    """按 label 或 index 取 story prompt (label, template, index)。"""
    choices = _story_prompt_choices(channel_key)
    if not choices:
        return ("", "", 0)
    if label:
        want = label.strip()
        for i, (lbl, tpl) in enumerate(choices):
            if (lbl or "").strip() == want:
                return (lbl, tpl, i)
    idx = max(0, min(index, len(choices) - 1))
    lbl, tpl = choices[idx]
    return (lbl, tpl, idx)


def _story_entry_display_text(entry: dict) -> str:
    """单条 story JSON 条目 → 可读文本（title/caption + story）。"""
    if not isinstance(entry, dict):
        return ""
    title = _story_entry_heading(entry)
    body = (entry.get("story") or entry.get("content") or "").strip()
    if title and body:
        return f"{title}\n\n{body}"
    return body or title


def _resolve_notebooklm_prompt_template(
    channel_key: str,
    *,
    label: str | None = None,
    index: int = 0,
) -> tuple[str, str, int]:
    """按 label 或 index 取 (label, template, index)；无匹配时回退首项。"""
    choices = _scenes_prompt_choices(channel_key)
    if not choices:
        return ("", "", 0)
    if label:
        want = label.strip()
        for i, (lbl, tpl) in enumerate(choices):
            if (lbl or "").strip() == want:
                return (lbl, tpl, i)
    idx = max(0, min(index, len(choices) - 1))
    lbl, tpl = choices[idx]
    return (lbl, tpl, idx)


def _notebooklm_row_topic_fields(video_detail: dict) -> tuple[str, str, str]:
    """从列表行 / ``project_profile`` 取主题分类、子类型与 ``topic`` 字符串。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    cat = (vd.get("topic_category") or "").strip()
    sub = (vd.get("topic_subtype") or "").strip()
    prof = vd.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict):
        if not cat:
            cat = (prof.get("topic_category") or "").strip()
        if not sub:
            sub = (prof.get("topic_subtype") or "").strip()
    topic = f"{cat}-{sub}" if cat or sub else ""
    return cat, sub, topic


def _notebooklm_row_tags_text(video_detail: dict) -> str:
    vd = video_detail if isinstance(video_detail, dict) else {}
    tags_raw = vd.get("tags", "")
    if isinstance(tags_raw, list):
        return ", ".join(str(x) for x in tags_raw if str(x).strip())
    return ", ".join(parse_tags_list(str(tags_raw or "")))


def _notebooklm_story_text(video_detail: dict) -> str:
    """``{story}`` 占位符：story JSON array 首条，无则空字符串。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    return project_manager.story_first_entry_text(vd.get("story")).strip()


def _notebooklm_prompt_context_from_video_detail(
    mgr,
    video_detail: dict,
    *,
    instruction: str = "",
) -> dict:
    """场景智能生成等共用的 NotebookLM 占位符数据源。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    cat, sub, topic = _notebooklm_row_topic_fields(vd)
    reference_parts = []
    channel_videos = getattr(getattr(mgr, "downloader", None), "channel_videos", []) or []
    for i, seg in enumerate((vd.get("status") or "").split("|")):
        yid = (seg or "").strip()
        if not yid or yid in ("success", "failed"):
            continue
        ref_v = _find_video_by_youtube_id(channel_videos, yid)
        if not ref_v:
            continue
        ref_title = _youtube_row_display_title(ref_v)
        summary = (ref_v.get("summary") or "").strip()
        reference_parts.append(
            f"Reference {i + 1}: Title: {ref_title}\nReference {i + 1}: Summary: {summary}"
        )
    reference = (
        "\n\n\n----------------------------------------------------------\n".join(reference_parts)
        if reference_parts
        else ""
    )
    content = vd.get("analyzed_content")
    story = _notebooklm_story_text(vd)
    return {
        "topic": topic,
        "tags": _notebooklm_row_tags_text(vd),
        "reference": reference,
        "story_title": _youtube_row_display_title(vd),
        "content": content,
        "story": story,
        "link": (vd.get("url") or "").strip(),
        "instruction": (instruction or "").strip(),
        "language": config.llm_language_label(getattr(mgr, "language", "")),
        "category": cat,
        "subtype": sub,
    }


def _build_notebooklm_prompt_for_row(
    mgr,
    video_detail: dict,
    template: str,
    *,
    instruction: str = "",
    sections: int = 1,
    topic: str = "",
    tags: str = "",
    topic_category: str = "",
    topic_subtype: str = "",
    story_override: str | None = None,
    content_override: str | None = None,
) -> str:
    """按频道模板 + 列表行数据拼 NotebookLM / LLM 提示词（单段 format，含 ``content`` / ``story``）。"""
    ctx = _notebooklm_prompt_context_from_video_detail(
        mgr, video_detail, instruction=instruction
    )
    if story_override is not None:
        ctx["story"] = (story_override or "").strip()
    if content_override is not None:
        ctx["content"] = (content_override or "").strip()
    if topic:
        ctx["topic"] = topic
    if tags:
        ctx["tags"] = tags
    cat = (topic_category or ctx.get("category") or "").strip()
    sub = (topic_subtype or ctx.get("subtype") or "").strip()
    soul = ""
    if "{soul}" in template:
        soul, _, _, _ = project_manager.build_soul(
            getattr(mgr, "channel", None) or mgr._channel_config_key(),
            cat,
            sub,
        )
    return _format_nb_prompt_template(
        template,
        topic=ctx.get("topic", ""),
        tags=ctx.get("tags", ""),
        language=ctx.get("language", ""),
        reference=ctx.get("reference", ""),
        soul=soul,
        story_title=ctx.get("story_title", ""),
        content=ctx.get("content", ""),
        story=ctx.get("story", ""),
        link=ctx.get("link", ""),
        instruction=ctx.get("instruction", ""),
        sections=sections,
    )



def _normalize_youtube_watch_url(url: str) -> str:
    """单视频 watch URL；去掉 list / start_radio 等，避免 yt-dlp 按播放列表解析。"""
    url = (url or "").strip()
    if not url:
        return url
    m = re.search(
        r"(?:[?&]v=|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})",
        url,
    )
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


def _iter_node_executable_candidates():
    """常见 Node.js 路径（含 PATH 与 Windows 默认安装目录）。"""
    seen: set[str] = set()
    w = shutil.which("node")
    if w:
        ap = os.path.normcase(os.path.abspath(w))
        seen.add(ap)
        yield w
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    for p in (
        os.path.join(pf, "nodejs", "node.exe"),
        os.path.join(pf86, "nodejs", "node.exe"),
        os.path.join(local, "Programs", "nodejs", "node.exe"),
        os.path.join(
            local,
            "Programs",
            "cursor",
            "resources",
            "app",
            "resources",
            "helpers",
            "node.exe",
        ),
    ):
        if not p:
            continue
        ap = os.path.normcase(os.path.abspath(p))
        if ap in seen or not os.path.isfile(p):
            continue
        seen.add(ap)
        yield p


def _verify_node_executable(node_path: str) -> bool:
    try:
        r = subprocess.run(
            [node_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _youtube_format_error_message(raw_error: str, *, cookies_invalid: bool = False) -> str:
    msg = (raw_error or "").strip()
    hints = [
        "YouTube 无法获取音视频格式。常见原因与处理：",
        "1) Node.js — 需已安装并在 PATH 中（重启程序后应看到「检测到 JavaScript 运行时」）",
    ]
    if cookies_invalid:
        hints.append(
            "2) cookies 已过期（日志出现 no longer valid）— 请重新登录 YouTube 并导出 "
            "www.youtube.com_cookies.txt 到「下载」文件夹，然后重启本程序"
        )
        hints.append("   导出说明: https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies")
    else:
        hints.append(
            "2) cookies 过期 — 将新的 www.youtube.com_cookies.txt 放入「下载」文件夹"
        )
    hints.append("3) yt-dlp 过旧 — 在 venv 中执行: pip install -U yt-dlp")
    if msg:
        hints.append("")
        hints.append(f"原始错误: {msg}")
    return "\n".join(hints)


YOUTUBE_AUDIO_FORMAT_FALLBACKS = (
    "bestaudio/best",
    "bestaudio",
    "ba/b",
    "best",
)

_YT_DOWNLOAD_PREFS_JSON = "_yt_download_prefs.json"


def _copy_text_to_clipboard(widget, text: str) -> None:
    """写入系统剪贴板（审阅窗打开、指令拷贝等）。"""
    s = (text or "").strip()
    if not s:
        return
    hosts: list = []
    if widget is not None:
        hosts.append(widget)
        try:
            top = widget.winfo_toplevel()
            if top is not widget:
                hosts.append(top)
        except tk.TclError:
            pass
    for w in hosts:
        try:
            w.clipboard_clear()
            w.clipboard_append(s)
            w.update()
            return
        except tk.TclError:
            continue


def _bind_text_editor_replace_from_clipboard_on_double_click(tx, clipboard_host) -> None:
    """双击编辑区：若系统剪贴板有非空内容，则用其替换全文。"""
    def _on_double(_event=None):
        clip = (_read_host_clipboard_text(clipboard_host) or "").strip()
        if not clip:
            return "break"
        tx.delete("1.0", tk.END)
        tx.insert("1.0", clip)
        return "break"

    tx.bind("<Double-Button-1>", _on_double, add="+")


def _sanitize_list_row_id_stem(raw_id: str) -> str:
    rid = (raw_id or "").strip()
    if not rid:
        return ""
    bad = '\\/:*?"<>|\r\n\t'
    s = "".join(c if c not in bad else "_" for c in rid)
    return s[:200] if len(s) > 200 else s


def _gen_video_watermark_dest_filename(video_detail: dict | None) -> str:
    """按 ``_gen_video_id_stem_candidates_for_row`` 顺序选用 stem（与条目 ``id`` 一致）；均无则时间戳。"""
    if isinstance(video_detail, dict):
        for stem in _gen_video_id_stem_candidates_for_row(video_detail):
            if stem:
                return stem + ".mp4"
    return datetime.now().strftime("%Y%m%d_%H%M%S") + ".mp4"


def _gen_video_cover_webp_dest_filename(video_detail: dict | None) -> str:
    """封面/配图 webp：与成片 mp4 同 stem，扩展名为 ``.webp``（``gen_video/<id>.webp``）。"""
    if isinstance(video_detail, dict):
        for stem in _gen_video_id_stem_candidates_for_row(video_detail):
            if stem:
                return stem + ".webp"
    return datetime.now().strftime("%Y%m%d_%H%M%S") + ".webp"


GEN_VIDEO_CLIP_SEGMENTS_KEY = "gen_video_clip_segments"


def _normalize_gen_video_clip_segment(seg) -> dict | None:
    if not isinstance(seg, dict):
        return None
    p = (seg.get("path") or "").strip()
    if not p:
        return None
    p = os.path.normpath(p)
    try:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))
        speed = round(float(seg.get("speed") or 1.0), 1)
    except (TypeError, ValueError):
        return None
    return {"path": p, "start": start, "end": end, "speed": speed}


def _get_gen_video_clip_segments(video_detail: dict) -> list[dict]:
    if not isinstance(video_detail, dict):
        return []
    raw = video_detail.get(GEN_VIDEO_CLIP_SEGMENTS_KEY)
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for seg in raw:
        n = _normalize_gen_video_clip_segment(seg)
        if n:
            out.append(n)
    return out


def _set_gen_video_clip_segments(video_detail: dict, segments: list[dict]) -> None:
    if not isinstance(video_detail, dict):
        return
    normalized: list[dict] = []
    for seg in segments or []:
        n = _normalize_gen_video_clip_segment(seg)
        if n:
            normalized.append(n)
    if normalized:
        video_detail[GEN_VIDEO_CLIP_SEGMENTS_KEY] = normalized
    else:
        video_detail.pop(GEN_VIDEO_CLIP_SEGMENTS_KEY, None)


_SUMMARY_IMAGE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
    ".jfif",
    ".heic",
    ".heif",
)


def _is_summary_image_file_path(path: str) -> bool:
    return (path or "").lower().endswith(_SUMMARY_IMAGE_SUFFIXES)


def _gen_video_publish_mp4_if_ready(video: dict) -> str:
    """gen_video 下任一候选 stem 的 ``.mp4`` 存在即有成片（频道行 / 项目行不区别对待）。"""
    return _find_gen_video_mp4_for_row(video)


def _win_long_path(path: str) -> str:
    """Windows 长路径前缀，避免超长路径 isfile 失败。"""
    p = os.path.normpath(path)
    if os.name != "nt" or p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    if len(p) >= 240:
        return "\\\\?\\" + p
    return p


def _is_existing_file(path: str) -> bool:
    p = (path or "").strip()
    if not p:
        return False
    lp = _win_long_path(p)
    return os.path.isfile(lp) or os.path.isfile(p)


def _collect_unique_file_paths(
    paths: list[str], *, label: str = "", allow_duplicates: bool = False
) -> list[str]:
    """规范化路径列表；默认去重（保留顺序），``allow_duplicates=True`` 时保留重复项。"""
    out: list[str] = []
    seen: set[str] = set()
    raw_n = len(paths)
    for raw in paths:
        p = (raw or "").strip()
        if p.startswith("{") and p.endswith("}"):
            p = p[1:-1].strip()
        if not p:
            continue
        p = os.path.normpath(p)
        if not _is_existing_file(p):
            print(f"⚠️ 跳过无效文件: {p}")
            continue
        if not allow_duplicates:
            key = os.path.normcase(os.path.abspath(p))
            if key in seen:
                print(f"⚠️ 跳过重复: {os.path.basename(p)}")
                continue
            seen.add(key)
        out.append(p)
    if label and raw_n != len(out):
        print(f"📎 {label}: 收到 {raw_n} 项 → 有效 {len(out)} 项")
    return out


def _dnd_paths_splitlist(master_widget, raw) -> list:
    if raw is None or str(raw).strip() == "":
        return []
    try:
        return list(master_widget.tk.splitlist(str(raw)))
    except tk.TclError:
        return []


def _natural_sort_key(text: str) -> list:
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", text)]


def _mp4_timestamp_from_filename(path: str) -> float | None:
    """从常见文件名中提取时间戳（如 20250619_143022）。"""
    base = os.path.basename(path)
    m = re.search(r"(\d{8})[_-]?(\d{6})", base)
    if m:
        try:
            return time.mktime(
                time.strptime(f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S")
            )
        except ValueError:
            pass
    m = re.search(r"(\d{4})(\d{2})(\d{2})", base)
    if m:
        try:
            return time.mktime(
                time.strptime("".join(m.groups()), "%Y%m%d")
            )
        except ValueError:
            pass
    return None


def _mp4_chronological_sort_key(path: str) -> tuple:
    """拼接排序键：优先文件名内时间 → 修改时间 → 创建时间 → 自然文件名。"""
    name_key = _natural_sort_key(os.path.basename(path))
    fn_ts = _mp4_timestamp_from_filename(path)
    if fn_ts is not None:
        return (0, fn_ts, name_key)
    try:
        st = os.stat(path)
        # Windows: st_ctime 为创建时间；取 mtime/ctime 较早者作「成片先后」近似
        t = min(st.st_mtime, st.st_ctime)
        return (1, t, name_key)
    except OSError:
        return (2, 0.0, name_key)


def _order_mp4_paths_for_concat(paths: list[str]) -> list[str]:
    """多段 mp4 拼接顺序：按时间从旧到新（文件名时间 / 文件时间，相同时按文件名）。"""
    if len(paths) <= 1:
        return list(paths)
    ordered = sorted(paths, key=_mp4_chronological_sort_key)
    print("📎 MP4 拼接顺序（旧 → 新）：")
    for i, p in enumerate(ordered, 1):
        ts = _mp4_timestamp_from_filename(p)
        try:
            st = os.stat(p)
            tinfo = (
                f"fn_ts={ts:.0f}" if ts is not None else f"mtime={st.st_mtime:.0f}"
            )
        except OSError:
            tinfo = "?"
        print(f"  {i}. {os.path.basename(p)}  ({tinfo})")
    return ordered


def _read_clipboard_file_paths() -> list[str]:
    """从系统剪贴板读取文件路径（Windows 资源管理器复制文件）。"""
    try:
        import win32clipboard  # type: ignore

        win32clipboard.OpenClipboard()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_HDROP):
                return []
            raw = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return []

    paths: list[str] = []
    if isinstance(raw, (list, tuple)):
        paths = [str(p) for p in raw if p]
    elif isinstance(raw, str) and raw.strip():
        if "\0" in raw:
            paths = [p for p in raw.split("\0") if (p or "").strip()]
        else:
            paths = [raw.strip()]
    elif isinstance(raw, bytes):
        try:
            text = raw.decode("utf-16-le", errors="ignore")
            paths = [p for p in text.split("\0") if (p or "").strip()]
        except Exception:
            paths = []

    return _collect_unique_file_paths(paths, label="剪贴板")


def _dnd_normalize_file_paths(
    master_widget, raw, *, allow_duplicates: bool = False
) -> list[str]:
    """拖放路径列表（保持 Explorer 给出的先后顺序）。"""
    out: list[str] = []
    for raw_path in _dnd_paths_splitlist(master_widget, raw):
        p = (raw_path or "").strip()
        if p.startswith("{") and p.endswith("}"):
            p = p[1:-1]
        if p:
            out.append(os.path.normpath(p))
    return _collect_unique_file_paths(
        out, label="拖放", allow_duplicates=allow_duplicates
    )


def _tkinter_dnd_root_capable(widget) -> bool:
    """文件拖放需要应用根为 ``TkinterDnD.Tk``（纯 ``tk.Tk`` 会显示禁止拖放）。"""
    if not _TK_DND_AVAILABLE or _TKINTER_DND_TK is None or widget is None:
        return False
    w = widget
    while getattr(w, "master", None) is not None:
        w = w.master
    return isinstance(w, _TKINTER_DND_TK)


def _flush_accumulated_summary_drop(summary_window: tk.Toplevel) -> None:
    """合并短时间内多次拖放事件的路径后统一处理。"""
    summary_window._accumulated_drop_after_id = None
    buf = getattr(summary_window, "_accumulated_drop_paths", None)
    setattr(summary_window, "_accumulated_drop_paths", [])
    if not isinstance(buf, list) or not buf:
        return
    paths = _collect_unique_file_paths(buf, label="拖放合并", allow_duplicates=True)
    mp4_paths = [p for p in paths if p.lower().endswith(".mp4")]
    image_in = next(
        (p for p in paths if _is_summary_image_file_path(p)),
        None,
    )
    if mp4_paths:
        _on_summary_mp4_watermark_drop(None, summary_window, mp4_paths=mp4_paths)
    elif image_in:
        ctx = getattr(summary_window, "_summary_drop_ctx", None)
        if isinstance(ctx, dict):
            _start_summary_cover_webp_save(image_in, summary_window, ctx)
    else:
        try:
            show_auto_close_popup(
                summary_window,
                "拖放",
                "请拖入 .mp4（将打开审阅窗裁剪/排序后加水印成片）或图片。",
            )
        except Exception:
            pass


def _register_summary_gen_media_drop_targets(
    summary_window: tk.Toplevel, content_root: tk.Misc | None
):
    """注册摘要窗拖放：``.mp4``（审阅裁剪/排序后拼接）加水印成片；图片转 webp 封面。"""
    if not (_TK_DND_AVAILABLE and summary_window):
        return
    if not callable(getattr(summary_window, "drop_target_register", None)):
        return

    def _drop(ev, sw=summary_window):
        master = getattr(ev, "widget", None) or sw
        paths = _dnd_normalize_file_paths(master, getattr(ev, "data", None))
        if not paths:
            return
        buf = getattr(sw, "_accumulated_drop_paths", None)
        if not isinstance(buf, list):
            buf = []
        buf.extend(paths)
        setattr(sw, "_accumulated_drop_paths", buf)
        aid = getattr(sw, "_accumulated_drop_after_id", None)
        if aid:
            try:
                sw.after_cancel(aid)
            except tk.TclError:
                pass
        sw._accumulated_drop_after_id = sw.after(
            180, lambda s=sw: _flush_accumulated_summary_drop(s)
        )

    def _bind_one(w: tk.Misc):
        try:
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<Drop>>", _drop)
        except (tk.TclError, AttributeError, Exception):
            pass

    _bind_one(summary_window)
    if content_root is not None:
        _bind_one(content_root)

        def _walk_children(w: tk.Misc):
            try:
                for ch in w.winfo_children():
                    _bind_one(ch)
                    _walk_children(ch)
            except tk.TclError:
                pass

        _walk_children(content_root)


def _register_summary_gen_media_paste_bindings(
    summary_window: tk.Toplevel, content_root: tk.Misc | None
):
    """Ctrl+V：仅粘贴媒体（mp4 / 图片），摘要窗内不做文字粘贴。"""

    def _on_paste_media(_event=None):
        _on_summary_paste_media_from_clipboard(summary_window)
        return "break"

    paste_seqs = ("<Control-v>", "<Control-V>")

    def _bind_paste_subtree(widget):
        for seq in paste_seqs:
            widget.bind(seq, _on_paste_media, add="+")
        for ch in widget.winfo_children():
            _bind_paste_subtree(ch)

    if not getattr(summary_window, "_summary_paste_root_bound", False):
        for seq in paste_seqs:
            summary_window.bind(seq, _on_paste_media)
        summary_window._summary_paste_root_bound = True
    if content_root is not None:
        _bind_paste_subtree(content_root)


def _on_summary_paste_media_from_clipboard(summary_window: tk.Toplevel) -> None:
    """粘贴：资源管理器复制的文件，或剪贴板位图 → 与拖放相同。"""
    ctx = getattr(summary_window, "_summary_drop_ctx", None)
    if not isinstance(ctx, dict):
        return
    mgr = ctx.get("mgr")
    vd = ctx.get("vd")
    if mgr is None or not isinstance(vd, dict):
        return

    file_paths = _read_clipboard_file_paths()
    mp4_paths = [p for p in file_paths if p.lower().endswith(".mp4")]
    image_path = next(
        (p for p in file_paths if _is_summary_image_file_path(p)),
        None,
    )

    if mp4_paths:
        _on_summary_mp4_watermark_drop(
            None, summary_window, mp4_paths=mp4_paths
        )
        return
    if image_path:
        _start_summary_cover_webp_save(image_path, summary_window, ctx)
        return
    _on_summary_paste_image_from_clipboard(summary_window)


def _on_summary_gen_media_drop(event, summary_window: tk.Toplevel):
    ctx = getattr(summary_window, "_summary_drop_ctx", None)
    if not isinstance(ctx, dict):
        return
    mgr = ctx.get("mgr")
    vd = ctx.get("vd")
    if mgr is None or not isinstance(vd, dict):
        return
    master = getattr(event, "widget", None) or summary_window
    paths = _dnd_normalize_file_paths(
        master, getattr(event, "data", None), allow_duplicates=True
    )
    mp4_paths: list[str] = []
    image_in = None
    for p in paths:
        low = p.lower()
        if low.endswith(".mp4"):
            mp4_paths.append(p)
        elif _is_summary_image_file_path(p) and image_in is None:
            image_in = p
    if mp4_paths:
        _on_summary_mp4_watermark_drop(event, summary_window, mp4_paths=mp4_paths)
    elif image_in:
        _start_summary_cover_webp_save(image_in, summary_window, ctx)
    else:
        try:
            show_auto_close_popup(
                summary_window,
                "拖放",
                "请拖入 .mp4（将打开审阅窗裁剪/排序后加水印成片）或图片。",
            )
        except Exception:
            pass


def _on_summary_paste_image_from_clipboard(summary_window: tk.Toplevel) -> bool:
    ctx = getattr(summary_window, "_summary_drop_ctx", None)
    if not isinstance(ctx, dict):
        return False
    mgr = ctx.get("mgr")
    vd = ctx.get("vd")
    if mgr is None or not isinstance(vd, dict):
        return False
    tmp_png = ""
    try:
        from PIL import ImageGrab

        im = ImageGrab.grabclipboard()
        if im is None:
            return False
        pid = getattr(mgr, "pid", "") or "yt_img"
        os.makedirs(config.TEMP_PATH_BASE or ".", exist_ok=True)
        tmp_png = config.get_temp_file(pid, "png")
        if hasattr(im, "save"):
            im.save(tmp_png, format="PNG")
        else:
            return False
    except Exception:
        return False
    _start_summary_cover_webp_save(tmp_png, summary_window, ctx, cleanup_source=True)
    return True


def _refresh_summary_window_title(
    summary_window: tk.Toplevel,
    video_detail: dict,
) -> None:
    """刷新摘要窗标题栏。"""
    try:
        if not summary_window.winfo_exists():
            return
    except tk.TclError:
        return
    ctx = getattr(summary_window, "_summary_drop_ctx", None) or {}
    idx = ctx.get("summary_title_index", "")
    suf = ctx.get("summary_dnd_title_suffix", "")
    title_part = _youtube_row_display_title(video_detail) or "—"
    summary_window.title(
        f"{idx} - {title_part} - 摘要 · 拖入/ Ctrl+V 粘贴 MP4/图片{suf}"
    )


def _refresh_summary_ui_after_analyze(ctx: dict, summary_window: tk.Toplevel) -> None:
    """图片分析写入 analyzed_content 后，刷新摘要窗「视频摘要」与列表分析标记。"""
    try:
        if not summary_window.winfo_exists():
            return
    except tk.TclError:
        return
    refresh_display = ctx.get("refresh_summary_display")
    if callable(refresh_display):
        try:
            refresh_display()
        except Exception as e:
            print(f"刷新视频摘要失败: {e}")
    refresh_tree = ctx.get("refresh_channel_tree")
    if callable(refresh_tree):
        try:
            refresh_tree()
        except Exception as e:
            print(f"刷新频道列表失败: {e}")


def _normalize_story_entry(item: dict) -> dict | None:
    """单条 story：保留 LLM 返回的全部字段（title/story/heart_message/speaking 等）。"""
    if not isinstance(item, dict):
        return None
    out: dict = {}
    for k, v in item.items():
        if isinstance(v, str):
            sv = v.strip()
            if sv:
                out[k] = sv
        elif v is not None:
            out[k] = v
    if not out:
        return None
    title = _story_entry_heading(out)
    body = (out.get("story") or out.get("content") or "").strip()
    heart = (out.get("heart_message") or "").strip()
    speaking = (out.get("speaking") or "").strip()
    voiceover = (out.get("voiceover") or "").strip()
    actor = (out.get("actor") or "").strip()
    if not title and not body and not heart and not speaking and not voiceover and not actor:
        return None
    return out


def _parse_story_field(raw) -> list[dict]:
    """解析 ``video_detail['story']``：JSON array 或 legacy 纯文本。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[dict] = []
        for it in raw:
            n = _normalize_story_entry(it) if isinstance(it, dict) else None
            if n:
                out.append(n)
        return out
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                return [{"title": "", "story": s}]
            return _parse_story_field(parsed)
        return [{"title": "", "story": s}]
    return []


def _story_entries_to_json_text(entries: list[dict]) -> str:
    clean = [_normalize_story_entry(e) for e in (entries or [])]
    clean = [e for e in clean if e]
    return json.dumps(clean, ensure_ascii=False, indent=2)


def _coerce_story_editor_text(raw: str) -> tuple[list[dict], str]:
    """Story 编辑区文本 → (条目列表, 落盘 JSON 字符串)。单条 ``{...}`` 自动包成 array。"""
    s = (raw or "").strip()
    if not s:
        return [], ""
    lead = s.lstrip()
    if lead.startswith("{"):
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            entries = _parse_story_field(s)
            return entries, (_story_entries_to_json_text(entries) if entries else s)
        if isinstance(parsed, dict):
            entries = _parse_story_field([parsed])
            return entries, (
                _story_entries_to_json_text(entries)
                if entries
                else json.dumps([parsed], ensure_ascii=False, indent=2)
            )
        if isinstance(parsed, list):
            entries = _parse_story_field(parsed)
            return entries, (_story_entries_to_json_text(entries) if entries else s)
    entries = _parse_story_field(s)
    if entries and lead.startswith("["):
        return entries, _story_entries_to_json_text(entries)
    return entries, s


def _channel_key_for_stories_json(channel_key: str = "", channel_path: str = "") -> str:
    ck = (channel_key or "").strip()
    if ck:
        return ck
    cp = (channel_path or "").strip()
    if not cp:
        return ""
    slug = config._channel_id_from_program_path(cp)
    return slug or os.path.basename(cp.rstrip("/\\"))


def _prepend_story_entries_to_channel_stories_json(
    entries: list[dict],
    *,
    channel_key: str = "",
    channel_path: str = "",
) -> str:
    """将 story 条目插入 ``program/<channel>/stories.json`` 最前；返回写入路径。"""
    normalized_new = [_normalize_story_entry(e) for e in (entries or [])]
    normalized_new = [e for e in normalized_new if e]
    if not normalized_new:
        return ""
    ch = _channel_key_for_stories_json(channel_key, channel_path)
    if not ch:
        raise ValueError("无法解析频道目录（缺少 channel_key / channel_path）")
    folder = config.get_channel_path(ch)
    path = os.path.join(folder, "stories.json")
    existing: list[dict] = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise OSError(f"读取已有 stories.json 失败：{e}") from e
        if isinstance(data, list):
            existing = data
        elif isinstance(data, dict):
            existing = [data]
        else:
            existing = []
    normalized_old = [_normalize_story_entry(e) for e in existing]
    normalized_old = [e for e in normalized_old if e]
    merged = normalized_new + normalized_old
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return path


def _story_first_entry_json_text(raw) -> str:
    """Story JSON 数组首条 → 格式化 JSON 对象文本（剪贴板 / Slideshow 输入）。"""
    entries = _parse_story_field(raw)
    if entries:
        return json.dumps(entries[0], ensure_ascii=False, indent=2)
    if isinstance(raw, str):
        s = raw.strip()
        if s and not s.startswith("["):
            return s
    return ""


def _merge_story_entries(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    """新条目 prepend 到已有 story array。"""
    old = [_normalize_story_entry(e) for e in (existing or [])]
    old = [e for e in old if e]
    new = [_normalize_story_entry(e) for e in (new_entries or [])]
    new = [e for e in new if e]
    return new + old


def _story_field_editor_text(raw) -> str:
    """Story 编辑区展示：array → 格式化 JSON；legacy 纯文本原样。"""
    if isinstance(raw, str) and raw.strip().startswith("["):
        entries = _parse_story_field(raw)
        if entries:
            return _story_entries_to_json_text(entries)
    if isinstance(raw, list):
        entries = _parse_story_field(raw)
        if entries:
            return _story_entries_to_json_text(entries)
    if isinstance(raw, str):
        return raw.strip()
    if raw is None:
        return ""
    return str(raw).strip()


def _apply_story_title_to_project_profile(video_detail: dict, title: str) -> None:
    """有 ``project_profile`` 时，用新 story 的 ``title`` 更新 ``video_title``。"""
    if not isinstance(video_detail, dict):
        return
    vt = (title or "").strip()
    if not vt:
        return
    prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
    if not isinstance(prof, dict) or not prof:
        return
    merged = copy.deepcopy(prof)
    merged["video_title"] = vt
    video_detail[project_manager.PROJECT_PROFILE_KEY] = (
        project_manager.profile_for_list_storage(merged)
    )


def _persist_channel_videos(mgr) -> bool:
    try:
        with open(mgr.downloader.channel_list_json, "w", encoding="utf-8") as f:
            json.dump(mgr.downloader.channel_videos, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存 channel 列表失败: {e}")
        return False


def _apply_titles_to_story_first_entry(video_detail: dict, title: str) -> bool:
    """若已有 story，将首条 ``title`` 与 ``caption`` 同步为给定标题。"""
    vt = (title or "").strip()
    if not vt or not isinstance(video_detail, dict):
        return False
    raw = video_detail.get("story")
    if isinstance(raw, dict):
        updated = copy.deepcopy(raw)
        updated["title"] = vt
        updated["caption"] = vt
        video_detail["story"] = updated
        return True
    entries = _parse_story_field(raw)
    if not entries:
        return False
    first = copy.deepcopy(entries[0])
    first["title"] = vt
    first["caption"] = vt
    entries[0] = first
    video_detail["story"] = _story_entries_to_json_text(entries)
    return True


def _cover_save_default_video_title(video_detail: dict) -> str:
    """封面前对话框默认成片名：project_profile.video_title > story 首条 title。"""
    proj = _youtube_row_project_title(video_detail)
    if proj:
        return proj
    return _youtube_row_story_meta_title(video_detail)


def _apply_video_title_before_cover_save(
    video_detail: dict,
    *,
    video_title: str,
    channel_path: str = "",
) -> None:
    """保存封面前：更新 ``project_profile.video_title`` 与 story 首条；不改外层 ``title``（YouTube 原标题）。"""
    if not isinstance(video_detail, dict):
        return
    vt = (video_title or "").strip()
    if not vt:
        return
    _apply_story_title_to_project_profile(video_detail, vt)
    _apply_titles_to_story_first_entry(video_detail, vt)
    _normalize_channel_list_item_for_storage(video_detail, channel_path or "")


def _ask_video_title_before_cover_save_dialog(
    parent,
    video_detail: dict,
) -> dict | None:
    """保存封面前让用户确认/修改成片名；取消则放弃本次粘贴/拖放。"""
    if not isinstance(video_detail, dict):
        return None
    has_project_profile = project_manager.list_json_row_has_project_profile(
        video_detail
    )
    source_title = _youtube_row_source_title(video_detail)
    result_holder: dict | None = None
    dlg = tk.Toplevel(parent)
    dlg.title("保存封面前 — 确认视频标题")
    dlg.geometry("720x200")
    dlg.minsize(480, 160)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.update_idletasks()
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"720x200+{(sw - 720) // 2}+{(sh - 200) // 2}")

    frm = ttk.Frame(dlg, padding=12)
    frm.pack(fill=tk.BOTH, expand=True)

    hint = (
        "请确认或修改成片名后再保存封面。"
        "不会修改原视频标题（YouTube 下载名）。"
        "若本条已有 story，首条的 title 与 caption 将同步为下方成片名。"
    )
    if has_project_profile:
        hint += " 同时更新 project_profile.video_title。"
    ttk.Label(frm, text=hint, wraplength=680, justify=tk.LEFT).pack(
        anchor=tk.W, pady=(0, 10)
    )

    if source_title:
        src_row = ttk.Frame(frm)
        src_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(src_row, text="原视频标题（只读）:", width=18).pack(side=tk.LEFT)
        ttk.Label(
            src_row,
            text=source_title,
            wraplength=560,
            foreground="#555",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    title_box = ttk.LabelFrame(frm, text="成片名", padding=8)
    title_box.pack(fill=tk.X, pady=(0, 10))
    title_var = tk.StringVar(value=_cover_save_default_video_title(video_detail))
    title_entry = ttk.Entry(title_box, textvariable=title_var, width=90)
    title_entry.pack(fill=tk.X)
    title_entry.focus_set()
    title_entry.selection_range(0, tk.END)

    btn_row = ttk.Frame(frm)
    btn_row.pack(fill=tk.X)

    def on_confirm():
        nonlocal result_holder
        vt = (title_var.get() or "").strip()
        if not vt:
            messagebox.showwarning("提示", "成片名不能为空。", parent=dlg)
            return
        result_holder = {"video_title": vt}
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    ttk.Button(btn_row, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(btn_row, text="确认并继续", command=on_confirm).pack(side=tk.RIGHT)

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.wait_window()
    return result_holder


def _apply_image_analyze_to_video_detail(
    video_detail: dict,
    *,
    title: str,
    content: str,
    channel_path: str = "",
) -> None:
    """确认后：``content`` → ``analyzed_content``；有 ``project_profile`` 时 ``title`` → ``video_title``。"""
    if not isinstance(video_detail, dict):
        return
    body = (content or "").strip()
    if body:
        video_detail["analyzed_content"] = body
    vt = (title or "").strip()
    prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
    if vt and isinstance(prof, dict) and prof:
        merged = copy.deepcopy(prof)
        merged["video_title"] = vt
        video_detail[project_manager.PROJECT_PROFILE_KEY] = (
            project_manager.profile_for_list_storage(merged)
        )
    _normalize_channel_list_item_for_storage(video_detail, channel_path or "")


def _ask_image_analyze_confirm_dialog(
    parent,
    *,
    title: str = "",
    content: str = "",
) -> dict | None:
    """展示可编辑的图片分析结果；取消返回 ``None``，确认返回 ``{\"title\", \"content\"}``。"""
    result_holder: dict | None = None
    dlg = tk.Toplevel(parent)
    dlg.title("图片分析结果 — 确认写入")
    dlg.geometry("760x580")
    dlg.minsize(540, 440)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.update_idletasks()
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"760x580+{(sw - 760) // 2}+{(sh - 580) // 2}")

    frm = ttk.Frame(dlg, padding=12)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(
        frm,
        text=(
            "以下为 LLM 对图片的文字分析。可编辑后确认写入；"
            "「取消」仅保留已保存的封面 WebP，不改动 analyzed_content 与项目名。"
        ),
        wraplength=720,
        justify=tk.LEFT,
    ).pack(anchor=tk.W, pady=(0, 10))

    title_box = ttk.LabelFrame(frm, text="标题 title", padding=8)
    title_box.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(
        title_box,
        text="有 project_profile 时，确认后将更新「项目成片名」。",
        wraplength=700,
    ).pack(anchor=tk.W, pady=(0, 4))
    title_var = tk.StringVar(value=title or "")
    title_entry = ttk.Entry(title_box, textvariable=title_var, width=90)
    title_entry.pack(fill=tk.X)
    title_entry.focus_set()

    content_box = ttk.LabelFrame(frm, text="分析内容 content → analyzed_content", padding=8)
    content_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    content_tx = scrolledtext.ScrolledText(
        content_box, wrap=tk.WORD, width=88, height=16, font=("Arial", 10)
    )
    content_tx.pack(fill=tk.BOTH, expand=True)
    if content:
        content_tx.insert("1.0", content)

    btn_row = ttk.Frame(frm)
    btn_row.pack(fill=tk.X)

    def on_confirm():
        nonlocal result_holder
        t = (title_var.get() or "").strip()
        c = (content_tx.get("1.0", tk.END) or "").strip()
        if not t and not c:
            messagebox.showwarning(
                "提示", "标题与分析内容不能同时为空。", parent=dlg
            )
            return
        result_holder = {"title": t, "content": c}
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    ttk.Button(btn_row, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(btn_row, text="确认写入", command=on_confirm).pack(side=tk.RIGHT)

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.wait_window()
    return result_holder


def _start_summary_cover_webp_save(
    image_path: str,
    summary_window: tk.Toplevel,
    ctx: dict,
    *,
    cleanup_source: bool = False,
):
    """图片：LLM 分析写入 analyzed_content；加水印转 webp 写入 gen_video。"""
    mgr = ctx.get("mgr")
    vd = ctx.get("vd")
    if mgr is None or not isinstance(vd, dict):
        return
    if not image_path or not os.path.isfile(image_path):
        return

    par = summary_window if summary_window.winfo_exists() else (
        getattr(mgr, "root", None) or summary_window.winfo_toplevel()
    )
    title_choice = _ask_video_title_before_cover_save_dialog(par, vd)
    if title_choice is None:
        if cleanup_source and image_path and os.path.isfile(image_path):
            try:
                safe_remove(image_path)
            except Exception:
                pass
        return

    ch_path = getattr(mgr, "channel_path", "") or ""
    _apply_video_title_before_cover_save(
        vd,
        video_title=title_choice.get("video_title", ""),
        channel_path=ch_path,
    )
    if _persist_channel_videos(mgr):
        rfn_title = ctx.get("refresh_title_fields") if isinstance(ctx, dict) else None
        if callable(rfn_title):
            try:
                rfn_title()
            except Exception:
                _refresh_summary_window_title(summary_window, vd)
        else:
            _refresh_summary_window_title(summary_window, vd)
        refresh_tree = ctx.get("refresh_channel_tree") if isinstance(ctx, dict) else None
        if callable(refresh_tree):
            try:
                refresh_tree()
            except Exception:
                pass

    wm_path, wm_opts = resolve_watermark_for_channel(getattr(mgr, "channel", "") or "")
    if not wm_path:
        messagebox.showwarning(
            "加水印失败",
            r"未找到水印 PNG（频道 watermark 路径或仓库下 media\watermark.png）。",
            parent=summary_window,
        )
        return

    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    dest_name = _gen_video_cover_webp_dest_filename(vd)
    pid = getattr(mgr, "pid", "") or "yt_img"
    lang = getattr(mgr, "language", "") or "zh"

    def _worker():
        out_ok = ""
        err_msg = ""
        parsed_analysis: dict = {}
        wm_webp = ""
        webp_tmp = ""
        try:
            payload = mgr.llm_api.analyze_image_json(
                config_prompt.IMAGE_READ_SYSTEM_PROMPT.format(language=lang),
                image_path,
            )
            if payload and isinstance(payload, dict):
                parsed_analysis = payload

            os.makedirs(gen_dir, exist_ok=True)
            ff = FfmpegProcessor(pid, lang)
            wm_webp = ff.apply_watermark_to_flat_image(image_path, wm_path, wm_opts or {})
            if not wm_webp or not os.path.isfile(wm_webp):
                if not err_msg:
                    err_msg = "图片叠加水印失败。"
                return
            webp_tmp = ff.image_to_webp(wm_webp)
            if not webp_tmp or not os.path.isfile(webp_tmp):
                if not err_msg:
                    err_msg = "图片转 WebP 失败。"
                return
            dest_abs = os.path.join(gen_dir, dest_name)
            safe_copy_overwrite(webp_tmp, dest_abs)
            out_ok = dest_abs
            if out_ok and parsed_analysis:
                err_msg = ""
        except Exception as ex:
            err_msg = str(ex)
        finally:
            if cleanup_source and image_path and os.path.isfile(image_path):
                try:
                    safe_remove(image_path)
                except Exception:
                    pass
            for tmp in (wm_webp, webp_tmp):
                if tmp and tmp != out_ok and os.path.isfile(tmp):
                    try:
                        safe_remove(tmp)
                    except Exception:
                        pass

        root = getattr(mgr, "root", None) or summary_window.winfo_toplevel()

        def _done_ui():
            par = summary_window if summary_window.winfo_exists() else root
            analyze_applied = False
            had_analysis = bool(parsed_analysis)

            if had_analysis:
                llm_title_default = (
                    parsed_analysis.get("title", "")
                    or _youtube_row_project_title(vd)
                    or _youtube_row_source_title(vd)
                )
                choice = _ask_image_analyze_confirm_dialog(
                    par,
                    title=llm_title_default,
                    content=parsed_analysis.get("story", ""),
                )
                if choice is not None:
                    story_payload = copy.deepcopy(parsed_analysis)
                    t = (choice.get("title") or "").strip()
                    body = (choice.get("content") or "").strip()
                    if t:
                        story_payload["title"] = t
                        story_payload["caption"] = t
                    if body:
                        story_payload["story"] = body
                    vd["story"] = story_payload

                    ch_path = getattr(mgr, "channel_path", "") or ""
                    _apply_image_analyze_to_video_detail(
                        vd,
                        title=t,
                        content=body,
                        channel_path=ch_path,
                    )
                    
                    if _persist_channel_videos(mgr):
                        analyze_applied = True
                        _refresh_summary_ui_after_analyze(ctx, summary_window)
                        rfn_title = (
                            ctx.get("refresh_title_fields")
                            if isinstance(ctx, dict)
                            else None
                        )
                        if callable(rfn_title):
                            try:
                                rfn_title()
                            except Exception:
                                _refresh_summary_window_title(summary_window, vd)
                        else:
                            _refresh_summary_window_title(summary_window, vd)

            rfn_feat = ctx.get("refresh_feature_media_row") if isinstance(ctx, dict) else None
            if callable(rfn_feat):
                try:
                    rfn_feat()
                except Exception:
                    pass
            if out_ok and analyze_applied:
                show_auto_close_popup(
                    par,
                    "封面与分析已保存",
                    f"已写入 analyzed_content"
                    + (
                        " 与项目成片名"
                        if project_manager.list_json_row_has_project_profile(vd)
                        else ""
                    )
                    + f"，并保存 WebP 封面：\n{out_ok}",
                )
            elif out_ok and had_analysis:
                show_auto_close_popup(
                    par,
                    "封面已保存",
                    f"已加水印并保存为 WebP：\n{out_ok}\n\n"
                    "（已取消写入图片分析，analyzed_content / 项目名未改动）",
                )
            elif out_ok:
                show_auto_close_popup(
                    par,
                    "封面已保存",
                    f"已加水印并保存为 WebP：\n{out_ok}\n\n"
                    + (
                        f"（{err_msg}）"
                        if err_msg
                        else "（LLM 分析未返回有效结果）"
                    ),
                )
            elif analyze_applied:
                show_auto_close_popup(
                    par,
                    "分析已保存",
                    "已写入本条 analyzed_content（封面 WebP 保存失败）。",
                )
            elif err_msg and not out_ok:
                show_auto_close_popup(par, "保存失败", err_msg, kind="error")

        root.after(0, _done_ui)

    threading.Thread(target=_worker, daemon=True).start()


def _run_summary_gen_video_clip_review(
    summary_window: tk.Toplevel,
    *,
    mgr,
    vd: dict,
    ctx: dict,
    mp4_paths: list[str] | None = None,
    initial_segments: list[dict] | None = None,
) -> None:
    """打开审阅窗 → 保存片段配置到频道列表行 → 拼接加水印写入 gen_video。"""
    wm_path, wm_opts = resolve_watermark_for_channel(getattr(mgr, "channel", "") or "")
    if not wm_path:
        messagebox.showwarning(
            "加水印失败",
            r"未找到水印 PNG（频道 watermark 路径或仓库下 media\watermark.png）。",
            parent=summary_window,
        )
        return

    pid = getattr(mgr, "pid", "") or "yt_wm"
    lang = getattr(mgr, "language", "") or "zh"
    try:
        if initial_segments:
            segments = ask_summary_mp4_review_segments(
                summary_window,
                initial_segments=initial_segments,
                pid=pid,
                lang=lang,
            )
        else:
            segments = ask_summary_mp4_review_segments(
                summary_window,
                mp4_paths=mp4_paths or [],
                pid=pid,
                lang=lang,
            )
    except ValueError as ex:
        messagebox.showwarning("审阅", str(ex), parent=summary_window)
        return
    if not segments:
        return

    _set_gen_video_clip_segments(vd, segments)
    _persist_channel_videos(mgr)

    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "")
    dest_name = _gen_video_watermark_dest_filename(vd)

    def _on_worker_done(out_ok: str, err_msg: str, n_saved: int):
        root = getattr(mgr, "root", None) or summary_window.winfo_toplevel()

        def _done_ui():
            par = summary_window if summary_window.winfo_exists() else root
            if out_ok:
                rfn = ctx.get("refresh_channel_tree")
                if callable(rfn):
                    try:
                        rfn()
                    except Exception:
                        pass
                rfn_pub = ctx.get("refresh_publish_row")
                if callable(rfn_pub):
                    try:
                        rfn_pub()
                    except Exception:
                        pass
                rfn_feat = ctx.get("refresh_feature_media_row")
                if callable(rfn_feat):
                    try:
                        rfn_feat()
                    except Exception:
                        pass
                if n_saved > 1:
                    msg = f"已裁剪并拼接 {n_saved} 段、加水印保存：\n{out_ok}"
                else:
                    msg = f"已裁剪并加水印保存：\n{out_ok}"
                show_auto_close_popup(par, "已保存", msg)
            elif err_msg:
                show_auto_close_popup(par, "加水印失败", err_msg, kind="error")

        root.after(0, _done_ui)

    run_trim_concat_watermark_worker(
        segments=segments,
        pid=pid,
        lang=lang,
        wm_path=wm_path,
        wm_opts=wm_opts or {},
        gen_dir=gen_dir,
        dest_name=dest_name,
        on_done=_on_worker_done,
    )


def _on_summary_reopen_gen_video_clip_review(summary_window: tk.Toplevel) -> None:
    """从已保存的片段配置重新打开审阅窗并生成成片。"""
    ctx = getattr(summary_window, "_summary_drop_ctx", None)
    if not isinstance(ctx, dict):
        return
    mgr = ctx.get("mgr")
    vd = ctx.get("vd")
    if mgr is None or not isinstance(vd, dict):
        return
    segments = _get_gen_video_clip_segments(vd)
    if not segments:
        messagebox.showinfo(
            "编辑成片片段",
            "尚无已保存的片段配置。\n请先拖入 MP4 并完成审阅，或从资源管理器一次拖入多个相同文件。",
            parent=summary_window,
        )
        return
    missing = [
        s["path"] for s in segments
        if not os.path.isfile(s.get("path", ""))
    ]
    if missing:
        preview = "\n".join(os.path.basename(p) for p in missing[:6])
        extra = f"\n…等共 {len(missing)} 个" if len(missing) > 6 else ""
        if not messagebox.askyesno(
            "源文件缺失",
            f"有 {len(missing)} 个片段源文件已不存在，审阅窗将跳过它们：\n{preview}{extra}\n\n是否继续？",
            parent=summary_window,
        ):
            return
    _run_summary_gen_video_clip_review(
        summary_window,
        mgr=mgr,
        vd=vd,
        ctx=ctx,
        initial_segments=segments,
    )


def _on_summary_mp4_watermark_drop(
    event,
    summary_window: tk.Toplevel,
    *,
    mp4_path: str | None = None,
    mp4_paths: list[str] | None = None,
):
    ctx = getattr(summary_window, "_summary_drop_ctx", None)
    if not isinstance(ctx, dict):
        return
    mgr = ctx.get("mgr")
    vd = ctx.get("vd")
    if mgr is None or not isinstance(vd, dict):
        return

    paths: list[str] = []
    if mp4_paths:
        paths = _collect_unique_file_paths(
            [
                p for p in mp4_paths
                if (p or "").strip() and p.lower().endswith(".mp4")
            ],
            label="审阅 MP4",
            allow_duplicates=True,
        )
    elif (mp4_path or "").strip():
        p = os.path.normpath(mp4_path.strip())
        if os.path.isfile(p) and p.lower().endswith(".mp4"):
            paths = [p]
    if not paths:
        master = getattr(event, "widget", None) or summary_window
        paths = [
            p for p in _dnd_normalize_file_paths(
                master, getattr(event, "data", None), allow_duplicates=True
            )
            if p.lower().endswith(".mp4")
        ]
    if not paths:
        try:
            show_auto_close_popup(summary_window, "拖放", "请拖入 .mp4 文件。")
        except Exception:
            pass
        return

    _run_summary_gen_video_clip_review(
        summary_window,
        mgr=mgr,
        vd=vd,
        ctx=ctx,
        mp4_paths=paths,
    )


def _treeview_item_tags_safe(tree, item):
    """读取 Treeview 行的 tags。populate_tree 会删行重建，旧 iid 失效，必须先 exists。"""
    try:
        if tree.exists(item):
            return tree.item(item, "tags")
    except tk.TclError:
        pass
    return ()


def _configure_channel_list_treeview(tree: ttk.Treeview) -> None:
    """频道视频列表：固定列不拉伸（默认 stretch=True 会在宽窗口撑出列间空白）。"""
    for col, width, anchor in (
        ("#0", 46, "center"),
        ("views", 66, "e"),
        ("duration", 50, "center"),
        ("upload_date", 86, "center"),
        ("status", 150, "center"),
        ("analyzed", 100, "center"),
        ("topic_category", 200, "w"),
        ("topic_subtype", 200, "w"),
        ("tags", 200, "w"),
        ("mark", 250, "w"),
    ):
        tree.column(col, width=width, minwidth=width, stretch=False, anchor=anchor)
    tree.column("title", width=350, minwidth=200, stretch=True, anchor="w")


def _configure_video_pick_treeview(tree: ttk.Treeview) -> None:
    """新视频选择弹窗：仅标题列拉伸。"""
    for col, width, anchor in (
        ("views", 72, "e"),
        ("duration", 56, "center"),
        ("upload_date", 88, "center"),
    ):
        tree.column(col, width=width, minwidth=width, stretch=False, anchor=anchor)
    tree.column("title", width=450, minwidth=200, stretch=True, anchor="w")


def _channel_list_dir_for_media_downloader(youtube_dir: str) -> str:
    """若 ``youtube_dir`` 为 ``<频道>/Download``，列表目录为 ``<频道>/list``；否则（如项目路径）为 ``<youtube_dir>/list``。"""
    norm = os.path.normpath(youtube_dir)
    if os.path.basename(norm) == "Download":
        return config.channel_list_json_dir_abs(os.path.dirname(norm))
    return os.path.join(norm, "list")


def _topic_category_program_list_path(channel_path: str, topic_category: str) -> str:
    d = config.ensure_channel_list_json_dir(channel_path)
    return os.path.join(d, config.topic_category_list_file_basename(topic_category))


# --- 全 program 共享 persistent 剪贴板：``{BASE_PROGRAM_PATH}/program_clipboard.json`` ---

PROGRAM_CLIPBOARD_JSON_NAME = "program_clipboard.json"
LEGACY_CHANNEL_CLIPBOARD_JSON_NAME = "channel_clipboard.json"
_program_clipboard_manager_window: "ChannelClipboardManagerWindow | None" = None


def _program_clipboard_file() -> str:
    root = (config.BASE_PROGRAM_PATH or "").strip()
    if not root:
        root = os.path.join(config.BASE_MEDIA_PATH or "/AI_MEDIA", "program")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, PROGRAM_CLIPBOARD_JSON_NAME)


def _merge_legacy_clipboard_file_into_items(
    fp: str,
    items: list,
    seen: set,
    *,
    ch_name: str = "",
) -> None:
    try:
        with open(fp, "r", encoding="utf-8") as f:
            legacy = json.load(f)
    except Exception:
        return
    if not isinstance(legacy, dict):
        return
    for it in legacy.get("items") or []:
        if not isinstance(it, dict):
            continue
        eid = str(it.get("id") or "").strip()
        if eid and eid in seen:
            continue
        if eid:
            seen.add(eid)
        src = (it.get("source") or "").strip()
        if ch_name and src and not src.startswith(ch_name + ":"):
            it = dict(it)
            it["source"] = f"{ch_name}:{src}"[:80]
        elif ch_name and not src:
            it = dict(it)
            it["source"] = ch_name[:80]
        items.append(it)


def _migrate_legacy_channel_clipboards(data: dict) -> dict:
    """一次性合并各频道子目录下旧剪贴板 JSON 到 ``program/program_clipboard.json``。"""
    if not isinstance(data, dict):
        data = {"items": []}
    items = data.setdefault("items", [])
    seen = {str(x.get("id", "")) for x in items if isinstance(x, dict) and x.get("id")}
    root = (config.BASE_PROGRAM_PATH or "").strip()
    if not root:
        root = os.path.join(config.BASE_MEDIA_PATH or "/AI_MEDIA", "program")
    global_path = os.path.normcase(_program_clipboard_file())
    if root and os.path.isdir(root):
        if not data.get("_migrated_channel_clipboards_v1"):
            pattern = os.path.join(root, "*", LEGACY_CHANNEL_CLIPBOARD_JSON_NAME)
            for fp in glob.glob(pattern):
                ch_name = os.path.basename(os.path.dirname(fp))
                _merge_legacy_clipboard_file_into_items(fp, items, seen, ch_name=ch_name)
            data["_migrated_channel_clipboards_v1"] = True
        if not data.get("_migrated_channel_program_clipboards_v1"):
            pattern2 = os.path.join(root, "*", PROGRAM_CLIPBOARD_JSON_NAME)
            for fp in glob.glob(pattern2):
                if os.path.normcase(fp) == global_path:
                    continue
                ch_name = os.path.basename(os.path.dirname(fp))
                _merge_legacy_clipboard_file_into_items(fp, items, seen, ch_name=ch_name)
            data["_migrated_channel_program_clipboards_v1"] = True
    return data


def _load_program_clipboard_data() -> dict:
    path = _program_clipboard_file()
    if not os.path.isfile(path):
        data = {"items": []}
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"items": []}
    if not isinstance(data, dict):
        data = {"items": []}
    if not isinstance(data.get("items"), list):
        data["items"] = []
    need_save = not (
        data.get("_migrated_channel_clipboards_v1")
        and data.get("_migrated_channel_program_clipboards_v1")
    )
    data = _migrate_legacy_channel_clipboards(data)
    items = data.get("items", [])
    if isinstance(items, list):
        deduped = _dedupe_program_clipboard_items_by_preview(items)
        if len(deduped) != len(items):
            data["items"] = deduped
            _save_program_clipboard_data(data)
    if need_save and data.get("_migrated_channel_clipboards_v1"):
        _save_program_clipboard_data(data)
    return data


def _save_program_clipboard_data(data: dict) -> None:
    write_json(_program_clipboard_file(), data)


def _program_clipboard_preview_key(item: dict) -> str:
    """用于去重的 preview 键（相同 preview 视为重复条目）。"""
    pv = (item.get("preview") or "").strip()
    if pv:
        return pv
    content = (item.get("content") or "").strip()
    return content[:64] if content else ""


def _dedupe_program_clipboard_items_by_preview(items: list) -> list:
    """相同 preview 只保留最新一条（列表靠后的条目）。"""
    kept: list = []
    seen: set[str] = set()
    for it in reversed(items):
        if not isinstance(it, dict):
            continue
        key = _program_clipboard_preview_key(it)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(it)
    kept.reverse()
    return kept


def _program_clipboard_make_id(existing: set) -> str:
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = base
    n = 0
    while uid in existing:
        n += 1
        uid = f"{base}_{n}"
    return uid


def _program_clipboard_source_label(channel_path: str, source: str) -> str:
    src = (source or "").strip()
    ch = (channel_path or "").strip()
    if ch:
        ch_tag = os.path.basename(os.path.normpath(ch))
        if ch_tag and src and not src.startswith(ch_tag + ":"):
            return f"{ch_tag}:{src}"[:80]
        if ch_tag and not src:
            return ch_tag[:80]
    return src[:80]


def program_clipboard_append_item(content: str, source: str, *, channel_path: str = "") -> str:
    """追加一条到 ``program`` 根目录 JSON 剪贴板（全频道共享），返回条目 id。

    相同 ``preview`` 已存在则不再追加，返回已有条目 id。
    """
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
    data = _load_program_clipboard_data()
    items = data.setdefault("items", [])
    new_preview = text[:64]
    for it in items:
        if isinstance(it, dict) and _program_clipboard_preview_key(it) == new_preview:
            return str(it.get("id") or "")
    existing = {str(x.get("id", "")) for x in items if isinstance(x, dict)}
    eid = _program_clipboard_make_id(existing)
    items.append(
        {
            "id": eid,
            "preview": new_preview,
            "content": text,
            "source": _program_clipboard_source_label(channel_path, source),
        }
    )
    _save_program_clipboard_data(data)
    return eid


def channel_clipboard_append_item(channel_path: str, content: str, source: str) -> str:
    """兼容旧名：写入全局 program 剪贴板；``channel_path`` 仅用于 ``source`` 标注频道。"""
    return program_clipboard_append_item(content, source, channel_path=channel_path)


def _read_host_clipboard_text(clipboard_host) -> str:
    try:
        return safe_clipboard_json_copy(clipboard_host.clipboard_get() or "")
    except tk.TclError:
        return ""


def _parse_json_object_from_clipboard_text(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _scene_json_dedupe_key(data: dict) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return repr(data)


def program_clipboard_sync_system_clipboard_item(
    clipboard_host,
    *,
    channel_path: str = "",
) -> str | None:
    """系统剪贴板有内容且与 program 剪贴板最后一条不同时，追加为 ``system_clipboard`` 条目。"""
    text = _read_host_clipboard_text(clipboard_host).strip()
    if not text:
        return None
    data = _load_program_clipboard_data()
    items = data.get("items", []) or []
    if items and isinstance(items[-1], dict):
        if (items[-1].get("content") or "").strip() == text:
            return None
    return program_clipboard_append_item(text, "system_clipboard", channel_path=channel_path)


def ask_cross_channel_clipboard_pick(
    parent,
    clipboard_host,
    channel_path: str = "",
) -> dict | None:
    """全频道剪贴板：首项为 Windows 系统剪贴板，其余为 ``program_clipboard.json`` 条目。

    返回可写入 scene_content 的 JSON 对象；取消或无效则返回 None。
    """
    entries: list[tuple[str, dict | None, str]] = []
    choices: list[tuple[str, str]] = []

    sys_text = _read_host_clipboard_text(clipboard_host).strip()
    if sys_text:
        sys_parsed = _parse_json_object_from_clipboard_text(sys_text)
        pv = (sys_text[:48] + "…") if len(sys_text) > 48 else sys_text
        pv = pv.replace("\n", " ")
        lbl = f"【Windows 系统剪贴板】 {pv}"
        if not sys_parsed:
            lbl += " （非 JSON 对象）"
        choices.append(("__windows__", lbl))
        entries.append(("__windows__", sys_parsed, sys_text))

    data = _load_program_clipboard_data()
    items = _dedupe_program_clipboard_items_by_preview(
        [x for x in data.get("items", []) if isinstance(x, dict)]
    )
    for it in reversed(items):
        content = (it.get("content") or "").strip()
        if not content:
            continue
        eid = str(it.get("id") or "").strip() or f"item_{len(entries)}"
        parsed = _parse_json_object_from_clipboard_text(content)
        src = (it.get("source") or "")[:20]
        pv = (it.get("preview") or content[:44]).replace("\n", " ")
        lbl = f"[{src}] {pv}…"
        if not parsed:
            lbl += " （非 JSON 对象/数组）"
        key = f"prog:{eid}"
        choices.append((key, lbl))
        entries.append((key, parsed, content))

    if not choices:
        show_auto_close_popup(
            parent,
            "全频道剪贴板",
            f"无可用条目。\n文件: {_program_clipboard_file()}",
        )
        return None

    picked = askchoice("全频道剪贴板", choices, parent=parent)
    if not picked:
        return None
    mode = picked[1]
    for key, parsed, _raw in entries:
        if key != mode:
            continue
        if parsed:
            return copy.deepcopy(parsed)
        messagebox.showwarning(
            "无效 Scene JSON",
            "所选内容须为 JSON 对象或数组，才能用于 scene_content 等后续操作。",
            parent=parent,
        )
        return None
    return None


def open_or_refresh_program_clipboard_manager(
    parent,
    clipboard_host,
    *,
    select_last: bool = False,
    on_pick=None,
):
    """打开或刷新全 program 剪贴板管理窗（列表 + 快捷键）。

    on_pick: 若提供 ``callable(str)``，Enter 仅回调内容（用于填入对话框等），不弹全文窗、不写系统剪贴板。
    """
    global _program_clipboard_manager_window
    win = _program_clipboard_manager_window
    if win is not None:
        try:
            if win.winfo_exists():
                win.set_on_pick(on_pick)
                win.refresh(select_last=select_last)
                win.lift()
                win.deiconify()
                win.after(10, lambda: win.listbox.focus_set())
                return win
        except tk.TclError:
            _program_clipboard_manager_window = None
    nw = ChannelClipboardManagerWindow(
        parent, clipboard_host, select_last=select_last, on_pick=on_pick
    )
    _program_clipboard_manager_window = nw

    def on_destroy(event):
        global _program_clipboard_manager_window
        if event.widget is nw and _program_clipboard_manager_window is nw:
            _program_clipboard_manager_window = None

    nw.bind("<Destroy>", on_destroy)
    return nw


def open_or_refresh_channel_clipboard_manager(
    parent,
    channel_path: str,
    clipboard_host,
    *,
    select_last: bool = False,
    on_pick=None,
):
    """兼容旧签名：``channel_path`` 已忽略，剪贴板为 ``BASE_PROGRAM_PATH`` 下全局共享。"""
    return open_or_refresh_program_clipboard_manager(
        parent,
        clipboard_host,
        select_last=select_last,
        on_pick=on_pick,
    )


class ChannelClipboardManagerWindow(tk.Toplevel):
    """全 program JSON 剪贴板：↑↓ 选择；Enter 默认复制到系统剪贴板并弹窗，或 on_pick 时仅回调；Delete 删项；Ctrl+Delete 清空。"""

    def __init__(
        self,
        parent,
        clipboard_host,
        *,
        select_last: bool = False,
        on_pick=None,
    ):
        super().__init__(parent)
        self.clipboard_host = clipboard_host
        self.on_pick = on_pick
        self.title("全频道剪贴板")
        self.geometry("920x460")
        self.minsize(640, 280)
        self._json_path = _program_clipboard_file()

        fr = ttk.Frame(self, padding=10)
        fr.pack(fill=tk.BOTH, expand=True)
        ttk.Label(fr, text=f"文件: {self._json_path}", font=("Consolas", 8), wraplength=880).pack(
            anchor=tk.W, pady=(0, 4)
        )
        self._hint_var = tk.StringVar(value="")
        ttk.Label(fr, textvariable=self._hint_var, wraplength=880, justify=tk.LEFT).pack(anchor=tk.W)
        self.listbox = tk.Listbox(fr, height=18, width=110, font=("Consolas", 9), exportselection=False)
        sb = ttk.Scrollbar(fr, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        row = ttk.Frame(fr)
        row.pack(fill=tk.BOTH, expand=True, pady=(6, 6))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        bf = ttk.Frame(fr)
        bf.pack(fill=tk.X)
        self._activate_btn = ttk.Button(bf, text="复制并查看 (Enter)", command=self._on_activate)
        self._activate_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf, text="刷新列表", command=lambda: self.refresh(select_last=False)).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf, text="关闭", command=self.destroy).pack(side=tk.RIGHT)

        self._items: list = []
        self._sync_pick_ui()
        self.refresh(select_last=select_last)

        self.listbox.bind("<Return>", self._on_return)
        self.listbox.bind("<KP_Enter>", self._on_return)
        self.listbox.bind("<Delete>", self._on_delete_one)
        self.bind("<Control-Delete>", self._on_clear_all)
        self.listbox.bind("<Double-Button-1>", lambda e: self._on_activate())

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.listbox.focus_set()

    def set_on_pick(self, on_pick):
        self.on_pick = on_pick
        self._sync_pick_ui()

    def _sync_pick_ui(self):
        if self.on_pick is not None:
            self._hint_var.set(
                "↑↓ 选择 · Enter 将所选内容填入导向说明（无预览、不写系统剪贴板）· Delete 删除当前项 · Ctrl+Delete 清空全部"
            )
            self._activate_btn.configure(text="填入导向说明 (Enter)")
        else:
            self._hint_var.set(
                "↑↓ 选择 · Enter 复制到系统剪贴板并查看全文 · Delete 删除当前项 · Ctrl+Delete 清空全部"
            )
            self._activate_btn.configure(text="复制并查看 (Enter)")
    def refresh(self, select_last: bool = False):
        self.listbox.delete(0, tk.END)
        data = _load_program_clipboard_data()
        raw = data.get("items", [])
        self._items = _dedupe_program_clipboard_items_by_preview(
            [x for x in raw if isinstance(x, dict)]
        )
        for it in self._items:
            eid = it.get("id", "")
            src = (it.get("source") or "")[:16]
            pv = (it.get("preview") or "")[:72].replace("\n", " ")
            self.listbox.insert(tk.END, f"[{src}] {eid}  {pv}")
        if not self._items:
            return
        if select_last:
            i = len(self._items) - 1
        else:
            i = 0
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(i)
        self.listbox.activate(i)
        self.listbox.see(i)

    def _paste_to_system_clipboard(self, text: str) -> None:
        for w in (self.clipboard_host, self.winfo_toplevel()):
            if w is None:
                continue
            try:
                w.clipboard_clear()
                w.clipboard_append(text)
                w.update_idletasks()
                return
            except tk.TclError:
                continue

    def _on_return(self, event=None):
        self._on_activate()
        return "break"

    def _on_activate(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = int(sel[0])
        if i < 0 or i >= len(self._items):
            return
        content = self._items[i].get("content", "") or ""
        if self.on_pick is not None:
            try:
                self.on_pick(content)
            except Exception:
                pass
            return
        self._paste_to_system_clipboard(content)
        self._popup_content_view(content)

    def _popup_content_view(self, content: str):
        top = tk.Toplevel(self)
        top.title("剪贴板条目 · 全文")
        top.geometry("820x560")
        top.transient(self)
        tx = scrolledtext.ScrolledText(top, wrap=tk.WORD, width=98, height=28, font=("Consolas", 10))
        tx.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tx.insert("1.0", content)
        tx.configure(state=tk.DISABLED)
        bf = ttk.Frame(top)
        bf.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(bf, text="确定", command=top.destroy).pack(side=tk.RIGHT, padx=8)

    def _on_delete_one(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = int(sel[0])
        if i < 0 or i >= len(self._items):
            return
        rm_id = self._items[i].get("id")
        data = _load_program_clipboard_data()
        data["items"] = [x for x in data.get("items", []) if isinstance(x, dict) and x.get("id") != rm_id]
        _save_program_clipboard_data(data)
        next_idx = max(0, i - 1)
        self.refresh(select_last=False)
        if self.listbox.size() > 0:
            next_idx = min(next_idx, self.listbox.size() - 1)
            self.listbox.selection_set(next_idx)
            self.listbox.activate(next_idx)
            self.listbox.see(next_idx)
        return "break"

    def _on_clear_all(self, event=None):
        if not messagebox.askyesno(
            "清空程序剪贴板",
            "确定删除 program 根目录 JSON 剪贴板中的全部条目？\n（所有频道共享，将一并清空。）",
            parent=self,
        ):
            return
        data = _load_program_clipboard_data()
        data["items"] = []
        _save_program_clipboard_data(data)
        self.refresh(select_last=False)
        return "break"


def _youtube_row_source_title(video_detail: dict) -> str:
    """原视频标题（列表行外层 ``title``，兼容旧顶层 ``video_title``）。"""
    if not isinstance(video_detail, dict):
        return ""
    return (video_detail.get("title") or video_detail.get("video_title") or "").strip()


def _youtube_row_project_title(video_detail: dict) -> str:
    """项目成片名（``project_profile.video_title``）。"""
    if not isinstance(video_detail, dict):
        return ""
    prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict):
        return (prof.get("video_title") or "").strip()
    return ""


def _youtube_row_story_meta_title(video_detail: dict) -> str:
    """Story JSON array 首条的 ``title``（无 project_profile 时摘要窗第二行展示）。"""
    if not isinstance(video_detail, dict):
        return ""
    entries = _parse_story_field(video_detail.get("story"))
    if not entries:
        return ""
    return (entries[0].get("title") or entries[0].get("caption") or "").strip()


def _youtube_row_display_title(video_detail: dict) -> str:
    """业务逻辑用标题：若有 ``project_profile.video_title`` 则优先成片名；否则原视频标题。"""
    proj = _youtube_row_project_title(video_detail)
    if proj:
        return proj
    return _youtube_row_source_title(video_detail)


def _youtube_row_list_suffix_title(video_detail: dict) -> str:
    """列表行标题后缀：``project_profile.video_title`` > story 首条 title > scene 首场景 caption。"""
    if not isinstance(video_detail, dict):
        return ""
    proj = _youtube_row_project_title(video_detail)
    if proj and proj not in _GENERIC_PROJECT_VIDEO_TITLES:
        return proj
    story_meta = _youtube_row_story_meta_title(video_detail)
    if story_meta:
        return story_meta
    sc = video_detail.get("scene_content")
    return (project_manager.title_from_scene_content(sc) or "").strip()


_CHANNEL_LIST_TREE_TITLE_MAX_SRC_CHARS = 40


def _youtube_row_list_display_title(
    video_detail: dict, *, max_src_chars: int | None = None
) -> str:
    """列表树展示用标题：``原视频标题 (成片名或 story title)``。

    ``max_src_chars``：有后缀时截断原标题，保证括号内项目/story 名可见。
    """
    src = _youtube_row_source_title(video_detail)
    suffix = _youtube_row_list_suffix_title(video_detail)

    def _trunc_src(s: str) -> str:
        if not max_src_chars or len(s) <= max_src_chars:
            return s
        return s[:max_src_chars].rstrip() + "…"

    if suffix and suffix != src:
        return f"{_trunc_src(src)} ({suffix})" if src else suffix
    return _trunc_src(src)


def _apply_video_detail_titles_from_ui(
    video_detail: dict,
    *,
    source_title: str,
    project_title: str = "",
    channel_path: str = "",
) -> None:
    """将摘要窗「视频名称」写回列表行：无项目时改 ``title``；有项目时改 ``title`` + ``project_profile.video_title``。"""
    if not isinstance(video_detail, dict):
        return
    src = (source_title or "").strip()
    proj = (project_title or "").strip()
    prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict) and prof:
        if src:
            video_detail["title"] = src
        if proj:
            merged = copy.deepcopy(prof)
            merged["video_title"] = proj
            video_detail[project_manager.PROJECT_PROFILE_KEY] = (
                project_manager.profile_for_list_storage(merged)
            )
    elif src:
        video_detail["title"] = src
    _normalize_channel_list_item_for_storage(video_detail, channel_path or "")


def _infer_channel_list_item_media_dir(item: dict, channel_path: str = "") -> str:
    """推断频道列表条目字幕/媒体目录 ``program/<ch>/Download/media``。"""
    if isinstance(item, dict):
        for key in ("transcribed_file", "audio_path", "video_path"):
            p = (item.get(key) or "").strip()
            if not p:
                continue
            d = os.path.dirname(os.path.abspath(p))
            if d and os.path.isdir(d):
                return d
            if d:
                return d
    ch = (channel_path or "").strip()
    if ch:
        return os.path.join(ch, "Download", "media")
    return ""


def _normalize_channel_list_item_for_storage(item: dict, channel_path: str = "") -> None:
    """无项目行：外层统一 ``title``，顶层 ``video_title`` 仅作旧数据合并进 ``title``。
    有 ``project_profile`` 的行：外层 ``title`` 表示原视频标题，不因顶层 ``video_title`` 改写 ``title``；收窄 ``project_profile``。"""
    if not isinstance(item, dict):
        return
    prof = item.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict) and prof:
        item.pop("video_title", None)
    else:
        t = (item.get("title") or "").strip()
        vt = (item.get("video_title") or "").strip()
        item["title"] = t if t else vt
        item.pop("video_title", None)
    item.pop("project_id", None)
    item.pop("project_pid", None)
    item.pop("pid", None)
    item.pop("youtube_source_id", None)
    item.pop("youtube_watch_url", None)
    item.pop("published_watch_url", None)
    config.migrate_content_to_transcribed_file(
        item,
        media_dir=_infer_channel_list_item_media_dir(item, channel_path),
    )
    prof = item.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict):
        item[project_manager.PROJECT_PROFILE_KEY] = project_manager.profile_for_list_storage(copy.deepcopy(prof))
    _sync_project_video_title_on_list_row(item)
    project_manager.sync_list_item_id_and_profile_pid(item)


_GENERIC_PROJECT_VIDEO_TITLES = frozenset({"", "新项目", "未命名", "default_title"})


def _sync_project_video_title_on_list_row(
    row: dict, selected_config: dict | None = None
) -> None:
    """``project_profile.video_title`` 优先 scene 首场景 caption，其次 story 首条 title，避免「新项目」占位。"""
    if not isinstance(row, dict):
        return
    prof = row.get(project_manager.PROJECT_PROFILE_KEY)
    if not isinstance(prof, dict) or not prof:
        return
    cfg = selected_config if isinstance(selected_config, dict) else {}
    sc = row.get("scene_content") or cfg.get("scene_content")
    sc_title = (project_manager.title_from_scene_content(sc) or "").strip()
    story_title = _youtube_row_story_meta_title(row)
    vt = (prof.get("video_title") or cfg.get("video_title") or "").strip()
    if vt and vt not in _GENERIC_PROJECT_VIDEO_TITLES:
        return
    pick = sc_title or story_title
    if not pick:
        return
    merged = copy.deepcopy(prof)
    merged["video_title"] = pick
    row[project_manager.PROJECT_PROFILE_KEY] = project_manager.profile_for_list_storage(
        merged
    )


def _drop_cloned_duplicates_of_row(videos: list, keeper: dict) -> list:
    """从频道热门列表去掉同一源视频的旧克隆行，只保留 ``keeper``。"""
    if not isinstance(keeper, dict):
        return list(videos or [])
    keep_pid = project_manager.list_json_row_workflow_pid(keeper)
    keep_url = (keeper.get("url") or "").strip()
    out = []
    for v in videos or []:
        if not isinstance(v, dict):
            continue
        if project_manager.list_json_row_workflow_pid(v) == keep_pid:
            out.append(v)
            continue
        cfu = (v.get("cloned_from_url") or "").strip()
        if keep_url and cfu == keep_url:
            continue
        out.append(v)
    return out


def _apply_project_config_to_list_row(
    row: dict, selected_config: dict, *, channel_path: str = ""
) -> None:
    """将新建/更新后的项目配置写入频道热门列表中的源视频行（不克隆新行；保留外层 YouTube ``id``）。"""
    row.pop("cloned_from_id", None)
    row.pop("cloned_from_url", None)
    row.pop("youtube_source_id", None)
    row[project_manager.PROJECT_PROFILE_KEY] = project_manager.profile_for_list_storage(
        project_manager.export_profile_for_storage(copy.deepcopy(selected_config))
    )
    for k in (
        "story",
        "analyzed_content",
        "scene_content",
        "topic_category",
        "topic_subtype",
        "tags",
        "language",
    ):
        if k in selected_config and selected_config.get(k) is not None:
            row[k] = copy.deepcopy(selected_config[k])
    row.pop("project_id", None)
    row.pop("project_pid", None)
    row.pop("pid", None)
    _sync_project_video_title_on_list_row(row, selected_config)
    _normalize_channel_list_item_for_storage(row, channel_path or "")


def _remove_pid_from_topic_category_lists(channel_path: str, pid: str) -> None:
    """项目 pid 变更后，从各主题分表中移除旧 pid 行。"""
    pid = (pid or "").strip()
    ch = (channel_path or "").strip()
    if not pid or not ch:
        return
    list_dir = config.channel_list_json_dir_abs(ch)
    if not os.path.isdir(list_dir):
        return
    for name in os.listdir(list_dir):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(list_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(arr, list):
            continue
        new_arr = [
            it
            for it in arr
            if not (isinstance(it, dict) and _list_json_item_matches_pid(it, pid))
        ]
        if len(new_arr) == len(arr):
            continue
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(new_arr, f, ensure_ascii=False, indent=2)
        except OSError:
            pass


def _normalize_channel_videos_for_storage(items, channel_path: str = "") -> None:
    """就地规范化列表条目。"""
    if not items:
        return
    for it in items:
        if isinstance(it, dict):
            _normalize_channel_list_item_for_storage(it, channel_path)


def _ensure_topic_category_list_files(channel_path: str, topic_categories) -> None:
    """为 topics.json 中每个 topic_category 在频道 program 下放空列表 JSON（尚无文件时）。"""
    if not channel_path or not os.path.isdir(channel_path):
        return
    seen = set()
    for cat in topic_categories or []:
        c = (cat or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        p = _topic_category_program_list_path(channel_path, c)
        if os.path.isfile(p):
            continue
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        except OSError:
            pass


def _channel_list_row_tree_key(video: dict) -> str:
    """树视图 tag / 查找键：优先外层 ``id``，否则 ``url``。"""
    if not isinstance(video, dict):
        return ""
    iid = project_manager.list_json_row_id(video)
    if iid:
        return iid
    return (video.get("url") or "").strip()


def _channel_list_row_dedupe_key(video: dict) -> str:
    """列表去重键：优先外层 ``id``（YouTube id 或独立行 id）；无 id 再按 ``url``；最后按展示标题。"""
    if not isinstance(video, dict):
        return ""
    iid = project_manager.list_json_row_id(video)
    if iid:
        return f"id:{iid}"
    u = (video.get("url") or "").strip()
    if u:
        return f"url:{u}"
    t = _youtube_row_display_title(video).strip().lower()
    if t:
        return f"title:{t}"
    return f"row:{id(video)}"


def _channel_list_row_complete_score(video: dict) -> int:
    c = config.read_transcript_text_from_video_detail(video)
    cat = (video.get("topic_category") or "").strip()
    sub = (video.get("topic_subtype") or "").strip()
    content_len = len(c)
    if cat and sub:
        return 1_000_000 + content_len
    return content_len


def dedupe_channel_video_list(videos: list) -> list:
    """仅合并去重键完全相同的行；勿按展示标题误删不同项目/不同 url 的条目。"""
    by_key = {}
    for video in videos or []:
        if not isinstance(video, dict):
            continue
        key = _channel_list_row_dedupe_key(video)
        if not key:
            continue
        if key not in by_key:
            by_key[key] = video
            continue
        cur = by_key[key]
        if _channel_list_row_complete_score(video) > _channel_list_row_complete_score(cur):
            by_key[key] = video
    return list(by_key.values())


def _topic_split_list_find_pid_for_channel(
    channel_path: str,
    *,
    preferred_topic_category: str,
    topic_categories,
    pid: str,
):
    """在频道 ``list/<主题>.json`` 分表中查找 ``pid``；优先 ``preferred_topic_category``，再遍历 ``topic_categories``。"""
    pid = (pid or "").strip()
    if not pid or not channel_path:
        return None, None
    ordered = []
    pt = (preferred_topic_category or "").strip()
    if pt:
        ordered.append(pt)
    for tc in topic_categories or []:
        c = (tc or "").strip()
        if c and c not in ordered:
            ordered.append(c)
    seen_paths = set()
    for tc in ordered:
        path = _topic_category_program_list_path(channel_path, tc)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(arr, list):
            continue
        for item in arr:
            if _list_json_item_matches_pid(item, pid):
                return tc, path
    return None, None


def _is_viewing_topic_category_program_list(
    channel_path: str, list_json_path: str, topic_category: str
) -> bool:
    """当前打开的 ``channel_list_json`` 是否即为某主题分表（``list/<topic>.json``）。"""
    list_json_path = (list_json_path or "").strip()
    topic_category = (topic_category or "").strip()
    if not list_json_path or not topic_category:
        return False
    topic_path = _topic_category_program_list_path(channel_path, topic_category)
    if not topic_path:
        return False
    return os.path.normcase(os.path.normpath(list_json_path)) == os.path.normcase(
        os.path.normpath(topic_path)
    )


def _upsert_topic_category_program_list_row(channel_path: str, topic_category: str, entry: dict) -> str:
    """按 ``pid`` 对指定主题分表做 upsert（去掉同 PID 旧行再追加），返回写入路径。"""
    path = _topic_category_program_list_path(channel_path, topic_category or "")
    pid = _video_detail_project_pid(entry)
    arr = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)
        except (json.JSONDecodeError, OSError):
            arr = []
    if not isinstance(arr, list):
        arr = []
    if pid:
        arr = [it for it in arr if isinstance(it, dict) and not _list_json_item_matches_pid(it, pid)]
    arr.append(copy.deepcopy(entry))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False, indent=2)
    return path


def _clone_channel_video_for_new_project(base: dict, selected_config: dict) -> dict:
    """基于当前列表项生成新条目：``id`` = 项目 pid，不继承源 ``url`` / ``upload_date``（发布后只写 ``url``）；源链接记入 ``cloned_from_*``。"""
    if not isinstance(base, dict):
        raise ValueError("base 无效")
    if not isinstance(selected_config, dict):
        raise ValueError("selected_config 无效")
    pid = (selected_config.get("pid") or "").strip()
    if not pid:
        raise ValueError("缺少项目 pid")
    clone = copy.deepcopy(base)
    clone["id"] = pid
    clone.pop("gen_video_stem", None)
    clone.pop("video_title", None)
    lang = selected_config.get("language")
    if lang:
        clone["language"] = lang
    if "scene_content" in selected_config:
        clone["scene_content"] = copy.deepcopy(selected_config["scene_content"])
    if "analyzed_content" in selected_config:
        clone["analyzed_content"] = copy.deepcopy(selected_config["analyzed_content"])
    if (base.get("story") or "").strip():
        clone["story"] = copy.deepcopy(base["story"])
    if "topic_category" in selected_config:
        tc = selected_config.get("topic_category")
        clone["topic_category"] = tc if tc else None
    if "topic_subtype" in selected_config:
        clone["topic_subtype"] = selected_config.get("topic_subtype")
    if "tags" in selected_config:
        tg = selected_config.get("tags")
        if tg:
            clone["tags"] = copy.deepcopy(tg)
        else:
            clone.pop("tags", None)
    for k in (
        "url",
        "upload_date",
        "view_count",
        "duration",
        "video_path",
        "audio_path",
        "transcribed_file",
        "captions",
        "publish",
        "create_date",
        "content",
        "summary",
        "playlist_id",
        "playlist_index",
        "thumb_url",
        "youtube_channel_id",
        "youtube_channel_name",
        "youtube_channel_thumbnail",
        "youtube_source_id",
        "youtube_watch_url",
        "published_watch_url",
    ):
        clone.pop(k, None)
    clone["status"] = ""
    clone.pop("project_id", None)
    clone.pop("project_pid", None)
    clone.pop("pid", None)
    clone[project_manager.PROJECT_PROFILE_KEY] = project_manager.profile_for_list_storage(
        project_manager.export_profile_for_storage(copy.deepcopy(selected_config))
    )
    prof = clone.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict):
        old_vt = ""
        base_prof = base.get(project_manager.PROJECT_PROFILE_KEY)
        if isinstance(base_prof, dict):
            old_vt = (base_prof.get("video_title") or "").strip()
        new_vt = (prof.get("video_title") or "").strip()
        if not new_vt:
            lang = (selected_config.get("language") or clone.get("language") or "tw").strip()
            new_vt = (
                project_manager.title_from_scene_content(
                    selected_config.get("scene_content")
                )
                or ""
            ).strip()
        if not new_vt:
            new_vt = f"项目 {pid}"
        if old_vt and new_vt == old_vt:
            new_vt = f"{new_vt} ({pid})"
        prof["video_title"] = new_vt
    orig_id = (base.get("id") or "").strip()
    if orig_id:
        clone["cloned_from_id"] = orig_id
    orig_url = (base.get("url") or "").strip()
    if orig_url:
        clone["cloned_from_url"] = orig_url
    _sync_project_video_title_on_list_row(clone, selected_config)
    _normalize_channel_list_item_for_storage(clone)
    return clone


def _video_detail_project_pid(vd) -> str:
    """列表项绑定的工作流 pid（仅 ``project_profile.pid``）。"""
    return project_manager.list_json_row_workflow_pid(vd if isinstance(vd, dict) else {})


def _list_json_item_matches_pid(item: dict, wanted_pid: str) -> bool:
    """主题分表或列表中的一行是否与给定 ``pid`` 对应（优先 ``project_profile.pid``）。"""
    wanted_pid = (wanted_pid or "").strip()
    if not wanted_pid or not isinstance(item, dict):
        return False
    return project_manager.list_json_row_workflow_pid(item) == wanted_pid


def _launch_gui_wf_open_pid(pid: str, *, parent=None) -> bool:
    """另起进程启动 ``GUI_wf.py --open-pid``，与在主窗口用 ``--open-pid`` /「选择项目→打开」后的加载逻辑一致。"""
    pid = (pid or "").strip()
    if not pid:
        return False
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(repo_root, "GUI_wf.py")
    if not os.path.isfile(script):
        show_auto_close_popup(parent, "无法启动魔法工作流", f"找不到工作流脚本：\n{script}", kind="error")
        return False
    cmd = [sys.executable, script, "--open-pid", pid]
    try:
        subprocess.Popen(cmd, cwd=repo_root)
        return True
    except Exception as e:
        show_auto_close_popup(parent, "无法启动魔法工作流", str(e), kind="error")
        return False


def _launch_gui_wf_from_list_json(list_json_path: str, index: int, *, parent=None) -> bool:
    """启动 ``GUI_wf.py --open-from-list-json``，从频道热门列表 JSON 的一行载入完整 ``project_profile``。"""
    list_json_path = (list_json_path or "").strip()
    if not list_json_path or not os.path.isfile(list_json_path):
        return False
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(repo_root, "GUI_wf.py")
    if not os.path.isfile(script):
        show_auto_close_popup(parent, "无法启动魔法工作流", f"找不到工作流脚本：\n{script}", kind="error")
        return False
    cmd = [sys.executable, script, "--open-from-list-json", os.path.normpath(list_json_path), str(int(index))]
    try:
        subprocess.Popen(cmd, cwd=repo_root)
        return True
    except Exception as e:
        show_auto_close_popup(parent, "无法启动魔法工作流", str(e), kind="error")
        return False
def _video_youtube_id(v):
    """从频道视频项解析 YouTube 视频 id（11 位）。

    有 ``project_profile`` 的行：外层 ``id`` 可仍为源 YouTube id；亦从 ``url`` / ``cloned_from_url`` 解析。
    无项目行：``id`` 或 ``url`` 均可。
    """
    if not isinstance(v, dict):
        return ""
    has_proj = project_manager.list_json_row_has_project_profile(v)
    if not has_proj:
        vid = (v.get("id") or "").strip()
        if vid and len(vid) == 11:
            return vid
    for key in ("url", "cloned_from_url"):
        u_pub = (v.get(key) or "").strip()
        if u_pub:
            m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", u_pub)
            if m:
                return m.group(1)
            m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", u_pub)
            if m:
                return m.group(1)
    if has_proj:
        vid = (v.get("id") or "").strip()
        if vid and project_manager.list_row_outer_id_in_watch_url(v):
            return vid
        return ""
    vid = (v.get("id") or "").strip()
    if vid and len(vid) == 11:
        return vid
    return ""


def _video_id_present_in_url(v: dict) -> bool:
    """外层 ``id`` 是否为 ``url`` 中的 YouTube 视频 id（源下载行 / 热门总表同行绑定项目）。

    新建项目克隆行：``id`` 为 pid，``url`` 空或仅为发布后链接（pid 不在 url 中）→ False。
    """
    if not isinstance(v, dict):
        return False
    vid = (v.get("id") or "").strip()
    if not vid:
        return False
    url = (v.get("url") or "").strip()
    if not url:
        return False
    if re.search(rf"[?&]v={re.escape(vid)}(?:&|$)", url):
        return True
    if re.search(rf"youtu\.be/{re.escape(vid)}(?:[?&#/]|$)", url):
        return True
    return False


def _should_update_upload_date(video: dict) -> bool:
    """是否允许用 YouTube API / yt-dlp 的 ``upload_date`` 写入本条（下载、频道刷新）。

    克隆项目行（``cloned_from_*``）跳过；源下载行及发布后 ``url`` 已变的行均允许更新。
    本工具发布到 YouTube 不写 ``upload_date``，改写 ``create_date``（见 ``_apply_publish_create_date``）。
    """
    if not isinstance(video, dict):
        return False
    if (video.get("cloned_from_url") or video.get("cloned_from_id") or "").strip():
        return False
    return True


def _apply_publish_create_date(
    video_detail: dict,
    *,
    publish_at,
    published_iso: str = "",
) -> None:
    """记录本工具上传到 YouTube 的日期（``create_date``，YYYYMMDD）；不改 ``upload_date``。"""
    if not isinstance(video_detail, dict):
        return
    iso = (published_iso or "").strip()
    if iso:
        try:
            _dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            video_detail["create_date"] = _dt.astimezone().strftime("%Y%m%d")
            return
        except Exception:
            pass
    if publish_at is not None:
        local_tz = datetime.now().astimezone().tzinfo
        pa = (
            publish_at
            if getattr(publish_at, "tzinfo", None)
            else publish_at.replace(tzinfo=local_tz)
        )
        video_detail["create_date"] = pa.astimezone().strftime("%Y%m%d")
    else:
        video_detail["create_date"] = datetime.now().strftime("%Y%m%d")


def _gen_video_id_stem_candidates_for_row(video: dict) -> list[str]:
    """匹配 / 命名 gen_video 里 ``<stem>.mp4`` 的候选 stem（有序、去重）。
    含外层 ``id``、YouTube id、``project_profile.pid`` 及旧字段。"""
    if not isinstance(video, dict):
        return []
    ordered: list[str] = []
    seen: set[str] = set()

    def add_raw(raw: object) -> None:
        s = _sanitize_list_row_id_stem(str(raw or "").strip())
        if s and s not in seen:
            seen.add(s)
            ordered.append(s)

    add_raw(video.get("id"))
    add_raw(_video_youtube_id(video))
    add_raw(video.get("youtube_id"))
    pp = video.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(pp, dict):
        add_raw(pp.get("youtube_video_id"))
        add_raw(pp.get("youtube_id"))
        add_raw(pp.get("video_id"))
        add_raw(pp.get("source_video_id"))
    add_raw(_video_detail_project_pid(video))
    return ordered


def _find_gen_video_mp4_for_row(video: dict) -> str:
    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if not gen_dir:
        return ""
    try:
        os.makedirs(gen_dir, exist_ok=True)
    except OSError:
        pass
    for stem in _gen_video_id_stem_candidates_for_row(video):
        p = os.path.join(gen_dir, stem + ".mp4")
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""


def _find_gen_video_webp_for_row(video: dict) -> str:
    """``gen_video/<id>.webp`` 封面（摘要窗拖入/粘贴图片并加水印后）。"""
    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if not gen_dir:
        return ""
    for stem in _gen_video_id_stem_candidates_for_row(video):
        p = os.path.join(gen_dir, stem + ".webp")
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""


def _gen_video_storage_dir() -> str:
    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if gen_dir:
        try:
            os.makedirs(gen_dir, exist_ok=True)
        except OSError:
            pass
    return gen_dir


def _open_feature_media_in_explorer(*preferred_files: str) -> None:
    """打开 ``publish/gen_video``；若已有成片/封面则选中对应文件。"""
    gen_dir = _gen_video_storage_dir()
    target = ""
    for fp in preferred_files:
        p = (fp or "").strip()
        if p and os.path.isfile(p):
            target = os.path.normpath(p)
            break
    if target:
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", target], check=False)
        else:
            folder = os.path.dirname(target)
            if folder and os.path.isdir(folder):
                if sys.platform == "darwin":
                    subprocess.run(["open", "-R", target], check=False)
                else:
                    subprocess.run(["xdg-open", folder], check=False)
        return
    if gen_dir and os.path.isdir(gen_dir):
        if sys.platform == "win32":
            os.startfile(gen_dir)
        elif sys.platform == "darwin":
            subprocess.run(["open", gen_dir], check=False)
        else:
            subprocess.run(["xdg-open", gen_dir], check=False)


def _copy_image_file_to_clipboard(parent, image_path: str) -> bool:
    """将图片文件复制到 Windows 剪贴板（CF_DIB）。"""
    from io import BytesIO

    image_path = (image_path or "").strip()
    if not image_path or not os.path.isfile(image_path):
        messagebox.showwarning("提示", "图片文件不存在。", parent=parent)
        return False
    try:
        import win32clipboard  # type: ignore
        from PIL import Image

        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        output = BytesIO()
        img.save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except ImportError:
        messagebox.showwarning(
            "提示",
            "复制图片到剪贴板需要 pywin32 与 Pillow。\n请运行: pip install pywin32",
            parent=parent,
        )
        return False
    except Exception as exc:
        show_auto_close_popup(parent, "复制失败", str(exc), kind="error")
        return False


def _merge_related_id_status(existing, new_id):
    new_id = (new_id or "").strip()
    if not new_id:
        return (existing or "").strip()
    parts = [p.strip() for p in str(existing or "").split("|") if p.strip()]
    if new_id not in parts:
        parts.append(new_id)
    return "|".join(parts)


def _find_video_by_youtube_id(channel_videos, yid):
    yid = (yid or "").strip()
    if not yid:
        return None
    for v in channel_videos or []:
        if _video_youtube_id(v) == yid:
            return v
    return None


# INPUT_MEDIA_PATH 下 __数字__简码__标题_.txt，JSON 含 id → 同目录同 stem 的 .mp4 可发布；发布后同 stem 的 mp4/png/txt 可归档到简码/topic_category 对应的子文件夹（如 Identity__...）
_INPUT_PUBLISH_TXT_RE = re.compile(r"^__\d+__.+\.txt$", re.IGNORECASE)


def _scan_input_media_publish_map():
    """扫描 config.INPUT_MEDIA_PATH，返回 {youtube_id: {txt_path, mp4_path}}。"""
    out = {}
    base = getattr(config, "INPUT_MEDIA_PATH", None)
    if not base or not os.path.isdir(base):
        return out
    try:
        for name in os.listdir(base):
            if not _INPUT_PUBLISH_TXT_RE.match(name):
                continue
            txt_path = os.path.join(base, name)
            if not os.path.isfile(txt_path):
                continue
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            yid = (data.get("id") or "").strip()
            if not yid:
                continue
            stem = os.path.splitext(name)[0]
            mp4_path = os.path.join(base, stem + ".mp4")
            out[yid] = {"txt_path": txt_path, "mp4_path": mp4_path}
    except Exception:
        pass
    return out


def _folder_english_prefix(folder_name: str) -> str:
    """如 Identity__人格防御... → 'Identity'。"""
    if not folder_name:
        return ""
    return folder_name.split("__", 1)[0] if "__" in folder_name else folder_name


def _parse_input_media_category_short_code(basename_no_ext: str) -> str:
    """从 __102__Identi__Slug_ 形式解析中间简码（如 Identi）。"""
    if not basename_no_ext.startswith("__"):
        return ""
    parts = basename_no_ext.split("__")
    if len(parts) >= 4 and parts[1].isdigit():
        return (parts[2] or "").strip()
    return ""


def _find_category_subfolder(parent_dir: str, short_code: str, topic_category: str):
    """在 parent_dir 下找与 video_detail['topic_category'] 或文件名简码前缀匹配的子文件夹。"""
    try:
        names = os.listdir(parent_dir)
    except OSError:
        return None
    dirs = [n for n in names if os.path.isdir(os.path.join(parent_dir, n))]
    tc = (topic_category or "").strip()
    if tc:
        for n in dirs:
            en = _folder_english_prefix(n)
            if en == tc or n.startswith(tc + "__"):
                return n
    sc = (short_code or "").strip()
    if not sc:
        return None
    best = None
    best_len = -1
    for n in dirs:
        en = _folder_english_prefix(n)
        if en.startswith(sc) and len(en) > best_len:
            best = n
            best_len = len(en)
    return best


def _is_windows_file_in_use(err: OSError) -> bool:
    """WinError 32：文件正被另一进程使用。"""
    if getattr(err, "winerror", None) == 32:
        return True
    # 非 Windows：EBUSY 等
    en = getattr(err, "errno", None)
    return en in (11, 16, 26)  # EAGAIN, EBUSY, ETXTBSY 等视平台而定


def _tk_dialog_parent(preferred, fallback=None):
    """messagebox 父窗口：preferred 已关闭时回退 fallback，避免 parent 销毁后弹窗报错。"""
    for w in (preferred, fallback):
        if w is None:
            continue
        try:
            if w.winfo_exists():
                return w
        except tk.TclError:
            continue
    return fallback


def _set_publish_review_publishing(parent, publishing: bool) -> None:
    try:
        pr = getattr(parent, "_publish_review", None)
        if pr is not None:
            pr._publishing = bool(publishing)
    except Exception:
        pass


def _run_on_main_tk_and_wait(root, fn, timeout=60) -> None:
    """后台线程中等待 Tk 主线程执行 fn（释放播放器句柄等）。"""
    ev = threading.Event()
    err: list = [None]

    def _run():
        try:
            fn()
        except Exception as e:
            err[0] = e
        finally:
            ev.set()

    root.after(0, _run)
    if not ev.wait(timeout=timeout):
        raise TimeoutError("主线程操作超时")
    if err[0]:
        raise err[0]


def _release_publish_review_if_same_mp4(parent, mp4_path: str) -> None:
    """审阅窗口若正在播放同一 mp4，先 _stop_play，避免归档/覆盖时 WinError 32。"""
    try:
        pr = getattr(parent, "_publish_review", None)
        if not pr:
            return
        p = os.path.normcase(os.path.abspath(getattr(pr, "mp4_path", "") or ""))
        m = os.path.normcase(os.path.abspath(mp4_path or ""))
        if p == m and hasattr(pr, "_stop_play"):
            pr._stop_play()
            time.sleep(0.15)  # 给 OS 释放 mp4 句柄一点时间
    except Exception:
        pass


def _move_file_to_dest_with_fallback(src: str, dst: str) -> None:
    """优先 move；失败时 copy2 再删源。对「文件正被使用」短暂重试（预览刚停时句柄未立即释放）。"""
    retries = 12
    delay = 0.3
    last_err: OSError | None = None
    for attempt in range(retries):
        try:
            shutil.move(src, dst)
            return
        except OSError as e:
            last_err = e
            if _is_windows_file_in_use(e) and attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 1.2, 2.0)
                continue
            break
    delay = 0.3
    for attempt in range(retries):
        try:
            shutil.copy2(src, dst)
            try:
                os.remove(src)
            except OSError as rm_err:
                if _is_windows_file_in_use(rm_err) and attempt < retries - 1:
                    time.sleep(delay)
                    delay = min(delay * 1.2, 2.0)
                    continue
                raise
            return
        except OSError as e:
            last_err = e
            if _is_windows_file_in_use(e) and attempt < retries - 1:
                time.sleep(delay)
                delay = min(delay * 1.2, 2.0)
                continue
            raise
    if last_err:
        raise last_err


def _is_already_in_category_folder(current_dir: str, short_code: str, topic_category: str) -> bool:
    """已在名称匹配的子文件夹内（如 Identity__xxx）则不再移动。"""
    base = os.path.basename(current_dir.rstrip("/\\"))
    if not base:
        return False
    en = _folder_english_prefix(base)
    tc = (topic_category or "").strip()
    if tc and en == tc:
        return True
    sc = (short_code or "").strip()
    if sc and en.startswith(sc):
        return True
    return False


def _move_published_input_media_files(mp4_path: str, video_detail: dict) -> str:
    """发布后把同 stem 的 mp4/png/txt 移入同级分类子文件夹；返回给 UI 的说明。"""
    mp4_path = os.path.abspath(mp4_path)
    parent = os.path.dirname(mp4_path)
    stem, _ = os.path.splitext(os.path.basename(mp4_path))
    short_code = _parse_input_media_category_short_code(stem)
    topic_category = (video_detail.get("topic_category") or "").strip()

    if not short_code and not topic_category:
        return ""

    if _is_already_in_category_folder(parent, short_code, topic_category):
        return "成品已在分类文件夹内，未移动。"

    sub = _find_category_subfolder(parent, short_code, topic_category)
    if not sub:
        hint = short_code or topic_category
        return f"未找到与「{hint}」对应的分类子文件夹，文件未移动。"

    dest_dir = os.path.join(parent, sub)
    if not os.path.isdir(dest_dir):
        return "分类文件夹不存在，未移动。"

    moved = []
    for ext in (".mp4", ".png", ".txt"):
        src = os.path.join(parent, stem + ext)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dest_dir, os.path.basename(src))
        if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
            continue
        try:
            _move_file_to_dest_with_fallback(src, dst)
            moved.append(ext)
        except OSError as e:
            return f"归档失败（{ext}）：{e}"

    if not moved:
        return "未找到可移动的同名 .mp4/.png/.txt，未移动。"
    return f"已将成品移入文件夹：{sub}"


def _format_publish_display_date(pub_s: str) -> str:
    """将已发布时间的多种字符串格式压成 yyyy-mm-dd（只精确到天）。"""
    s = (pub_s or "").strip()
    if not s:
        return ""
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00").split("+")[0])
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return s[:10] if len(s) >= 10 else s


def _publish_cell_display(video: dict, input_map: dict):
    """返回 (列文本, 状态 published|ready|txt|na, 用于发布的 mp4 绝对路径)。

    可发布：优先 gen_video 下任一条目候选 stem 的 ``.mp4``（参见 ``_find_gen_video_mp4_for_row``）；其次 input 目录 __*__.txt + 同名 mp4。
    已上传：``publish`` 有值即显示为已发布。
    """
    pub = (video.get("publish") or "").strip()
    if pub:
        return _format_publish_display_date(pub) + " ✓", "published", ""

    mp4_gv = _gen_video_publish_mp4_if_ready(video)
    if mp4_gv:
        return "ready", "ready", mp4_gv

    yid = _video_youtube_id(video)
    if yid and yid in input_map:
        entry = input_map[yid] or {}
        txt_path = (entry.get("txt_path") or "").strip()
        mp4_path = os.path.abspath(entry.get("mp4_path") or "") if entry.get("mp4_path") else ""
        if txt_path and os.path.isfile(txt_path):
            if mp4_path and os.path.isfile(mp4_path):
                return "ready", "ready", mp4_path
            return "TXT", "txt", ""

    return "N/A", "na", ""


def _resolve_review_publish_mp4_path(video_detail: dict, input_map: dict) -> str:
    """本条用于「审阅并发布」的成品 mp4：gen_video → input 联名；不限于列表「ready」状态（已上传也可再找文件重投）。"""
    if not isinstance(video_detail, dict):
        return ""
    _, _, mp4 = _publish_cell_display(video_detail, input_map)
    p = (mp4 or "").strip()
    if p and os.path.isfile(p):
        return os.path.abspath(p)
    gv = _gen_video_publish_mp4_if_ready(video_detail)
    if gv and os.path.isfile(gv):
        return gv
    yid = _video_youtube_id(video_detail)
    if yid and yid in input_map:
        cand = (input_map.get(yid) or {}).get("mp4_path") or ""
        cand = cand.strip()
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)
    return ""


def ask_publish_schedule_dialog(parent, mp4_path_hint=None, dialog_title="上传至 YouTube"):
    """
    与 GUI_wf.py _ask_upload_schedule 相同：立即上传或定时公开；tkcalendar 可选。
    返回 None 表示取消；("immediate", None) 或 ("scheduled", datetime)。
    """
    result = {"ok": False, "mode": "immediate", "dt": None}
    dlg = tk.Toplevel(parent)
    dlg.title(dialog_title)
    dlg.transient(parent)
    dlg.resizable(True, True)
    dlg.geometry("440x560")
    dlg.grab_set()

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    if mp4_path_hint:
        ttk.Label(frm, text=f"视频文件:\n{mp4_path_hint}", wraplength=410, justify=tk.LEFT).pack(anchor="w", pady=(0, 8))

    ttk.Label(
        frm,
        text=(
            "YouTube API 支持定时「公开」：上传时为私有，到点自动公开。\n"
            "「首映 Premiere」需在 YouTube Studio 里单独设置。"
        ),
        wraplength=410,
        justify=tk.LEFT,
    ).pack(anchor="w", pady=(0, 10))

    mode_var = tk.StringVar(value="scheduled")
    ttk.Radiobutton(
        frm,
        text="立即上传（不公开列出，与原先一致）",
        variable=mode_var,
        value="immediate",
    ).pack(anchor="w")
    ttk.Radiobutton(
        frm,
        text="定时发布（指定日期与时刻后由 YouTube 自动公开）",
        variable=mode_var,
        value="scheduled",
    ).pack(anchor="w", pady=(0, 6))

    sched_frame = ttk.LabelFrame(frm, text="日期与时间（本机本地时区）", padding=8)
    sched_frame.pack(fill=tk.BOTH, expand=True, pady=6)

    now = datetime.now()
    local_tz = now.astimezone().tzinfo

    cal_widget = None
    y_var = tk.IntVar(value=now.year)
    m_var = tk.IntVar(value=now.month)
    d_var = tk.IntVar(value=now.day)
    h_var = tk.IntVar(value=min(now.hour + 1, 23))
    min_var = tk.IntVar(value=0)

    if TkCalendar is not None:
        cal_widget = TkCalendar(
            sched_frame,
            selectmode="day",
            date_pattern="yyyy-mm-dd",
            year=now.year,
            month=now.month,
            day=now.day,
        )
        cal_widget.pack(pady=4)
    else:
        rowd = ttk.Frame(sched_frame)
        rowd.pack(fill=tk.X, pady=2)
        ttk.Label(rowd, text="年").pack(side=tk.LEFT)
        tk.Spinbox(rowd, from_=now.year, to=now.year + 3, textvariable=y_var, width=6).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(rowd, text="月").pack(side=tk.LEFT)
        tk.Spinbox(rowd, from_=1, to=12, textvariable=m_var, width=4).pack(side=tk.LEFT, padx=4)
        ttk.Label(rowd, text="日").pack(side=tk.LEFT)
        tk.Spinbox(rowd, from_=1, to=31, textvariable=d_var, width=4).pack(side=tk.LEFT, padx=4)

    rowt = ttk.Frame(sched_frame)
    rowt.pack(fill=tk.X, pady=4)
    ttk.Label(rowt, text="时 (0–23)").pack(side=tk.LEFT)
    tk.Spinbox(rowt, from_=0, to=23, textvariable=h_var, width=4).pack(side=tk.LEFT, padx=6)
    ttk.Label(rowt, text="分 (0–59)").pack(side=tk.LEFT)
    tk.Spinbox(rowt, from_=0, to=59, textvariable=min_var, width=4).pack(side=tk.LEFT, padx=6)

    btn_row = ttk.Frame(frm)
    btn_row.pack(fill=tk.X, pady=(12, 0))

    def on_ok():
        if mode_var.get() == "immediate":
            result["ok"] = True
            result["mode"] = "immediate"
            result["dt"] = None
            dlg.destroy()
            return
        if TkCalendar is not None and cal_widget is not None:
            dstr = cal_widget.get_date()
            try:
                y, mo, da = map(int, dstr.split("-"))
            except ValueError:
                show_auto_close_popup(dlg, "日期错误", "无法解析日历日期（需 yyyy-mm-dd）。", kind="error")
                return
        else:
            y, mo, da = y_var.get(), m_var.get(), d_var.get()
        try:
            dt = datetime(y, mo, da, h_var.get(), min_var.get(), 0, tzinfo=local_tz)
        except ValueError as e:
            show_auto_close_popup(dlg, "日期错误", str(e), kind="error")
            return
        min_future = datetime.now(local_tz) + timedelta(minutes=2)
        if dt <= min_future:
            messagebox.showwarning("时间", "请选择至少约 2 分钟后的时间。", parent=dlg)
            return
        result["ok"] = True
        result["mode"] = "scheduled"
        result["dt"] = dt
        dlg.destroy()

    def on_cancel():
        result["ok"] = False
        dlg.destroy()

    ttk.Button(btn_row, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=4)
    ttk.Button(btn_row, text="取消", command=on_cancel).pack(side=tk.RIGHT)
    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.update_idletasks()
    px = (dlg.winfo_screenwidth() - 440) // 2
    py = (dlg.winfo_screenheight() - 560) // 2
    dlg.geometry(f"440x560+{px}+{py}")
    dlg.wait_window()
    if not result["ok"]:
        return None
    return (result["mode"], result["dt"])


def _reference_item_youtube_id(item):
    """从 NotebookLM 参考项 dict 中解析 YouTube id（优先 id 字段，其次 url）。"""
    if not isinstance(item, dict):
        return ""
    return _video_youtube_id(item)


def _norm_path_compare(a, b):
    """比较两条路径是否指向同一文件（规范化 +  basename 兜底）。"""
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    try:
        na, nb = os.path.normcase(os.path.normpath(os.path.abspath(a))), os.path.normcase(
            os.path.normpath(os.path.abspath(b))
        )
        if na == nb:
            return True
    except Exception:
        pass
    return os.path.basename(a).lower() == os.path.basename(b).lower()


def _find_channel_video_for_reference_item(item, channel_videos):
    """
    将参考列表中的单项与 channel_videos 中的 video 对应：
    优先 YouTube id，其次 transcribed_file 路径，再试 url。
    """
    if not isinstance(item, dict):
        return None
    yid = _reference_item_youtube_id(item)
    if yid:
        v = _find_video_by_youtube_id(channel_videos, yid)
        if v:
            return v
    tfp = (item.get("transcribed_file") or "").strip()
    if tfp:
        for v in channel_videos or []:
            vtf = (v.get("transcribed_file") or "").strip()
            if vtf and _norm_path_compare(tfp, vtf):
                return v
    url = (item.get("url") or "").strip()
    if url:
        for v in channel_videos or []:
            if (v.get("url") or "").strip() == url:
                return v
    return None


def _status_display_for_related_field(raw):
    """树与表单展示：忽略历史下载占用的 status。"""
    s = raw if isinstance(raw, str) else str(raw or "")
    if s in ("success", "failed"):
        return ""
    return s


_SIMILAR_SUMMARY_MATCH_SYSTEM = """你是心理咨询类视频摘要的相似度分析助手。
给定一条「参考摘要」和若干「候选视频」（每条含 YouTube id、标题、摘要片段），请判断哪些候选与参考在**心理问题主题、案例结构、临床叙事**上足够接近，可视为「类似案例」。
只输出严格 JSON 对象，不要其它文字。格式：
{"matches":[{"id":"<候选中的 youtube id>","confidence":0.0-1.0,"reason":"一句中文说明相似点"}]}
规则：matches 按 confidence 降序；最多 18 条；id 必须完全来自候选列表；若无合适候选则 {"matches":[]}。"""



class MediaDownloader:

    def __init__(self, pid, youtube_path, language):
        print("YoutubeDownloader init...")
        self.pid = pid
        self.youtube_dir = youtube_path
        self.channel_list_dir = _channel_list_dir_for_media_downloader(youtube_path)
        os.makedirs(self.channel_list_dir, exist_ok=True)
        self.ffmpeg_audio_processor = FfmpegAudioProcessor(pid)

        self.channel_list_json = ""
        self.channel_videos = []
        self.channel_name = ""
        self.latest_date = datetime.now()
        self.language = language
        
        # Cookies 文件路径（优先检查下载文件夹，然后检查项目路径）
        self.cookie_file = self._find_cookies_file()
        if self.cookie_file and os.path.exists(self.cookie_file):
            print(f"✅ 找到 cookies 文件: {self.cookie_file}")
        else:
            print(f"⚠️ 未找到 cookies 文件")
        
        # 检测 JavaScript 运行时
        self.js_runtime = self._detect_js_runtime()
        self.transcriber = AudioTranscriber(self.pid, model_size="small", device="cuda")
        self._cookies_session_disabled = False
        # 批量转录时由首个视频探测：None | {"mode":"caption","lang":...} | {"mode":"audio"}
        self._batch_transcribe_strategy = None
        # 按频道记住成功的 yt-dlp 音频下载策略（player_client / format / cookies）
        self._yt_download_pref = None


    def _find_cookies_file(self):
        cookies_filename = "www.youtube.com_cookies.txt"
        download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        download_cookies = os.path.join(download_folder, cookies_filename)
        
        if os.path.exists(download_cookies):
            print(f"✅ 在下载文件夹找到 cookies 文件: {download_cookies}")
            # 移动到项目路径
            project_cookies = os.path.join(f"{self.youtube_dir}/work", cookies_filename)
            if os.path.exists(project_cookies):
                os.remove(project_cookies)
                print(f"🗑️ 已删除旧的 cookies 文件: {project_cookies}")
            # 移动文件到项目路径
            shutil.move(download_cookies, project_cookies)
            return project_cookies
        
        return None


    def _check_and_update_cookies(self, wait_forever=True):
        """
        检查 cookies：优先使用项目路径已有文件；仅当没有有效 cookies 时检查 Downloads 并可能弹窗。
        同一次启动内已有有效 cookies 则直接复用，不重复弹窗；弹窗在同 session 内最多一次。
        """
        cookies_filename = "www.youtube.com_cookies.txt"
        project_cookies = os.path.join(f"{self.youtube_dir}/work", cookies_filename)
        download_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        download_cookies = os.path.join(download_folder, cookies_filename)

        # 1. 若项目路径已有有效 cookies，直接复用，不弹窗
        if self.cookie_file and os.path.exists(self.cookie_file) and os.path.getsize(self.cookie_file) > 0:
            return True
        if os.path.exists(project_cookies) and os.path.getsize(project_cookies) > 0:
            self.cookie_file = project_cookies
            return True

        # 2. 尝试从 Downloads 获取（可能有新导出的）
        self.cookie_file = self._find_cookies_file()
        if self.cookie_file:
            return True

        # 3. 无有效 cookies：wait_forever=False 时直接返回
        if not wait_forever:
            return False

        # 4. 持续等待：同 session 内弹窗最多一次，避免频繁打扰
        last_prompt_key = '_cookie_prompt_shown_at'
        while True:
            if os.path.exists(download_cookies):
                print(f"🔄 在下载文件夹发现新的 cookies 文件: {download_cookies}")
                
                # 移动到项目路径
                project_cookies = os.path.join(f"{self.youtube_dir}/work", cookies_filename)
                try:
                    # 如果项目路径已有文件，直接删除
                    if os.path.exists(project_cookies):
                        os.remove(project_cookies)
                        print(f"🗑️ 已删除旧的 cookies 文件: {project_cookies}")
                    
                    # 移动新文件
                    shutil.move(download_cookies, project_cookies)

                    self.cookie_file = project_cookies
                    # 重置 cookies 日志标志，以便下次使用新 cookies 时打印信息
                    if hasattr(self, '_cookies_logged'):
                        delattr(self, '_cookies_logged')
                    print(f"✅ 已更新 cookies 文件: {project_cookies}")
                    print(f"🗑️ 已从下载文件夹删除原文件")
                    print(f"🔄 下次请求将使用新的 cookies 文件")
                    return True
                except Exception as e:
                    print(f"⚠️ 更新 cookies 文件时出错: {e}")
                    return False
            
            # 等待并检查
            print(f"⏳  请将新的 cookies 文件保存到: {download_cookies}")
            # 同一次启动内弹窗最多一次，避免频繁打扰
            if not getattr(self, '_cookie_prompt_shown', False):
                self._cookie_prompt_shown = True
                messagebox.showinfo("提示", "请将新的 cookies 文件保存到下载文件夹")
            time.sleep(2)  # 每2秒检查一次，避免 busy loop


    def _detect_js_runtime(self):
        """
        检测系统中可用的 JavaScript 运行时
        
        Returns:
            tuple: (runtime_name, runtime_path) 或 (None, None)
        """
        for node_path in _iter_node_executable_candidates():
            if not _verify_node_executable(node_path):
                continue
            try:
                result = subprocess.run(
                    [node_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    version = (result.stdout or "").strip().split("\n")[0]
                    print(
                        f"✅ 检测到 JavaScript 运行时: Node.js {version} ({node_path})"
                    )
                    return ("node", node_path)
            except Exception:
                continue

        deno_path = shutil.which("deno")
        if deno_path:
            try:
                result = subprocess.run(
                    ["deno", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split("\n")[0]
                    print(f"✅ 检测到 JavaScript 运行时: Deno {version}")
                    return ("deno", deno_path)
            except Exception:
                pass

        print("⚠️ 未检测到 JavaScript 运行时（Node.js 或 Deno）")
        print("   这可能导致某些 YouTube 视频无法下载或格式缺失")
        print("   建议安装 Node.js: https://nodejs.org/")
        return (None, None)


    def _get_ydl_opts_base(self, **kwargs):
        """
        获取基础的 yt-dlp 选项，包含 cookies 支持
        
        Args:
            **kwargs: 额外的选项参数（quiet, skip_download 等）；``use_cookies=False`` 可禁用 cookies。
            
        Returns:
            dict: yt-dlp 选项字典
        """
        use_cookies = kwargs.pop("use_cookies", True)
        if getattr(self, "_cookies_session_disabled", False):
            use_cookies = False
        opts = {}

        if (
            use_cookies
            and self.cookie_file
            and os.path.exists(self.cookie_file)
            and os.path.getsize(self.cookie_file) > 0
        ):
            opts["cookiefile"] = self.cookie_file
            if not hasattr(self, "_cookies_logged"):
                print(f"🍪 使用 cookies 文件: {self.cookie_file}")
                self._cookies_logged = True

        if "sleep_interval" not in kwargs:
            opts["sleep_interval"] = 2
        if "sleep_interval_requests" not in kwargs:
            opts["sleep_interval_requests"] = 5

        if self.js_runtime[0] and "js_runtimes" not in kwargs:
            runtime_name, runtime_path = self.js_runtime
            runtime_config = {}
            if runtime_path:
                runtime_config["path"] = runtime_path
            opts["js_runtimes"] = {runtime_name: runtime_config}

        if "remote_components" not in kwargs:
            opts["remote_components"] = ["ejs:github"]

        if "noplaylist" not in kwargs:
            opts["noplaylist"] = True

        opts.update(kwargs)

        ea = dict(opts.get("extractor_args") or {})
        yt = dict(ea.get("youtube") or {})
        if "player_client" not in yt:
            if self.js_runtime[0]:
                yt["player_client"] = ["mweb", "web", "android", "tv_embedded"]
            else:
                yt["player_client"] = ["android", "mweb", "web"]
        ea["youtube"] = yt
        opts["extractor_args"] = ea

        return opts


    def _extract_youtube_info(self, video_url, *, use_cookies=True, **extra_opts):
        """``extract_info``；URL 规范为单视频 watch 链接。"""
        url = _normalize_youtube_watch_url(video_url)
        opts = self._get_ydl_opts_base(
            use_cookies=use_cookies,
            quiet=True,
            skip_download=True,
            **extra_opts,
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False), url


    def _disable_cookies_for_session(self, reason: str = "") -> None:
        if getattr(self, "_cookies_session_disabled", False):
            return
        self._cookies_session_disabled = True
        why = (reason or "").strip()
        print("🍪 本次会话将跳过 cookies（可能已过期）" + (f"：{why}" if why else ""))
        print("   请重新导出 www.youtube.com_cookies.txt 到「下载」文件夹后重启程序。")


    def _yt_download_pref_key(self) -> str:
        """用于记住下载策略的频道键（YouTube 列表名或 list JSON 基名）。"""
        name = (self.channel_name or "").strip()
        if name:
            return name
        path = (self.channel_list_json or "").strip()
        if path:
            base = os.path.basename(path)
            if base.lower().endswith(".json"):
                base = base[:-5]
            if base:
                return base
        return ""


    def _yt_download_prefs_file(self) -> str:
        return os.path.join(self.channel_list_dir, _YT_DOWNLOAD_PREFS_JSON)


    def _default_youtube_player_clients(self) -> list[str]:
        if self.js_runtime[0]:
            return ["mweb", "web", "android", "tv_embedded"]
        return ["android", "mweb", "web"]


    def _load_yt_download_pref(self) -> dict | None:
        key = self._yt_download_pref_key()
        if not key:
            return None
        cached = getattr(self, "_yt_download_pref", None)
        if isinstance(cached, dict) and cached.get("_key") == key:
            return cached.get("data")
        pref = None
        path = self._yt_download_prefs_file()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    ent = data.get(key)
                    if isinstance(ent, dict) and ent.get("format"):
                        pref = ent
            except Exception:
                pass
        self._yt_download_pref = {"_key": key, "data": pref}
        return pref


    def _save_yt_download_pref(self, pref: dict) -> None:
        key = self._yt_download_pref_key()
        if not key or not isinstance(pref, dict) or not pref.get("format"):
            return
        path = self._yt_download_prefs_file()
        data: dict = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                pass
        data[key] = {
            "use_cookies": bool(pref.get("use_cookies", True)),
            "format": str(pref["format"]),
            "player_client": str(pref.get("player_client") or ""),
        }
        write_json(path, data)
        self._yt_download_pref = {"_key": key, "data": data[key]}
        print(
            f"📌 已记住频道下载策略: cookies={data[key]['use_cookies']}, "
            f"client={data[key]['player_client']}, format={data[key]['format']}"
        )


    def _yt_merge_player_client_args(self, extra_opts: dict, player_client: str | None) -> dict:
        if not player_client:
            return extra_opts
        kw = dict(extra_opts)
        ea = dict(kw.get("extractor_args") or {})
        yt = dict(ea.get("youtube") or {})
        yt["player_client"] = [player_client]
        ea["youtube"] = yt
        kw["extractor_args"] = ea
        return kw


    def _yt_is_format_or_cookie_error(self, err: Exception | str) -> bool:
        msg = str(err or "").lower()
        return (
            "format" in msg
            or "no video formats" in msg
            or "cookies are no longer valid" in msg
            or "only images are available" in msg
        )


    def _yt_extract_download(
        self,
        video_url: str,
        *,
        use_cookies: bool = True,
        download: bool = True,
        format_string: str | None = None,
        **extra_opts,
    ):
        url = _normalize_youtube_watch_url(video_url)
        opts = self._get_ydl_opts_base(
            use_cookies=use_cookies,
            quiet=extra_opts.pop("quiet", True),
            **extra_opts,
        )
        if format_string:
            opts["format"] = format_string
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=download), url


    def _yt_download_with_fallbacks(
        self,
        video_url: str,
        *,
        format_candidates: tuple[str, ...] = YOUTUBE_AUDIO_FORMAT_FALLBACKS,
        **extra_opts,
    ):
        """先复用频道已记住的策略；失效则逐个 client/format 探测并写入记忆。"""
        last_err = ""

        saved = self._load_yt_download_pref()
        if saved:
            fmt = saved.get("format")
            client = (saved.get("player_client") or "").strip() or None
            use_ck = bool(saved.get("use_cookies", True))
            if fmt:
                try:
                    kw = self._yt_merge_player_client_args(extra_opts, client)
                    print(
                        f"📌 复用频道下载策略: cookies={use_ck}, "
                        f"client={client or 'default'}, format={fmt}"
                    )
                    return self._yt_extract_download(
                        video_url,
                        use_cookies=use_ck,
                        download=True,
                        format_string=fmt,
                        **kw,
                    )
                except yt_dlp.utils.DownloadError as e:
                    last_err = str(e)
                    if "cookies are no longer valid" in last_err.lower() and use_ck:
                        self._disable_cookies_for_session("YouTube 报告 cookies 无效")
                    if not self._yt_is_format_or_cookie_error(e):
                        raise
                    print("⚠️ 已保存的下载策略失效，重新探测…")
                except Exception:
                    raise

        cookie_phases = (True, False) if self.cookie_file else (False,)
        for use_ck in cookie_phases:
            if use_ck and getattr(self, "_cookies_session_disabled", False):
                continue
            for client in self._default_youtube_player_clients():
                for fmt in format_candidates:
                    try:
                        kw = self._yt_merge_player_client_args(extra_opts, client)
                        result = self._yt_extract_download(
                            video_url,
                            use_cookies=use_ck,
                            download=True,
                            format_string=fmt,
                            **kw,
                        )
                        self._save_yt_download_pref(
                            {
                                "use_cookies": use_ck,
                                "format": fmt,
                                "player_client": client,
                            }
                        )
                        return result
                    except yt_dlp.utils.DownloadError as e:
                        last_err = str(e)
                        if "cookies are no longer valid" in last_err.lower() and use_ck:
                            self._disable_cookies_for_session("YouTube 报告 cookies 无效")
                            break
                        if not self._yt_is_format_or_cookie_error(e):
                            raise
                        print(
                            f"⚠️ 下载失败 (cookies={use_ck}, client={client}, "
                            f"format={fmt})，尝试下一方案…"
                        )
                        continue
                    except Exception:
                        raise
        cookies_bad = "cookies are no longer valid" in last_err.lower()
        raise Exception(
            _youtube_format_error_message(last_err, cookies_invalid=cookies_bad)
        )


    def find_video_basic(self, video_detail):
        if not self.cookie_file:
            return None

        check_opts = self._get_ydl_opts_base(quiet=True, skip_download=True)
        with yt_dlp.YoutubeDL(check_opts) as ydl:
            info = ydl.extract_info(video_detail.get('url', ''), download=False)
            return info


    def _find_caption_srt(self, download_prefix, target_lang):
        """查找 yt-dlp 下载的字幕文件（语言码可能与请求不完全一致）。"""
        expected = f"{download_prefix}.{target_lang}.srt"
        if os.path.exists(expected):
            return expected
        media_dir = os.path.dirname(download_prefix)
        base = os.path.basename(download_prefix)
        if not os.path.isdir(media_dir):
            return None
        for filename in os.listdir(media_dir):
            if filename.startswith(base) and filename.endswith(".srt"):
                return os.path.join(media_dir, filename)
        return None

    def _transcribe_audio_to_json(self, video_detail, target_lang, audio_path):
        """用 Whisper 转录音频并写入 JSON，成功返回路径。"""
        if not audio_path or not os.path.exists(audio_path):
            return None
        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        src_path = f"{download_prefix}.{target_lang}.json"
        if os.path.exists(src_path):
            return src_path
        cfg = project_manager.PROJECT_CONFIG or {}
        scene_min_length = cfg.get("scene_min_length", 9)
        script_json = self.transcriber.transcribe_with_whisper(
            audio_path,
            target_lang,
            False,
            False,
            False,
            scene_min_length,
            int(scene_min_length * 1.5),
        )
        if script_json:
            write_json(src_path, script_json)
            return src_path
        return None

    def _ensure_audio_path(self, video_detail):
        """返回已有或可解析的音频路径；不存在则返回空字符串。"""
        audio_path = (video_detail.get("audio_path") or "").strip()
        if audio_path and os.path.exists(audio_path):
            return audio_path
        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        for ext in ("mp3", "m4a", "webm", "opus", "wav"):
            candidate = f"{download_prefix}.{ext}"
            if os.path.exists(candidate):
                video_detail["audio_path"] = candidate
                return candidate
        video_path = f"{download_prefix}.mp4"
        if os.path.exists(video_path):
            audio_path = self.ffmpeg_audio_processor.extract_audio_from_video(video_path, "mp3")
            mp3_path = f"{download_prefix}.mp3"
            safe_copy_overwrite(audio_path, mp3_path)
            video_detail["audio_path"] = mp3_path
            return mp3_path
        return ""

    def download_captions(self, video_detail, target_lang, *, allow_audio_fallback=None):
        if not target_lang:
            return None

        video_url = video_detail.get('url', '')
        if not video_url:
            return None

        if allow_audio_fallback is None:
            allow_audio_fallback = config.TRANSCRIBE_FALLBACK_TO_AUDIO

        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        
        video_url = _normalize_youtube_watch_url(video_url)
        caption_opts = dict(
            skip_download=True,
            writesubtitles=True,
            writeautomaticsub=True,
            subtitleslangs=[target_lang],
            subtitlesformat="srt",
            outtmpl=download_prefix,
            quiet=True,
            no_warnings=True,
            format="bestaudio/best",
        )
        for use_ck in (True, False):
            if use_ck and (
                not self.cookie_file
                or getattr(self, "_cookies_session_disabled", False)
            ):
                continue
            try:
                info, _ = self._yt_extract_download(
                    video_url,
                    use_cookies=use_ck,
                    download=True,
                    **caption_opts,
                )
                if info and "upload_date" in info:
                    upload_date = info.get("upload_date", "")
                    if upload_date:
                        upload_date = str(upload_date).strip()
                        if upload_date:
                            if len(upload_date) == 10:
                                upload_date = upload_date.replace("-", "")
                            if _should_update_upload_date(video_detail):
                                video_detail["upload_date"] = upload_date[:8]
                                print(f"✅ 已更新 upload_date: {upload_date[:8]}")
                src_path = self._find_caption_srt(download_prefix, target_lang)
                if src_path:
                    print(f"✅ 已下载字幕：语言 {target_lang}")
                    return src_path
            except yt_dlp.utils.DownloadError as e:
                err = str(e)
                if "cookies are no longer valid" in err.lower() and use_ck:
                    self._disable_cookies_for_session("YouTube 报告 cookies 无效")
                    continue
                if self._yt_is_format_or_cookie_error(e) and use_ck:
                    print("⚠️ 带 cookies 下载字幕失败，尝试无 cookies…")
                    continue
            except Exception:
                break

        if not allow_audio_fallback:
            return None

        print(f"❌ 下载字幕失败，尝试音频转录...")
        src_path = f"{download_prefix}.{target_lang}.json"
        if os.path.exists(src_path):
            return src_path

        audio_path = self._ensure_audio_path(video_detail)
        if not audio_path:
            print(f"❌ 音频文件不存在")
            return None

        return self._transcribe_audio_to_json(video_detail, target_lang, audio_path)

    def reset_batch_transcribe_strategy(self):
        """重置批量转录策略（新批次开始时调用，首个视频会重新探测）。"""
        self._batch_transcribe_strategy = None

    def _get_caption_lang_priority(self):
        """按当前频道语言只尝试一种字幕（en 频道试 en，其余一律试 zh）。"""
        if (self.language or "zh").lower().startswith("en"):
            return ["en"]
        return ["zh"]

    def _transcribe_via_audio(self, video_detail, target_lang, *, direct_audio=False):
        """下载音频（若本地无）并用 Whisper 转录。"""
        audio_path = self._ensure_audio_path(video_detail)
        if not audio_path:
            if direct_audio:
                print("📥 正在下载音频…")
            else:
                print("📥 字幕不可用，正在下载音频…")
            audio_path = self.download_audio_only(video_detail)
        if not audio_path:
            print("❌ 音频下载失败，无法转录")
            return None
        return self._transcribe_audio_to_json(video_detail, target_lang, audio_path)

    def transcribe_video_detail(self, video_detail, target_lang=None, *, batch_mode=False):
        """优先下载字幕；失败时按 config 决定是否下载音频并 Whisper 转录。

        batch_mode=True 时，首个视频探测字幕语言/音频 fallback，后续视频复用同一策略。
        """
        target_lang = target_lang or self.language or "zh"
        strategy = self._batch_transcribe_strategy if batch_mode else None

        if strategy and strategy.get("mode") == "caption":
            return self.download_captions(
                video_detail, strategy["lang"], allow_audio_fallback=False
            )

        if strategy and strategy.get("mode") == "audio":
            if not config.TRANSCRIBE_FALLBACK_TO_AUDIO:
                return None
            return self._transcribe_via_audio(video_detail, target_lang, direct_audio=True)

        # 首个视频或非批量：按语言优先级探测字幕
        for lang in self._get_caption_lang_priority():
            transcribed_file = self.download_captions(
                video_detail, lang, allow_audio_fallback=False
            )
            if transcribed_file:
                if batch_mode:
                    self._batch_transcribe_strategy = {"mode": "caption", "lang": lang}
                    print(f"📌 批量策略：后续使用字幕 ({lang})")
                return transcribed_file

        if batch_mode:
            self._batch_transcribe_strategy = {"mode": "audio"}
            print("📌 批量策略：字幕不可用，后续直接下载音频转录")

        if not config.TRANSCRIBE_FALLBACK_TO_AUDIO:
            return None
        return self._transcribe_via_audio(video_detail, target_lang)

    def transcribe_audio_detail(self, video_detail, target_lang=None):
        """仅用本地/已下载音频 Whisper 转录，不尝试下载字幕。"""
        target_lang = target_lang or self.language or "zh"
        audio_path = self._ensure_audio_path(video_detail)
        if not audio_path:
            print("❌ 音频文件不存在，无法转录")
            return None
        return self._transcribe_audio_to_json(video_detail, target_lang, audio_path)


    def try_download_caption_with_priority(self, video_detail):
        """按用户选择的语言优先尝试下载字幕，成功返回路径，失败返回 None"""
        if not self.cookie_file:
            return None
        for lang in self._get_caption_lang_priority():
            path = self.download_captions(video_detail, lang, allow_audio_fallback=False)
            if path:
                return path
        return None

    def pick_best_caption_language(self, all_languages):
        """从可用语言中优先选中文，其次英文，否则返回 None"""
        if not all_languages:
            return None
        zh_pattern = re.compile(r'^zh', re.I)  # zh, zh-CN, zh-TW, zh-Hans...
        en_pattern = re.compile(r'^en', re.I)  # en, en-US, en-GB...
        zh_langs = [l for l in all_languages if zh_pattern.match(l)]
        en_langs = [l for l in all_languages if en_pattern.match(l)]
        if zh_langs:
            return zh_langs[0]
        if en_langs:
            return en_langs[0]
        return None

    def download_audio_only(self, video_detail, sleep_interval=2):
        video_url = _normalize_youtube_watch_url(video_detail.get("url", ""))
        if video_url:
            video_detail["url"] = video_url
        if not video_url:
            return None

        video_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)

        video_path = video_prefix + ".mp4"
        if os.path.exists(video_path):
            audio_path = self.ffmpeg_audio_processor.extract_audio_from_video(video_path, "mp3")
            safe_copy_overwrite(audio_path, video_prefix + ".mp3")
            video_detail['audio_path'] = audio_path
            return audio_path

        audio_extensions = ['mp3', 'm4a', 'webm', 'opus', 'wav']
        for ext in audio_extensions:
            audio_path = video_prefix + "." + ext
            if os.path.exists(audio_path):
                if not audio_path.endswith('.mp3'):
                    a = self.ffmpeg_audio_processor.to_mp3(audio_path)
                    safe_remove(audio_path)
                    audio_path = video_prefix + ".mp3"
                    safe_copy_overwrite(a, audio_path)
                video_detail['audio_path'] = audio_path
                return audio_path

        outtmpl = video_prefix + ".%(ext)s"
        ydl_extra = {
            "outtmpl": outtmpl,
            "quiet": False,
            "progress_hooks": [self._progress_hook],
            "skip_download": False,
            "ignoreerrors": False,
        }
        if sleep_interval is not None:
            ydl_extra["sleep_interval"] = sleep_interval

        try:
            info, _ = self._yt_download_with_fallbacks(
                video_url,
                **ydl_extra,
            )

            if info and "upload_date" in info:
                upload_date = info.get("upload_date", "")
                if upload_date:
                    if len(upload_date) == 10:
                        upload_date = upload_date.replace("-", "")
                    if _should_update_upload_date(video_detail):
                        video_detail["upload_date"] = upload_date
                        print(f"✅ 已更新 upload_date: {upload_date}")

            for ext in audio_extensions:
                expected_path = os.path.abspath(f"{video_prefix}.{ext}")
                if os.path.exists(expected_path):
                    print(f"✅ 找到下载的音频文件: {expected_path}")
                    if not expected_path.endswith(".mp3"):
                        a = self.ffmpeg_audio_processor.to_mp3(expected_path)
                        expected_path = video_prefix + ".mp3"
                        safe_copy_overwrite(a, expected_path)
                    video_detail["audio_path"] = expected_path
                    return expected_path

            if info and info.get("requested_downloads"):
                actual_path = info["requested_downloads"][0].get("filepath")
                if actual_path and os.path.exists(actual_path):
                    expected_path = os.path.abspath(actual_path)
                    if not expected_path.endswith(".mp3"):
                        a = self.ffmpeg_audio_processor.to_mp3(expected_path)
                        safe_remove(expected_path)
                        expected_path = video_prefix + ".mp3"
                        safe_copy_overwrite(a, expected_path)
                    video_detail["audio_path"] = expected_path
                    return expected_path

            return None
        except Exception as e:
            print(f"❌ 下载音频失败: {str(e)}")
            return None


    def download_video_highest_resolution(self, video_detail, sleep_interval=2):
        video_url = video_detail.get('url', '')
        if not video_url:
            return None
        video_prefix = self.youtube_dir + "/media/__" + self.generate_video_prefix(video_detail)

        target_video_path = video_prefix + ".mp4"
        target_audio_path = video_prefix + ".mp3"
        if os.path.exists(target_video_path):
            if video_detail.get('video_path', '') == target_video_path:
                return video_detail['video_path']
            video_detail['video_path'] = video_prefix + ".mp4"
            audio_path = video_detail.get('audio_path', '')
            if not audio_path or audio_path != target_audio_path:
                a = self.ffmpeg_audio_processor.extract_audio_from_video(target_video_path, "mp3")
                safe_copy_overwrite(a, target_audio_path)
                video_detail['audio_path'] = target_audio_path
            return video_detail['video_path']

        outtmpl = video_prefix + ".%(ext)s"
        # 优先级: MP4 高质量 -> 任何高质量 -> 最佳可用
        format_string = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best[ext=mp4]/"
            "best"
        )
        
        # 使用基础选项，包含 cookies 支持
        ydl_opts_kwargs = {
            'format': format_string,
            'outtmpl': outtmpl,
            'merge_output_format': 'mp4',
            'quiet': False,
            'progress_hooks': [self._progress_hook],
            'skip_download': False,  # 需要下载
            'ignoreerrors': False,  # 不忽略错误,让调用者处理
        }
        if sleep_interval is not None:
            ydl_opts_kwargs['sleep_interval'] = sleep_interval
        
        ydl_opts = self._get_ydl_opts_base(**ydl_opts_kwargs)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                # 验证文件是否存在
                if not os.path.exists(target_video_path):
                    # 尝试查找其他扩展名
                    base_path = target_video_path.rsplit('.', 1)[0]
                    for ext in ['webm', 'mkv', 'mp4']:
                        alt_path = f"{base_path}.{ext}"
                        if os.path.exists(alt_path):
                            print(f"✅ 找到下载文件: {alt_path}")
                            target_video_path = alt_path
                            break
                
                safe_copy_overwrite(self.ffmpeg_audio_processor.extract_audio_from_video(target_video_path, "mp3"), target_audio_path)
                video_detail['audio_path'] = target_audio_path
                video_detail['video_path'] = target_video_path

                return target_video_path

        except Exception as e:
            return None


    def get_playlist_info(self, playlist_url):
        """获取播放列表信息，不下载视频"""
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,  # 只提取基本信息，不下载
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(playlist_url, download=False)
                
                playlist_info = {
                    'title': info.get('title', 'Unknown Playlist'),
                    'description': info.get('description', ''),
                    'video_count': info.get('playlist_count', 0),
                    'videos': []
                }
                
                if 'entries' in info:
                    for entry in info['entries']:
                        if entry:
                            video_info = {
                                'title': entry.get('title', 'Unknown Title'),
                                'url': entry.get('url', ''),
                                'duration': entry.get('duration', 0),
                                'view_count': entry.get('view_count', 0),
                                'uploader': entry.get('uploader', ''),
                                'upload_date': entry.get('upload_date', '')
                            }
                            playlist_info['videos'].append(video_info)
                
                return playlist_info
                
            except Exception as e:
                print(f"❌ 获取播放列表信息失败: {str(e)}")
                return None


    def get_video_detail(self, video_url, channel_name='Unknown'):
        video_url = _normalize_youtube_watch_url(video_url)
        video_detail = None
        resolved_url = video_url
        last_error = ""

        try:
            video_detail, resolved_url = self._extract_youtube_info(
                video_url, use_cookies=True
            )
        except yt_dlp.utils.DownloadError as e:
            last_error = str(e)
            if "cookies are no longer valid" in last_error.lower():
                self._disable_cookies_for_session("YouTube 报告 cookies 无效")
            fmt_fail = (
                "format" in last_error.lower()
                or "No video formats" in last_error
                or "only images are available" in last_error.lower()
            )
            if (fmt_fail or getattr(self, "_cookies_session_disabled", False)) and self.cookie_file:
                try:
                    print("⚠️ 带 cookies 拉取失败，尝试无 cookies / android 客户端…")
                    video_detail, resolved_url = self._extract_youtube_info(
                        video_url, use_cookies=False
                    )
                    last_error = ""
                except Exception as retry_e:
                    last_error = str(retry_e)

            if video_detail is None:
                if "403" in last_error or "Forbidden" in last_error:
                    raise Exception(
                        f"HTTP 403 Forbidden - YouTube 访问被拒绝，可能需要更新 cookies 或等待: {video_url}"
                    )
                if "challenge" in last_error.lower():
                    raise Exception(f"YouTube 挑战验证失败: {video_url}")
                if fmt_fail or "format" in last_error.lower():
                    cookies_bad = "cookies are no longer valid" in last_error.lower()
                    raise Exception(
                        _youtube_format_error_message(
                            last_error, cookies_invalid=cookies_bad
                        )
                    )
                raise Exception(f"下载错误: {last_error}")

        if not video_detail:
            raise Exception(f"无法获取视频信息: {video_url}")

        uploader = video_detail.get("uploader") or video_detail.get("channel") or channel_name
        chan = video_detail.get("channel") or video_detail.get("uploader") or channel_name
        return {
            "title": video_detail.get("title", "Unknown Title"),
            "url": resolved_url or video_url,
            "id": video_detail.get("id", ""),
            "duration": video_detail.get("duration", 0),
            "view_count": video_detail.get("view_count", 0),
            "uploader": uploader,
            "channel": chan,
            "channel_id": video_detail.get("channel_id", ""),
            "upload_date": video_detail.get("upload_date", ""),
            "thumbnail": video_detail.get("thumbnail", ""),
            "description": video_detail.get("description", "")[:200]
            if video_detail.get("description")
            else "",
        }


    def generate_video_prefix(self, video_detail, title_length=15):
        # 格式: {view_count:010d}_{upload_date}_{title}.{ext}
        view_count = video_detail.get('view_count', 0)
        upload_date = video_detail.get('upload_date', "20260101")
        title = _youtube_row_display_title(video_detail)

        view_count_str = f"{view_count:010d}" if view_count else "0000000000"
        # 处理上传日期
        if upload_date and len(upload_date) >= 8:
            date_str = upload_date[:8]  # YYYYMMDD
        else:
            date_str = "00000000"
        # 清理标题中的非法字符，并限制长度
        safe_title = make_safe_file_name(title, title_length)
        # 构建文件名前缀（用于匹配）
        return f"{view_count_str}_{date_str}_{safe_title}"


    def get_channel_name(self, video_detail):
        """从视频/频道详情提取频道名。空或 Unknown 时尝试下一项；避免返回 untitled。"""
        if not video_detail:
            return 'YouTubeChannel'
        for key in ('channel', 'uploader', 'creator'):
            v = (video_detail.get(key) or '').strip()
            if v and v.lower() not in ('unknown', ''):
                r = make_safe_file_name(v)
                if r != "untitled":
                    print(f"📺 频道名称: {r}")
                    return r
        cid = (video_detail.get('channel_id') or '').strip()
        if cid and len(cid) >= 10:
            r = make_safe_file_name(cid)
            if r != "untitled":
                return r
        print(f"📺 频道名称: YouTubeChannel (fallback)")
        return "YouTubeChannel"

    def _parse_relative_time_to_yyyymmdd(self, s):
        """解析相对时间字符串为 YYYYMMDD。如 "1 day ago"=昨天, "2 weeks ago", "3 months ago"。
        1天=24h, 1周=24*7, 1月≈30*24h。供 flat 抓取无 upload_date 时估算，download 时再更新精确值。"""
        if not s or not isinstance(s, str):
            return ''
        s = s.strip().lower()
        if not s:
            return ''
        # Unix 时间戳（秒）
        if s.isdigit():
            try:
                t = datetime.fromtimestamp(int(s))
                return t.strftime('%Y%m%d')
            except (ValueError, OSError):
                return ''
        # 匹配 "X (second|minute|hour|day|week|month|year)(s)? ago" 或 "X 秒/分/时/天/周/月/年 前"
        now = datetime.now()
        m = re.search(r'(\d+)\s*(second|minute|hour|day|week|month|year|秒|分|时|天|周|月|年)s?\s*(ago|前)?', s, re.I)
        if not m:
            return ''
        n = int(m.group(1))
        unit = (m.group(2) or '').lower()
        mul = {'second': 1/3600, 'minute': 1/60, 'hour': 1, 'day': 24, 'week': 24*7, 'month': 30*24, 'year': 365*24,
               '秒': 1/3600, '分': 1/60, '时': 1, '天': 24, '周': 24*7, '月': 30*24, '年': 365*24}
        if unit not in mul:
            return ''
        hours = n * mul[unit]
        try:
            from datetime import timedelta
            t = now - timedelta(hours=hours)
            return t.strftime('%Y%m%d')
        except Exception:
            return ''

    def _entry_upload_date(self, entry):
        """从 entry 提取 upload_date：优先 upload_date/release_timestamp，否则尝试解析相对时间字符串。"""
        ud = (entry.get('upload_date') or entry.get('release_date') or '').strip()
        if ud:
            if len(ud) == 10 and '-' in ud:
                return ud.replace('-', '')[:8]
            if len(ud) >= 8 and ud.isdigit():
                return ud[:8]
        ts = entry.get('release_timestamp') or entry.get('timestamp')
        if ts is not None:
            try:
                t = datetime.fromtimestamp(int(ts))
                return t.strftime('%Y%m%d')
            except (ValueError, OSError, TypeError):
                pass
        for v in (entry.get(k) for k in ('description', 'title') if entry.get(k)):
            if isinstance(v, str) and ('ago' in v.lower() or '前' in v):
                r = self._parse_relative_time_to_yyyymmdd(v)
                if r:
                    return r
        return ''

    def fetch_channel_info_from_url(self, url):
        """从频道链接或视频链接解析出频道名和频道页 URL。供 YT文字/YT管理 创建新频道时共用。
        返回 (channel_name, channel_url) 或 (None, None) 表示失败。"""
        url = (url or '').strip()
        if not url:
            return None, None
        try:
            self._check_and_update_cookies()
            if '/watch?v=' in url or 'youtu.be/' in url:
                # 视频链接：从视频获取频道信息
                video_data = self.get_video_detail(url, '')
                if not video_data:
                    return None, None
                channel_name = self.get_channel_name(video_data)
                channel_id = (video_data.get('channel_id') or '').strip()
                channel_url = f"https://www.youtube.com/channel/{channel_id}/videos" if channel_id and len(channel_id) >= 10 else None
                return channel_name, channel_url
            # 频道链接：/channel/xxx 或 /@xxx 或 /c/xxx
            ydl_opts = self._get_ydl_opts_base(quiet=True, extract_flat='in_playlist', skip_download=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return None, None
            channel_name = self.get_channel_name(info)
            channel_url = url.rstrip('/')
            if '/videos' not in channel_url:
                channel_url += '/videos'
            return channel_name, channel_url
        except Exception as e:
            print(f"❌ 解析链接失败: {e}")
            return None, None

    def is_video_new(self, video_data):
        """判断是否为列表中尚未存在的视频。只要标题一致即视为已有，不重复展示。"""
        if not self.channel_videos:
            return True
        new_title = _youtube_row_display_title(video_data).lower()
        if not new_title:
            return True
        for existing_video in self.channel_videos:
            existing_title = _youtube_row_display_title(existing_video).lower()
            if existing_title == new_title:
                return False
        return True


    def _parse_relative_time_to_yyyymmdd(self, s):
        """从相对时间字符串解析出近似 YYYYMMDD。如 "1 day ago"->昨天, "2 weeks ago"->14天前, "3 months ago"->90天前。
        下载时再用精确日期更新。"""
        if not s or not isinstance(s, str):
            return ''
        s = s.strip().lower()
        if not s:
            return ''
        # 匹配 X second(s)/minute(s)/hour(s)/day(s)/week(s)/month(s)/year(s) ago，及中文
        multipliers = {
            'second': 1/3600, 'sec': 1/3600, '秒': 1/3600,
            'minute': 1/60, 'min': 1/60, '分钟': 1/60, '分': 1/60,
            'hour': 1, 'hr': 1, '小时': 1, '时': 1,
            'day': 24, '天': 24,
            'week': 24*7, '周': 24*7,
            'month': 30*24, '月': 30*24,
            'year': 365*24, '年': 365*24,
        }
        for unit, hours_per in multipliers.items():
            if unit not in s:
                continue
            m = re.search(r'(\d+)\s*' + re.escape(unit) + r's?\s*(ago|前)?', s, re.I)
            if m:
                n = int(m.group(1))
                hours = n * hours_per
                t = datetime.now() - timedelta(hours=hours)
                return t.strftime('%Y%m%d')
        return ''

    def _entry_upload_date_fallback(self, entry):
        """从 entry 提取 upload_date：优先 upload_date，其次 release_timestamp/timestamp，再试相对时间字符串。"""
        ud = (entry.get('upload_date') or '').strip()
        if ud:
            if len(ud) == 10 and '-' in ud:
                return ud.replace('-', '')
            if len(ud) >= 8:
                return ud[:8]
        ts = entry.get('release_timestamp') or entry.get('timestamp')
        if ts is not None:
            try:
                t = datetime.fromtimestamp(int(ts))
                return t.strftime('%Y%m%d')
            except (ValueError, OSError):
                pass
        for v in entry.values():
            if isinstance(v, str) and ('ago' in v.lower() or '前' in v):
                r = self._parse_relative_time_to_yyyymmdd(v)
                if r:
                    return r
        return ''

    def list_hot_videos(self, channel_url, max_videos=5000, min_view_count=500):
        self._check_and_update_cookies()

        try:
            # 使用基础选项，包含 cookies 支持
            # approximate_date：从频道页相对时间（如 "2 weeks ago"）估算 upload_date，一次请求即可拿到
            # 否则 flat 抓取无 upload_date，需逐个视频请求才能拿到精确日期
            ydl_opts = self._get_ydl_opts_base(
                quiet=False,
                extract_flat='in_playlist',
                skip_download=True,
                extractor_args={'youtubetab': ['approximate_date']},
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)

            channel_name = self.get_channel_name(info)

            with open(f'{self.youtube_dir}/work/info_{channel_name}.json', 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
        
            if not info or 'entries' not in info:
                return None

            self.channel_list_json = os.path.join(self.channel_list_dir, f"{channel_name}.json")
            if os.path.exists(self.channel_list_json):
                with open(self.channel_list_json, 'r', encoding='utf-8') as f:
                    self.channel_videos = json.load(f)
                    _normalize_channel_videos_for_storage(self.channel_videos)
                    self.latest_date = max(
                                            (
                                                datetime.strptime(v["upload_date"], "%Y%m%d")
                                                for v in self.channel_videos
                                                if v.get("upload_date")
                                            ),
                                            default=None
                                        )                    
            else:
                self.channel_videos = []

            for count, entry in enumerate(info['entries']):
                if count >= max_videos:
                    break

                if entry:
                    video_url = entry.get('url', '') or entry.get('webpage_url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                    video_id = entry.get('id', '')
                    
                    # 首先尝试使用 entry 中的基本信息
                    video_data = None
                    if entry.get('view_count') is not None and entry.get('title'):
                        # entry 中已有足够信息，直接使用；upload_date 空时用相对时间推算（下载时再更新精确值）
                        ud = entry.get('upload_date', '') or self._entry_upload_date_fallback(entry)
                        if isinstance(ud, str) and len(ud) == 10 and '-' in ud:
                            ud = ud.replace('-', '')
                        video_data = {
                            'title': entry.get('title', 'Unknown Title'),
                            'url': video_url,
                            'id': video_id,
                            'duration': entry.get('duration', 0),
                            'view_count': entry.get('view_count', 0),
                            'uploader': entry.get('uploader', channel_name),
                            'channel': channel_name,
                            'channel_id': entry.get('channel_id', ''),
                            'upload_date': ud[:8] if ud else '',
                            'thumbnail': entry.get('thumbnail', ''),
                            'description': entry.get('description', '')[:200] if entry.get('description') else ''
                        }
                        _disp = (video_data.get('title') or '')[:50]
                        print(f"✓ {count} -- {_disp} -- {video_data['view_count']:,} 观看" + (f" ({ud[:8]})" if ud else "") + " (使用列表信息)")
                    else:
                        # entry 中信息不足，尝试获取详细信息
                        try:
                            video_data = self.get_video_detail(video_url, channel_name)
                            _disp = (video_data.get('title') or '')[:50]
                            print(f"✓ {count} -- {_disp} -- {video_data['view_count']:,} 观看")
                        except Exception as e:
                            error_msg = str(e)
                            print(f"⚠️ 跳过视频: {error_msg}")
                            continue
                    
                    if video_data:
                        is_new_video = self.is_video_new(video_data)
                        if is_new_video:
                            self.channel_videos.append(video_data)
            
            self.channel_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
            self.channel_videos = [video for video in self.channel_videos if video.get('view_count', 0) >= min_view_count]
            self.latest_date = max(
                                    (
                                        datetime.strptime(v["upload_date"], "%Y%m%d")
                                        for v in self.channel_videos
                                        if v.get("upload_date")
                                    ),
                                    default=None
                                )                    

            _normalize_channel_videos_for_storage(self.channel_videos)
            with open(self.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.channel_videos, f, ensure_ascii=False, indent=2)

            return channel_name
            
        except Exception as e:
            print(f"❌ 获取视频列表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # YouTube 元数据字段：更新列表时从抓取结果覆盖，不覆盖用户添加的 audio_path/status/topic_* 等
    YOUTUBE_META_FIELDS = (
        'title',
        'url',
        'duration',
        'view_count',
        'uploader',
        'channel',
        'channel_id',
        'upload_date',
        'thumbnail',
        'description',
    )

    def fetch_channel_new_videos(self, channel_url, max_videos=5000):
        """抓取频道视频列表，返回 (新视频列表, 全部抓取数据 by_id)。
        全部抓取数据用于更新已有视频的观看次数等信息，不浪费本次调用。"""
        self._check_and_update_cookies()
        try:
            # approximate_date：从频道页相对时间估算 upload_date，一次请求即可拿到
            ydl_opts = self._get_ydl_opts_base(
                quiet=False,
                extract_flat='in_playlist',
                skip_download=True,
                extractor_args={'youtubetab': ['approximate_date']},
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
            if not info or 'entries' not in info:
                return [], {}
            channel_name = self.get_channel_name(info)
            new_videos = []
            all_fetched_by_id = {}
            for count, entry in enumerate(info['entries']):
                if count >= max_videos:
                    break
                if not entry:
                    continue
                video_url = entry.get('url', '') or entry.get('webpage_url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                video_id = entry.get('id', '')
                video_data = None
                if entry.get('view_count') is not None and entry.get('title'):
                    # 优先 entry.upload_date，空则用相对时间推算（1天=24h, 1周=24*7h, 3月=3*30*24h），最后才请求 get_video_detail
                    ud = entry.get('upload_date', '') or self._entry_upload_date_fallback(entry) or ''
                    if isinstance(ud, str) and len(ud) == 10 and '-' in ud:
                        ud = ud.replace('-', '')  # YYYY-MM-DD -> YYYYMMDD
                    video_data = {
                        'title': entry.get('title', 'Unknown Title'),
                        'url': video_url,
                        'id': video_id,
                        'duration': entry.get('duration', 0),
                        'view_count': entry.get('view_count', 0),
                        'uploader': entry.get('uploader', channel_name),
                        'channel': channel_name,
                        'channel_id': entry.get('channel_id', ''),
                        'upload_date': ud[:8] if ud else '',
                        'thumbnail': entry.get('thumbnail', ''),
                        'description': entry.get('description', '')[:200] if entry.get('description') else ''
                    }
                    # 仍无 upload_date 时再请求 get_video_detail 补全（下载时也会更新精确值）
                    if not video_data['upload_date']:
                        try:
                            full = self.get_video_detail(video_url, channel_name)
                            if full and full.get('upload_date'):
                                video_data['upload_date'] = (full['upload_date'] or '').replace('-', '')[:8]
                                video_data['thumbnail'] = full.get('thumbnail') or video_data['thumbnail']
                        except Exception:
                            pass
                    _disp = (video_data.get('title') or '')[:50]
                    print(f"✓ {count} -- {_disp} -- {video_data['view_count']:,} 观看" + (f" ({video_data.get('upload_date', '')[:8]})" if video_data.get('upload_date') else ""))
                else:
                    try:
                        video_data = self.get_video_detail(video_url, channel_name)
                        if video_data and video_data.get('upload_date'):
                            ud = video_data['upload_date']
                            if isinstance(ud, str) and len(ud) == 10 and '-' in ud:
                                video_data['upload_date'] = ud.replace('-', '')[:8]
                        _disp = (video_data.get('title') or '')[:50]
                        print(f"✓ {count} -- {_disp} -- {video_data['view_count']:,} 观看")
                    except Exception as e:
                        print(f"⚠️ 跳过视频: {e}")
                        continue
                if video_data:
                    all_fetched_by_id[video_id] = video_data
                    if self.is_video_new(video_data):
                        new_videos.append(video_data)
            return new_videos, all_fetched_by_id
        except Exception as e:
            print(f"❌ 抓取视频列表失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return None  # None 表示出错；([] , {}) 表示无新视频

    def _progress_hook(self, d):
        """下载进度回调函数"""
        if d['status'] == 'downloading':
            if 'total_bytes' in d and d['total_bytes']:
                percent = d['downloaded_bytes'] / d['total_bytes'] * 100
                speed = d.get('speed', 0)
                if speed:
                    speed_mb = speed / 1024 / 1024
                    print(f"📥 下载进度: {percent:.1f}% - 速度: {speed_mb:.1f} MB/s")
                else:
                    print(f"📥 下载进度: {percent:.1f}%")
            else:
                print(f"📥 下载中... {d.get('downloaded_bytes', 0)} bytes")
        elif d['status'] == 'finished':
            print(f"✅ 下载完成: {d.get('filename', 'Unknown file')}")
        elif d['status'] == 'error':
            print(f"❌ 下载错误: {d.get('error', 'Unknown error')}")



    def upload_video(
        self,
        file_path,
        thumbnail_path,
        title,
        description,
        language,
        script_path,
        secret_key,
        channel_id,
        categoryId,
        tags,
        privacy="unlisted",
        publish_at=None,
    ):
        """
        publish_at: 若为 datetime，则定时公开（YouTube 要求 privacy 为 private，并设置 status.publishAt，UTC RFC3339）。
        若为 None，则按 privacy 立即上传（如 unlisted）。
        """
        scopes = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]

        # 区分不同频道的 token 文件
        token_file = config.get_channel_path(channel_id) + f"/token_{channel_id}.json"
        credentials = None

        # 检查是否存在已保存的凭证
        if os.path.exists(token_file):
            credentials = Credentials.from_authorized_user_file(token_file, scopes)
        
        # 如果没有有效凭证，则启动 OAuth 2.0 登录流程
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                # the cient secret json is now just under fold config.get_channel_path(channel_id)
                client_secret_file = os.path.join(config.get_channel_path(channel_id), secret_key)
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(client_secret_file, scopes)
                # 运行时，浏览器会自动打开，请在浏览器中选择您想上传到的频道
                credentials = flow.run_local_server(port=8080)
            
            # 保存凭证以备下次使用
            with open(token_file, 'w') as token:
                token.write(credentials.to_json())

        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

        # Map language codes to YouTube's language format
        language_mapping = {
            "en": "en",
            "zh": "zh-CN",
            "tw": "zh-TW", 
            "ja": "ja",
            "ko": "ko",
            "es": "es",
            "fr": "fr",
            "de": "de",
            "pt": "pt",
            "ru": "ru",
            "ar": "ar"
        }
        
        # Get the proper YouTube language code
        youtube_language = language_mapping.get(language, language)

        status_block = {
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        }
        if publish_at is not None:
            # API：仅当 privacyStatus 为 private 且从未发布过时，可设置 publishAt
            if not isinstance(publish_at, datetime):
                raise TypeError("publish_at 须为 datetime 或 None")
            local_tz = datetime.now().astimezone().tzinfo
            dt_utc = publish_at if publish_at.tzinfo else publish_at.replace(tzinfo=local_tz)
            dt_utc = dt_utc.astimezone(timezone.utc)
            publish_at_str = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            status_block["privacyStatus"] = "private"
            status_block["publishAt"] = publish_at_str
            print(f"📅 定时发布（UTC）: {publish_at_str}")
        else:
            status_block["privacyStatus"] = privacy

        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": categoryId,
                "defaultLanguage": youtube_language,  # Video language
                "defaultAudioLanguage": youtube_language  # Audio language
            },
            "status": status_block,
            # ✅ NEW: Add localizations for title and description language
            "localizations": {
                youtube_language: {
                    "title": title,
                    "description": description
                }
            }
        }

        media_file = googleapiclient.http.MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)

        request = youtube.videos().insert(
            part="snippet,status,localizations",  # ✅ UPDATED: Include localizations part
            body=request_body,
            media_body=media_file
        )

        response = request.execute()
        video_id = response["id"]
        snippet = response.get("snippet") or {}
        published_at_iso = (
            snippet.get("publishedAt")
            or snippet.get("published_at")
            or ""
        )
        print("✅ Upload successful! Video ID:", video_id)
        print(f"📝 Video settings applied:")
        print(f"   - Privacy: {request_body['status'].get('privacyStatus')}")
        if request_body["status"].get("publishAt"):
            print(f"   - publishAt: {request_body['status']['publishAt']}")
        print(f"   - Made for Kids: {request_body['status']['selfDeclaredMadeForKids']}")
        print(f"   - Altered Content: {request_body['status']['containsSyntheticMedia']}")
        print(f"   - Video Language: {youtube_language}")
        print(f"   - Title/Description Language: {youtube_language}")

        # 上传缩略图（如果提供了thumbnail_path）
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                self.upload_thumbnail(youtube, video_id, thumbnail_path)
            except Exception as e:
                print(f"⚠️ 缩略图上传失败: {e}")

        # 上传字幕文件（如果提供了script_path）
        if script_path and os.path.exists(script_path):
            try:
                # Use the same language for subtitles
                self.upload_subtitle(youtube, video_id, script_path, youtube_language)
            except Exception as e:
                print(f"⚠️ 字幕上传失败: {e}")

        return video_id, (published_at_iso or "").strip()


    def upload_thumbnail(self, youtube, video_id, thumbnail_path):
        """上传缩略图到YouTube视频"""
        media_file = googleapiclient.http.MediaFileUpload(
            thumbnail_path,
            mimetype="image/jpeg",
            resumable=True
        )

        request = youtube.thumbnails().set(
            videoId=video_id,
            media_body=media_file
        )

        response = request.execute()
        print(f"✅ 缩略图上传成功! Video ID: {video_id}")
        return response


    def upload_subtitle(self, youtube, video_id, script_path, language):
        """上传字幕文件到YouTube视频"""
        subtitle_body = {
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": f"Subtitles ({language})",
            }
        }

        media_file = googleapiclient.http.MediaFileUpload(
            script_path, 
            mimetype="text/plain",
            resumable=True
        )

        request = youtube.captions().insert(
            part="snippet",
            body=subtitle_body,
            media_body=media_file
        )

        response = request.execute()
        print(f"✅ 字幕上传成功! Caption ID: {response['id']}")
        return response["id"]


    def pick_best_caption_language(self, all_languages):
        """优先选择中文，其次英文；若无则返回 None"""
        if not all_languages:
            return None
        zh_langs = [l for l in all_languages if l and (l.startswith('zh') or l in ('zh-Hans', 'zh-Hant', 'zh-CN', 'zh-TW'))]
        en_langs = [l for l in all_languages if l and l.startswith('en')]
        if zh_langs:
            return zh_langs[0]
        if en_langs:
            return en_langs[0]
        return all_languages[0]

    def try_download_caption_only(self, video_detail, target_lang):
        """仅尝试下载字幕，不 fallback 到音频转录；成功返回路径，失败返回 None"""
        if not target_lang or not self.cookie_file:
            return None
        video_url = video_detail.get('url', '')
        if not video_url:
            return None
        download_prefix = self.youtube_dir + "/media/" + self.generate_video_prefix(video_detail)
        ydl_opts = self._get_ydl_opts_base(
            skip_download=True,
            writesubtitles=True,
            writeautomaticsub=True,
            subtitleslangs=[target_lang],
            subtitlesformat="srt",
            outtmpl=download_prefix,
            quiet=True,
            no_warnings=True,
        )
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            src_path = self._find_caption_srt(download_prefix, target_lang)
            if src_path:
                print(f"✅ 已下载字幕：语言 {target_lang}")
                return src_path
        except Exception as e:
            print(f"⚠️ 字幕下载失败: {e}")
        return None



# YouTube GUI管理类
class MediaGUIManager:
    """YouTube GUI管理器 - 处理所有YouTube相关的GUI对话框"""
    
    def __init__(self, root, channel, pid, tasks, log_to_output_func, download_output, language, workflow_gui=None):
        self.root = root
        self.workflow_gui = workflow_gui

        self.channel = channel
        channel_path = config.get_channel_path(config_channel.get_channel_id(channel))
        self.channel_path = channel_path
        self.youtube_dir = f"{channel_path}/Download"

        os.makedirs(self.youtube_dir, exist_ok=True)
        os.makedirs(f"{self.youtube_dir}/media", exist_ok=True)
        os.makedirs(f"{self.youtube_dir}/work", exist_ok=True)

        self.pid = pid
        self.tasks = tasks
        self.log_to_output = log_to_output_func
        self.download_output = download_output
        self._input_language = (language or 'zh').strip().lower()
        if self._input_language not in config.LANGUAGES:
            self._input_language = 'zh'
        self.language = self._input_language  # 与 config.LANGUAGES 键一致（欢迎屏已选）
        _dl_lang = 'en' if self._input_language == 'en' else 'zh'  # yt-dlp 字幕常用 en/zh
        
        self.llm_api_local = llm_api.LLMApi(llm_api.GPT_MINI)
        self.llm_api = llm_api.LLMApi()

        # 创建YoutubeDownloader实例
        self.downloader = MediaDownloader(pid, self.youtube_dir, _dl_lang)
        
        # 跟踪活跃的摘要生成线程，确保对话框关闭时不会丢失数据
        self.active_summary_threads = []
        self.active_threads_lock = threading.Lock()

        self.topic_choices, self.topic_categories, self.tag_features_map = config.load_topics(channel)
        try:
            _ensure_topic_category_list_files(self.channel_path, self.topic_categories)
        except Exception:
            pass
        
        # 初始化主主题分类变量
        self.main_topic_category = None

    def _channel_config_key(self) -> str:
        ch = (self.channel or "").strip()
        if ch:
            return ch
        return os.path.basename(self.channel_path or "")


    def _do_create_new_channel_from_url(self):
        """创建新频道：弹窗输入频道/视频链接，解析出频道名，创建列表（可选获取视频）"""
        url = simpledialog.askstring("创建新频道", "输入 YouTube 频道链接或视频链接：", parent=self.root)
        if not url or not url.strip():
            return None
        url = url.strip()
        try:
            channel_name, channel_url = self.downloader.fetch_channel_info_from_url(url)
        except Exception as e:
            self.root.after(0, lambda e=e: show_auto_close_popup(self.root, "错误", f"解析链接失败: {e}", kind="error"))
            return None
        if not channel_name:
            self.root.after(0, lambda: show_auto_close_popup(self.root, "错误", "无法解析频道名称", kind="error"))
            return None
        new_name = simpledialog.askstring("创建新频道", "频道名称（可修改）:", initialvalue=channel_name, parent=self.root)
        if not new_name or not new_name.strip():
            return None
        channel_name = new_name.strip()
        self.downloader.channel_list_json = os.path.join(self.downloader.channel_list_dir, f"{channel_name}.json")
        self.downloader.channel_videos = []
        os.makedirs(os.path.dirname(self.downloader.channel_list_json), exist_ok=True)
        if channel_url and messagebox.askyesno("获取视频", f"是否从该频道获取热门视频列表？\n\n频道: {channel_name}", parent=self.root):
            cn = self.downloader.list_hot_videos(channel_url, max_videos=5000, min_view_count=0)
            if not cn:
                self.root.after(0, lambda: messagebox.showwarning("提示", "获取视频列表失败或为空", parent=self.root))
                return None
        else:
            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        self.downloader.channel_name = channel_name
        for v in self.downloader.channel_videos:
            self.check_video_status(v)
        return True

    def manage_hot_videos(self):
        # 语言已在 YT 欢迎屏（project_manager.show_initial_choice_dialog）选择
        self.downloader.language = 'en' if self.language == 'en' else 'zh'

        # 查找所有热门视频JSON文件
        pattern = os.path.join(self.downloader.channel_list_dir, "*.json")
        json_files = glob.glob(pattern)
        
        # 无已有文件时，直接进入创建新频道流程
        if not json_files:
            if self._do_create_new_channel_from_url():
                self._show_channel_videos_dialog()
            return
        
        # 提取频道名称
        channel_data = []
        for json_file in json_files:
            filename = os.path.basename(json_file)
            # 从文件名中提取频道名：频道名.json -> 频道名
            match = re.match(r'(.+?)\.json', filename)
            if match:
                channel_name = match.group(1)
                # 读取文件获取视频数量
                video_count = 0
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                for encoding in encodings:
                    try:
                        with open(json_file, 'r', encoding=encoding) as f:
                            videos = json.load(f)
                            video_count = len(videos) if isinstance(videos, list) else 0
                        break  # 成功读取后退出循环
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                        if encoding == encodings[-1]:  # 最后一个编码也失败
                            print(f"❌ 读取频道视频列表失败 (尝试了所有编码): {e}")
                        continue
                    except Exception as e:
                        print(f"❌ 读取频道视频列表失败: {e}")
                        break
                
                channel_data.append({
                    'name': channel_name,
                    'file': json_file,
                    'video_count': video_count
                })
        
        if not channel_data:
            messagebox.showwarning("提示", "未找到有效的频道视频列表")
            return
        
        # 准备选项列表和映射，加入【创建新频道】
        channel_choices = []
        choice_to_channel = {}
        for channel in channel_data:
            choice_text = f"{channel['name']} ({channel['video_count']} 个视频)"
            channel_choices.append(choice_text)
            choice_to_channel[choice_text] = channel
        CREATE_NEW = "【创建新频道】"
        channel_choices.append(CREATE_NEW)
        
        # 使用 askchoice 显示选择对话框
        picked = askchoice("选择频道", channel_choices, parent=self.root)
        if not picked:
            return  # 用户取消
        _, selected_choice = picked
        if selected_choice == CREATE_NEW:
            # 创建新频道（输入频道/视频链接，解析频道名）
            if self._do_create_new_channel_from_url():
                for v in self.downloader.channel_videos:
                    self.check_video_status(v)
                self._show_channel_videos_dialog()
            return
        
        if selected_choice not in choice_to_channel:
            return
        # 获取选中的频道
        channel = choice_to_channel[selected_choice]
        self.downloader.channel_list_json = channel['file']
        
        # 读出 list：按外层 id 去重（YouTube id / 项目 pid）；勿按展示标题合并不同项目行
        with open(self.downloader.channel_list_json, 'r', encoding='utf-8') as f:
            channel_videos = json.load(f)

        _normalize_channel_videos_for_storage(channel_videos)

        for video in channel_videos:
            scene_content = video.get('scene_content')
            if isinstance(scene_content, str):
                try:
                    scene_content = json.loads(scene_content)
                except Exception:
                    video.pop('scene_content', None)
                    continue
            if isinstance(scene_content, list) and scene_content:
                video['scene_content'] = scene_content
            else:
                video.pop('scene_content', None)

        cleaned = dedupe_channel_video_list(channel_videos)

        for video_detail in cleaned:
            video_detail.pop('description', '')
            video_detail.pop('thumbnail', '')
            video_detail.pop('uploader', '')

        _normalize_channel_videos_for_storage(cleaned)
        with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)

        self.downloader.channel_videos = cleaned
        self.downloader.latest_date = max(
            (
                datetime.strptime(v["upload_date"], "%Y%m%d")
                for v in self.downloader.channel_videos
                if v.get("upload_date")
            ),
            default=None
        )
        if not self.downloader.channel_videos:
            messagebox.showwarning("提示", "视频列表为空")
            return

        self.downloader.channel_name = channel['name']   
        for video in self.downloader.channel_videos:
            self.check_video_status(video)
        # 显示该频道的视频管理对话框
        self._show_channel_videos_dialog()


    def fetch_text_content(self, video_detail):
        text = config.read_transcript_text_from_video_detail(video_detail)
        return text if text else None

    def _analyze_content_source_text(
        self, video_detail: dict, *, override: str | None = None
    ) -> str:
        """内容概括 / 生成 analyzed_content 的 LLM 用户输入：优先 override → 转录 → 已有 analyzed_content。"""
        if override is not None:
            ov = str(override).strip()
            if ov:
                return ov
        t = (self.fetch_text_content(video_detail) or "").strip()
        if t:
            return t
        return video_detail.get("analyzed_content")


    def _youtube_story_title_from_video_detail(self, video_detail) -> str:
        if not isinstance(video_detail, dict):
            return ""
        story_title = project_manager.story_first_entry_heading(
            video_detail.get("story")
        )
        if story_title:
            return story_title
        source = _youtube_row_source_title(video_detail)
        if source:
            return source
        sc = video_detail.get("scene_content")
        scenes = sc if isinstance(sc, list) else []
        if scenes:
            first = scenes[0]
            if isinstance(first, dict):
                cap = project_manager.caption_from_scene_content_item(first)
                if cap:
                    return cap
        return ""



    def _youtube_story_llm_source_text(self, video_detail) -> str:
        """Story 智能添加 / 生成的 LLM 输入原文。"""
        if not isinstance(video_detail, dict):
            return ""
        scenes = video_detail.get("scene_content") or []
        if not isinstance(scenes, list):
            scenes = []
        for item in scenes:
            if not isinstance(item, dict):
                continue
            for key in ("story", "visual", "voiceover", "speaking"):
                text = (item.get(key) or "").strip()
                if text:
                    return text
        ac = video_detail.get("analyzed_content")
        if ac.strip():
            return ac.strip()
        return (config.read_transcript_text_from_video_detail(video_detail) or "").strip()

    def _generate_youtube_story_summary_text(self, video_detail) -> str:
        source = self._youtube_story_llm_source_text(video_detail)
        if not source:
            return ""
        prompt = config_prompt.YOUTUBE_PUBLISH_DESCRIPTION_PROMPT.format(
            language=config.llm_language_label(self.language)
        )
        result = self.llm_api_local.generate_text(prompt, source)
        return config.chinese_convert(result or "", self.language).strip()


    def _generate_story(
        self,
        video_detail: dict,
        *,
        prompt_label: str = "",
        instruction: str = "",
    ) -> list[dict]:
        if not (video_detail.get("analyzed_content") or "").strip():
            return []

        channel_key = self._channel_config_key()
        lbl, template, idx = _resolve_story_prompt_template(
            channel_key, label=(prompt_label or "").strip() or None
        )
        if not template:
            return []

        cat, sub, topic = _notebooklm_row_topic_fields(video_detail)
        prompt = _build_notebooklm_prompt_for_row(
            self,
            video_detail,
            template,
            instruction=instruction,
            sections=idx + 1,
            topic=topic,
            tags=_notebooklm_row_tags_text(video_detail),
            topic_category=cat,
            topic_subtype=sub,
        )
        if not (prompt or "").strip():
            return []

        parsed = self.llm_api.generate_json(prompt, "", expect_list=True)
        if isinstance(parsed, dict):
            one = _normalize_story_entry(parsed)
            return [one] if one else []
        if isinstance(parsed, list):
            out: list[dict] = []
            for it in parsed:
                n = _normalize_story_entry(it) if isinstance(it, dict) else None
                if n:
                    out.append(n)
            return out
        return []


    def _story_prompt_text_for_label(
        self,
        video_detail: dict,
        prompt_label: str,
        *,
        instruction: str = "",
        story_override: str | None = None,
        content_override: str | None = None,
    ) -> tuple[str, str]:
        """按频道 ``story_prompt_choices`` 的 label 生成完整 prompt 文本。"""
        channel_key = self._channel_config_key()
        lbl, template, idx = _resolve_story_prompt_template(
            channel_key, label=prompt_label
        )
        if not template:
            return "", ""
        cat, sub, topic = _notebooklm_row_topic_fields(video_detail)
        prompt = _build_notebooklm_prompt_for_row(
            self,
            video_detail,
            template,
            instruction=instruction,
            sections=idx + 1,
            topic=topic,
            tags=_notebooklm_row_tags_text(video_detail),
            topic_category=cat,
            topic_subtype=sub,
            story_override=story_override,
            content_override=content_override,
        )
        return lbl, prompt


    def _notebooklm_prompt_text_for_label(
        self,
        video_detail: dict,
        prompt_label: str,
        *,
        instruction: str = "",
        story_override: str | None = None,
        content_override: str | None = None,
    ) -> tuple[str, str]:
        """按频道 config 的提示 label 生成完整 prompt 文本。"""
        channel_key = self._channel_config_key()
        lbl, template, idx = _resolve_notebooklm_prompt_template(
            channel_key, label=prompt_label
        )
        if not template:
            return "", ""
        cat, sub, topic = _notebooklm_row_topic_fields(video_detail)
        prompt = _build_notebooklm_prompt_for_row(
            self,
            video_detail,
            template,
            instruction=instruction,
            sections=idx + 1,
            topic=topic,
            tags=_notebooklm_row_tags_text(video_detail),
            topic_category=cat,
            topic_subtype=sub,
            story_override=story_override,
            content_override=content_override,
        )
        return lbl, prompt

    def _generate_scene_content_from_notebooklm_prompt(
        self,
        video_detail: dict,
        prompt_label: str,
        *,
        instruction: str = "",
    ) -> list | None:
        """用所选 NotebookLM 提示生成 scene_content array（整段 prompt 已含 user input 占位符）。"""
        _, prompt = self._notebooklm_prompt_text_for_label(
            video_detail, prompt_label, instruction=instruction
        )
        if not (prompt or "").strip():
            return None
        raw = self.llm_api.generate_json(prompt, "", expect_list=True)
        scenes = raw if isinstance(raw, list) else []
        return scenes if scenes else None

    def _run_scene_smart_generate_async(
        self,
        parent,
        video_detail: dict,
        prompt_label: str,
        set_scene_json,
        *,
        get_instruction=None,
        on_busy=None,
        on_idle=None,
        persist_fn=None,
        on_saved=None,
    ) -> bool:
        """智能生成 scene_content：替换现有内容并自动保存。"""
        if not prompt_label:
            prompt_label = _default_scene_editor_prompt_label(
                video_detail, self._channel_config_key()
            )
        if on_busy:
            on_busy()

        def work():
            err_msg = ""
            scenes: list | None = None
            instr = (get_instruction() or "").strip() if callable(get_instruction) else ""
            try:
                scenes = self._generate_scene_content_from_notebooklm_prompt(
                    video_detail, prompt_label, instruction=instr
                )
            except Exception as ex:
                err_msg = str(ex)

            def apply():
                if on_idle:
                    on_idle()
                if err_msg:
                    show_auto_close_popup(parent, "生成失败", err_msg, kind="error")
                    return
                if not scenes:
                    messagebox.showwarning(
                        "提示",
                        "LLM 未返回有效 scene_content（须为 JSON array）。",
                        parent=parent,
                    )
                    return
                scene_json = json.dumps(scenes, ensure_ascii=False, indent=2)
                video_detail["scene_content"] = scenes
                set_scene_json(scene_json)
                persist = persist_fn or (
                    lambda vd, parent=None: self._persist_video_detail_story(
                        vd, parent=parent
                    )
                )
                if not persist(video_detail, parent=parent):
                    return
                try:
                    _copy_text_to_clipboard(parent, scene_json)
                except Exception:
                    pass
                if callable(on_saved):
                    try:
                        on_saved()
                    except Exception:
                        pass
                show_auto_close_popup(
                    parent,
                    "已生成场景",
                    f"已用「{prompt_label}」生成 {len(scenes)} 个场景，并已保存到频道列表。",
                )

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()
        return True

    def _rewrite_text_speaking_concise(self, source: str) -> str:
        """用 ``STORY_CONDENSE_PROMPT`` 精简改写 story 正文。"""
        text = (source or "").strip()
        if not text:
            return ""
        prompt = config_prompt.STORY_CONDENSE_PROMPT.format(
            language=config.llm_language_label(self.language)
        )
        out = self.llm_api_local.generate_text(prompt, text)
        return config.chinese_convert((out or "").strip(), self.language)

    def _run_story_speaking_concise_async(
        self,
        parent,
        video_detail: dict,
        get_existing_text,
        set_merged_text,
        *,
        on_busy=None,
        on_idle=None,
        persist_fn=None,
    ) -> bool:
        """Story 编辑区：用 STORY_CONDENSE prompt 改写首条 ``story`` 正文并写回。"""
        raw = (get_existing_text() or "").strip()
        if not raw:
            messagebox.showwarning(
                "提示", "编辑区无 story 内容。", parent=parent
            )
            return False
        if on_busy:
            on_busy()

        def work():
            err_msg = ""
            merged_json = ""
            try:
                if raw.lstrip().startswith("["):
                    entries = _parse_story_field(raw)
                    if not entries:
                        err_msg = "无法解析 story JSON array。"
                    else:
                        rewritten: list[dict] = []
                        for i, entry in enumerate(entries):
                            body = (entry.get("story") or "").strip()
                            if i == 0 and body:
                                body = self._rewrite_text_speaking_concise(body)
                            updated = dict(entry)
                            if body:
                                updated["story"] = body
                            rewritten.append(updated)
                        merged_json = _story_entries_to_json_text(rewritten)
                else:
                    merged_json = self._rewrite_text_speaking_concise(raw)
            except Exception as ex:
                err_msg = str(ex)

            def apply():
                if on_idle:
                    on_idle()
                if err_msg:
                    show_auto_close_popup(parent, "改写失败", err_msg, kind="error")
                    return
                if not (merged_json or "").strip():
                    messagebox.showwarning(
                        "提示", "LLM 未返回有效 story 文本。", parent=parent
                    )
                    return
                video_detail["story"] = merged_json
                set_merged_text(merged_json)
                persist = persist_fn or (
                    lambda vd, parent=None: self._persist_video_detail_story(
                        vd, parent=parent
                    )
                )
                if not persist(video_detail, parent=parent):
                    return
                show_auto_close_popup(
                    parent,
                    "已改写 Story",
                    "已用 Story 精简 prompt 改写首条 story 正文，并已保存到频道列表。",
                )

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()
        return True

    def _run_story_add_async(
        self,
        parent,
        video_detail: dict,
        get_existing_text,
        set_merged_text,
        *,
        prompt_label: str = "",
        get_instruction=None,
        on_busy=None,
        on_idle=None,
        on_title_updated=None,
        persist_fn=None,
    ) -> bool:
        """增加 Story：analyzed_content + 所选 story 提示词 → merge JSON array。"""
        if not video_detail.get("analyzed_content"):
            messagebox.showwarning(
                "提示",
                "需要 analyzed_content 作为原始材料。\n请先在「分析」中填写或生成内容。",
                parent=parent,
            )
            return False
        channel_key = self._channel_config_key()
        sel = (prompt_label or "").strip()
        if not sel:
            sel = _default_story_editor_prompt_label(channel_key)
        if not sel and not _story_prompt_choices(channel_key):
            messagebox.showwarning(
                "提示",
                "当前频道未配置 story_prompt_choices，无法生成 Story。",
                parent=parent,
            )
            return False
        if on_busy:
            on_busy()

        def work():
            err_msg = ""
            new_entries: list[dict] = []
            instr = ""
            if callable(get_instruction):
                instr = (get_instruction() or "").strip()
            try:
                new_entries = self._generate_story(
                    video_detail,
                    prompt_label=sel,
                    instruction=instr,
                )
            except Exception as ex:
                err_msg = str(ex)

            def apply():
                if on_idle:
                    on_idle()
                if err_msg:
                    show_auto_close_popup(parent, "生成失败", err_msg, kind="error")
                    return
                if not new_entries:
                    messagebox.showwarning(
                        "提示",
                        "LLM 未返回有效 story JSON（需含 title/story 或 mini 字段等）。",
                        parent=parent,
                    )
                    return
                existing = _parse_story_field(get_existing_text())
                merged = _merge_story_entries(existing, new_entries)
                merged_json = _story_entries_to_json_text(merged)
                video_detail["story"] = merged_json
                new_title = _story_entry_heading(new_entries[0])
                if new_title:
                    _apply_story_title_to_project_profile(video_detail, new_title)
                    ch_path = self.channel_path or ""
                    _normalize_channel_list_item_for_storage(
                        video_detail, ch_path
                    )
                set_merged_text(merged_json)
                if callable(on_title_updated):
                    try:
                        on_title_updated()
                    except Exception:
                        pass
                persist = persist_fn or (
                    lambda vd, parent=None: self._persist_video_detail_story(
                        vd, parent=parent
                    )
                )
                if not persist(video_detail, parent=parent):
                    return
                show_auto_close_popup(
                    parent,
                    "已增加 Story",
                    f"已合并 {len(new_entries)} 条新 story，并已保存到频道列表。"
                    + (
                        f"\n项目成片名已更新为：{new_title}"
                        if new_title
                        and project_manager.list_json_row_has_project_profile(
                            video_detail
                        )
                        else "\n（未绑定 project_profile，未改项目名）"
                    ),
                )

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()
        return True


    def _persist_video_detail_story(self, video_detail: dict, *, parent=None) -> bool:
        """将 ``video_detail`` 同步进 ``channel_videos`` 并写入 ``channel_list_json``。"""
        if not isinstance(video_detail, dict):
            return False
        list_path = (getattr(self.downloader, "channel_list_json", None) or "").strip()
        if not list_path:
            show_auto_close_popup(
                parent,
                "保存失败",
                "未打开频道列表 JSON，无法保存。",
                kind="error",
            )
            return False
        row_key = (video_detail.get("id") or video_detail.get("url") or "").strip()
        wf_pid = _video_detail_project_pid(video_detail)
        for row in self.downloader.channel_videos:
            if not isinstance(row, dict):
                continue
            rk = (row.get("id") or row.get("url") or "").strip()
            if row_key and rk and rk == row_key:
                if row is not video_detail:
                    row.clear()
                    row.update(video_detail)
                break
            if wf_pid and _video_detail_project_pid(row) == wf_pid:
                if row is not video_detail:
                    row.clear()
                    row.update(video_detail)
                break
        ch_path = self.channel_path or ""
        _normalize_channel_list_item_for_storage(video_detail, ch_path)
        _normalize_channel_videos_for_storage(
            self.downloader.channel_videos, ch_path
        )
        try:
            with open(list_path, "w", encoding="utf-8") as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            return True
        except OSError as e:
            show_auto_close_popup(
                parent,
                "保存失败",
                f"写入频道列表失败：{e}",
                kind="error",
            )
            return False


    def _show_video_story_editor(
        self,
        parent,
        video_detail: dict,
        *,
        dialog_title: str = "故事 / Story",
        header_text: str = "",
        confirm_label: str = "保存",
        allow_empty: bool = False,
        auto_generate_if_empty: bool = False,
        persist_fn=None,
        on_title_updated=None,
        main_character: str = "",
        channel_path: str = "",
    ) -> str | None:
        """编辑 ``video_detail['story']``（JSON array 或纯文本）；确认后写回频道列表。"""
        persist = persist_fn or (
            lambda vd, parent=None: self._persist_video_detail_story(vd, parent=parent)
        )
        result_holder: list[str | None] = [None]
        dlg = tk.Toplevel(parent)
        dlg.title(dialog_title)
        dlg.geometry("920x820")
        dlg.minsize(640, 560)
        dlg.transient(parent)
        dlg.grab_set()
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"920x820+{(sw - 920) // 2}+{(sh - 820) // 2}")

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        if not header_text:
            header_text = (
                f"{title}\n"
                "选 Story 提示（story_prompt_choices）；导向说明填入 {instruction}；"
                "预览用 analyzed_content 作 {content}；打开或生成 Story 后复制 JSON 首条到剪贴板。"
                "「增加 Story」用所选提示 + analyzed_content 生成并 merge 到列表（各条字段可不同）。"
                "Slideshow / Video 指令仅含生成指令 + JSON 首条 story（不含上方 Story 生成提示）。"
            )
        ttk.Label(frm, text=header_text, wraplength=860).pack(
            anchor=tk.W, pady=(0, 8)
        )

        channel_key = self._channel_config_key()
        story_prompt_choices = _story_prompt_choices(channel_key)
        prompt_row = ttk.Frame(frm)
        prompt_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(prompt_row, text="选Story提示").pack(side=tk.LEFT, padx=(0, 5))
        default_prompt_label = _default_story_editor_prompt_label(channel_key)
        prompt_combo_var = tk.StringVar(value=default_prompt_label)
        prompt_combo = ttk.Combobox(
            prompt_row,
            textvariable=prompt_combo_var,
            values=[opt[0] for opt in story_prompt_choices],
            state="readonly" if story_prompt_choices else "disabled",
            width=18,
        )
        prompt_combo.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(frm, text="导向说明（{instruction}，可选）：").pack(
            anchor=tk.W, pady=(0, 2)
        )
        instruction_frm = ttk.Frame(frm)
        instruction_frm.pack(fill=tk.X, pady=(0, 8))
        instruction_tx = scrolledtext.ScrolledText(
            instruction_frm, wrap=tk.WORD, width=100, height=3, font=("Arial", 9)
        )
        instruction_tx.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(frm, text="提示词预览（切换选项/编辑导向说明时更新，不写入剪贴板）：").pack(
            anchor=tk.W, pady=(0, 2)
        )
        prompt_tx = scrolledtext.ScrolledText(
            frm, wrap=tk.WORD, width=100, height=8, font=("Arial", 9)
        )
        prompt_tx.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(frm, text="story（JSON 数组首条用于 Slideshow / Video 指令）：").pack(
            anchor=tk.W, pady=(0, 2)
        )
        tx = scrolledtext.ScrolledText(
            frm, wrap=tk.WORD, width=100, height=16, font=("Consolas", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        initial = _story_field_editor_text(video_detail.get("story"))
        if initial:
            tx.insert("1.0", initial)
        _bind_text_editor_replace_from_clipboard_on_double_click(tx, dlg)

        def _copy_first_story_to_clipboard():
            clip = _story_first_entry_json_text((tx.get("1.0", tk.END) or ""))
            if clip:
                _copy_text_to_clipboard(dlg, clip)

        if initial:
            _copy_first_story_to_clipboard()

        def _first_story_override_text() -> str:
            entries = _parse_story_field((tx.get("1.0", tk.END) or ""))
            if entries:
                return _story_entry_display_text(entries[0])
            return _notebooklm_story_text(video_detail)

        def refresh_story_prompt(*_args):
            sel = (prompt_combo_var.get() or "").strip()
            if not sel or not story_prompt_choices:
                prompt_tx.delete("1.0", tk.END)
                return
            instr = (instruction_tx.get("1.0", tk.END) or "").strip()
            content_text = (video_detail.get("analyzed_content") or "").strip()
            story_text = _first_story_override_text()
            _, prompt = self._story_prompt_text_for_label(
                video_detail,
                sel,
                instruction=instr,
                story_override=story_text,
                content_override=content_text or story_text,
            )
            prompt_tx.delete("1.0", tk.END)
            if prompt:
                prompt_tx.insert("1.0", prompt)

        _build_instruction_snippet_combo(
            instruction_frm, channel_key, instruction_tx, on_changed=refresh_story_prompt
        )

        if story_prompt_choices:
            prompt_combo.bind("<<ComboboxSelected>>", refresh_story_prompt)
        instruction_tx.bind("<FocusOut>", refresh_story_prompt)
        if story_prompt_choices:
            refresh_story_prompt()

        def _set_editor_text_and_clipboard(text: str) -> None:
            tx.delete("1.0", tk.END)
            if text:
                tx.insert("1.0", text)
            _copy_first_story_to_clipboard()
            refresh_story_prompt()

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X)

        def _busy(btn):
            try:
                btn.config(state=tk.DISABLED)
                dlg.config(cursor="watch")
                dlg.update_idletasks()
            except tk.TclError:
                pass

        def _idle(btn):
            try:
                btn.config(state=tk.NORMAL)
                dlg.config(cursor="")
            except tk.TclError:
                pass

        def on_add_story():
            self._run_story_add_async(
                dlg,
                video_detail,
                lambda: (tx.get("1.0", tk.END) or ""),
                _set_editor_text_and_clipboard,
                prompt_label=(prompt_combo_var.get() or "").strip(),
                get_instruction=lambda: (instruction_tx.get("1.0", tk.END) or ""),
                on_busy=lambda: _busy(add_btn),
                on_idle=lambda: _idle(add_btn),
                on_title_updated=on_title_updated,
                persist_fn=persist,
            )

        def on_speaking_concise():
            self._run_story_speaking_concise_async(
                dlg,
                video_detail,
                lambda: (tx.get("1.0", tk.END) or ""),
                _set_editor_text_and_clipboard,
                on_busy=lambda: _busy(concise_btn),
                on_idle=lambda: _idle(concise_btn),
                persist_fn=persist,
            )

        def on_scene_split():
            self._run_story_scene_split_from_cover_async(
                dlg,
                video_detail,
                (tx.get("1.0", tk.END) or ""),
                on_busy=lambda: _busy(scene_split_btn),
                on_idle=lambda: _idle(scene_split_btn),
                persist_fn=persist,
            )

        _lang_lbl = config.llm_language_label(self.language)
        _story_nb_copy_cycle: dict[str, int] = {"slideshow": -1, "video": -1}

        def on_copy_image_instruction():
            self._copy_notebooklm_story_gen_instruction(
                parent=dlg,
                video_detail=video_detail,
                story_raw=(tx.get("1.0", tk.END) or ""),
                nb_mode="image",
                main_character=main_character,
                channel_path=channel_path or self.channel_path or "",
                cycle_holder=_story_nb_copy_cycle,
            )

        def on_copy_video_instruction():
            self._copy_notebooklm_story_gen_instruction(
                parent=dlg,
                video_detail=video_detail,
                story_raw=(tx.get("1.0", tk.END) or ""),
                nb_mode="video",
                main_character=main_character,
                channel_path=channel_path or self.channel_path or "",
                cycle_holder=_story_nb_copy_cycle,
            )

        def on_copy_speak_instruction():
            self._copy_notebooklm_story_gen_instruction(
                parent=dlg,
                video_detail=video_detail,
                story_raw=(tx.get("1.0", tk.END) or ""),
                nb_mode="speak",
                main_character=main_character,
                channel_path=channel_path or self.channel_path or "",
                cycle_holder=_story_nb_copy_cycle,
            )

        def on_confirm():
            raw = (tx.get("1.0", tk.END) or "").strip()
            if not raw and not allow_empty:
                messagebox.showwarning(
                    "提示", "story 不能为空。", parent=dlg
                )
                return
            entries: list[dict] = []
            if raw:
                entries, story_json = _coerce_story_editor_text(raw)
                if story_json:
                    video_detail["story"] = story_json
                else:
                    video_detail["story"] = raw
            else:
                video_detail.pop("story", None)
            if entries:
                try:
                    stories_path = _prepend_story_entries_to_channel_stories_json(
                        entries,
                        channel_key=channel_key,
                        channel_path=channel_path or self.channel_path or "",
                    )
                    print(f"✅ 已写入 stories.json（插入最前）: {stories_path}")
                except Exception as e:
                    messagebox.showwarning(
                        "stories.json",
                        f"已保存到本条 video_detail，但写入频道 stories.json 失败：\n{e}",
                        parent=dlg,
                    )
            if not persist(video_detail, parent=dlg):
                return
            result_holder[0] = video_detail.get("story") or raw
            dlg.destroy()

        add_btn = ttk.Button(btn_row, text="增加 Story", command=on_add_story)
        add_btn.pack(side=tk.LEFT, padx=(0, 8))
        if not story_prompt_choices:
            add_btn.config(state=tk.DISABLED)
        concise_btn = ttk.Button(btn_row, text="口语精简", command=on_speaking_concise)
        concise_btn.pack(side=tk.LEFT, padx=(0, 8))
        scene_split_btn = ttk.Button(btn_row, text="场景分离", command=on_scene_split)
        scene_split_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_row,
            text=f"To Image - ({_lang_lbl})",
            command=on_copy_image_instruction,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_row,
            text=f"To Video - ({_lang_lbl})",
            command=on_copy_video_instruction,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_row,
            text=f"To Speak - ({_lang_lbl})",
            command=on_copy_speak_instruction,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text=confirm_label, command=on_confirm).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(btn_row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.wait_window()
        return result_holder[0]

    def _show_analyzed_content_editor(
        self,
        parent,
        video_detail: dict,
        *,
        on_saved=None,
        on_content_summarized=None,
        enable_content_summary: bool = True,
        persist_fn=None,
    ) -> str | None:
        """编辑 ``video_detail['analyzed_content']``（纯文本）；确认后写回频道列表。"""
        persist = persist_fn or (
            lambda vd, parent=None: self._persist_video_detail_story(vd, parent=parent)
        )
        result_holder: list[str | None] = [None]
        dlg = tk.Toplevel(parent)
        dlg.title("分析内容 / Analyzed")
        dlg.geometry("820x580")
        dlg.minsize(560, 400)
        dlg.transient(parent)
        dlg.grab_set()
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"820x580+{(sw - 820) // 2}+{(sh - 580) // 2}")

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        ttk.Label(
            frm,
            text=(
                f"{title}\n"
                "分析内容 analyzed_content（可编辑；双击编辑区可用剪贴板内容替换全文；"
                "「内容概括」可重新生成；保存后写回本条并保存频道列表）"
            ),
            wraplength=760,
        ).pack(anchor=tk.W, pady=(0, 8))

        tx = scrolledtext.ScrolledText(
            frm, wrap=tk.WORD, width=90, height=24, font=("Arial", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        initial = video_detail.get("analyzed_content")
        if initial:
            tx.insert("1.0", initial)
            _copy_text_to_clipboard(dlg, initial)
        _bind_text_editor_replace_from_clipboard_on_double_click(tx, dlg)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X)

        def on_confirm():
            new_text = tx.get("1.0", tk.END)
            if new_text:
                video_detail["analyzed_content"] = new_text
            else:
                video_detail.pop("analyzed_content", None)
            if not persist(video_detail, parent=dlg):
                return
            result_holder[0] = new_text
            dlg.destroy()
            if callable(on_saved):
                on_saved()

        def on_content_summary():
            try:
                summary_btn.config(state=tk.DISABLED)
                dlg.config(cursor="watch")
                dlg.update_idletasks()
            except tk.TclError:
                pass
            try:
                rewritten = self._generate_analyzed_content_summary_text(
                    video_detail,
                    parent=dlg,
                    source_text=tx.get("1.0", tk.END),
                )
            finally:
                try:
                    summary_btn.config(state=tk.NORMAL)
                    dlg.config(cursor="")
                except tk.TclError:
                    pass
            if not rewritten:
                return
            tx.delete("1.0", tk.END)
            tx.insert("1.0", rewritten)
            video_detail["analyzed_content"] = rewritten
            _copy_text_to_clipboard(dlg, rewritten)
            if not persist(video_detail, parent=dlg):
                return
            if callable(on_content_summarized):
                on_content_summarized()

        if enable_content_summary:
            summary_btn = ttk.Button(
                btn_row, text="内容概括", command=on_content_summary
            )
            summary_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="保存", command=on_confirm).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.wait_window()
        return result_holder[0]

    def _show_poem_editor(
        self,
        parent,
        video_detail: dict,
        *,
        on_saved=None,
        persist_fn=None,
    ) -> str | None:
        """编辑 ``video_detail['poem']``（纯文本）；确认后写回频道列表。"""
        persist = persist_fn or (
            lambda vd, parent=None: self._persist_video_detail_story(vd, parent=parent)
        )
        result_holder: list[str | None] = [None]
        dlg = tk.Toplevel(parent)
        dlg.title("诗歌 / Poem")
        dlg.geometry("820x580")
        dlg.minsize(560, 400)
        dlg.transient(parent)
        dlg.grab_set()
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"820x580+{(sw - 820) // 2}+{(sh - 580) // 2}")

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        ttk.Label(
            frm,
            text=(
                f"{title}\n"
                "诗歌 poem（可编辑；双击编辑区可用剪贴板内容替换全文；"
                "保存后写回本条并保存频道列表）"
            ),
            wraplength=760,
        ).pack(anchor=tk.W, pady=(0, 8))

        tx = scrolledtext.ScrolledText(
            frm, wrap=tk.WORD, width=90, height=24, font=("Arial", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        initial = video_detail.get("poem")
        if initial:
            tx.insert("1.0", initial)
            _copy_text_to_clipboard(dlg, initial)
        _bind_text_editor_replace_from_clipboard_on_double_click(tx, dlg)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X)

        def on_confirm():
            new_text = (tx.get("1.0", tk.END) or "").strip()
            if new_text:
                video_detail["poem"] = new_text
            else:
                video_detail.pop("poem", None)
            if not persist(video_detail, parent=dlg):
                return
            result_holder[0] = new_text
            dlg.destroy()
            if callable(on_saved):
                on_saved()

        ttk.Button(btn_row, text="保存", command=on_confirm).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.wait_window()
        return result_holder[0]

    def _copy_notebooklm_story_gen_instruction(
        self,
        *,
        parent,
        video_detail: dict,
        story_raw: str,
        nb_mode: str,
        main_character: str = "",
        channel_path: str = "",
        cycle_holder: dict | None = None,
    ) -> bool:
        """Story JSON → NotebookLM slideshow / video 指令（不含 Story 生成提示）。

        ``cycle_holder`` 非空时按按钮循环拷贝：全部 array → 第 1 条 → … → 第 N 条 → 再回到全部。
        Slideshow / Video 各自独立计数。
        """
        entries = _parse_story_field(story_raw)
        if not entries:
            messagebox.showwarning(
                "无 Story",
                "请先在编辑区填写有效的 story（JSON 数组首条或纯文本）。",
                parent=parent,
            )
            return False

        status_msg = ""
        if cycle_holder is not None:
            idx = cycle_holder.get(nb_mode, -1)
            if idx < 0:
                scene_content = entries
                status_msg = f"已拷贝全部 {len(entries)} 条 story"
                cycle_holder[nb_mode] = 0
            else:
                scene_content = [entries[idx]]
                status_msg = (
                    f"已拷贝第 {idx + 1} 条 story（共 {len(entries)} 条）"
                )
                next_idx = idx + 1
                cycle_holder[nb_mode] = -1 if next_idx >= len(entries) else next_idx
        else:
            scene_content = [entries[0]]

        clip_body = config_prompt.build_notebooklm_gen_instruction_clipbody(
            mode=nb_mode,
            video_detail=video_detail,
            scene_content=scene_content,
            visual_style=project_manager.LAST_VISUAL_STYLE,
            main_character=(main_character or "").strip(),
            host_narrator=(project_manager.LAST_NARRATOR or "").strip(),
            host_display=project_manager.LAST_HOST_DISPLAY,
        )

        _copy_text_to_clipboard(parent, clip_body)
        if clip_body and (channel_path or "").strip():
            channel_clipboard_append_item(channel_path, clip_body, nb_mode)
        if status_msg:
            show_auto_close_popup(parent, f"Story to {nb_mode}", status_msg)
        return bool(clip_body)


    def _copy_image_prompt_instruction(
        self,
        *,
        parent,
        video_detail: dict,
        story_raw: str,
        main_character: str = "",
        channel_path: str = "",
    ) -> bool:
        """选择 Direct Video 指令模板并复制到剪贴板（单图 → 视频）。"""
        choices = config_prompt.DIRECT_VIDEO_PROMPT_CHOICES
        if not choices:
            show_auto_close_popup(
                parent, "Image Prompt", "未配置 image prompt 提示词。", kind="error"
            )
            return False

        pick_labels = [lbl for lbl, _ in choices]
        picked = askchoice("Image Prompt", pick_labels, parent=parent)
        if not picked:
            return False
        picked_label = picked[1] if isinstance(picked, (tuple, list)) else picked

        template = ""
        for lbl, tpl in choices:
            if lbl == picked_label:
                template = tpl
                break
        if not (template or "").strip():
            return False

        entries = _parse_story_field(story_raw)
        clip_body = config_prompt.build_direct_video_clipbody(
            instruction=template,
            story_entries=entries,
            main_character=(main_character or "").strip(),
            visual_style=project_manager.LAST_VISUAL_STYLE,
        )
        _copy_text_to_clipboard(parent, clip_body)
        if clip_body and (channel_path or "").strip():
            channel_clipboard_append_item(
                channel_path, clip_body, "direct_video_instruction"
            )
        show_auto_close_popup(parent, "Image Prompt", f"已拷贝到剪贴板：{picked_label}")
        return bool(clip_body)

    def _run_story_scene_split_from_cover_async(
        self,
        parent,
        video_detail: dict,
        story_raw: str,
        *,
        on_busy=None,
        on_idle=None,
        persist_fn=None,
        on_saved=None,
    ) -> bool:
        """用封面图 + story 首条 JSON，LLM 拆分为多条 scene_content。"""
        entries = _parse_story_field(story_raw)
        if not entries:
            messagebox.showwarning(
                "场景分离",
                "请先在 story 编辑区填写至少一条有效 JSON。",
                parent=parent,
            )
            return False

        webp_path = _find_gen_video_webp_for_row(video_detail)
        if not webp_path:
            show_auto_close_popup(
                parent,
                "场景分离",
                "未找到 gen_video/<id>.webp 封面。\n请先拖入/粘贴图片并保存封面。",
                kind="error",
            )
            return False

        first_entry = entries[0]
        lang = config.llm_language_label(self.language)
        system_prompt = config_prompt.STORY_SCENE_SPLIT_FROM_IMAGE_SYSTEM_PROMPT.format(
            language=lang
        )
        user_prompt = json.dumps(first_entry, ensure_ascii=False, indent=2)

        if on_busy:
            on_busy()

        def work():
            err_msg = ""
            scenes: list | None = None
            try:
                raw = self.llm_api.analyze_image_json(
                    system_prompt,
                    webp_path,
                    expect_list=True,
                    user_prompt=user_prompt,
                )
                scenes = raw if isinstance(raw, list) and raw else None
            except Exception as ex:
                err_msg = str(ex)

            def apply():
                if on_idle:
                    on_idle()
                if err_msg:
                    show_auto_close_popup(
                        parent, "场景分离失败", err_msg, kind="error"
                    )
                    return
                if not scenes:
                    messagebox.showwarning(
                        "场景分离",
                        "LLM 未返回有效 scene_content（须为 JSON array）。",
                        parent=parent,
                    )
                    return
                video_detail["scene_content"] = scenes
                persist = persist_fn or (
                    lambda vd, parent=None: self._persist_video_detail_story(
                        vd, parent=parent
                    )
                )
                if not persist(video_detail, parent=parent):
                    return
                scene_json = json.dumps(scenes, ensure_ascii=False, indent=2)
                try:
                    _copy_text_to_clipboard(parent, scene_json)
                except Exception:
                    pass
                if callable(on_saved):
                    try:
                        on_saved()
                    except Exception:
                        pass
                show_auto_close_popup(
                    parent,
                    "场景分离",
                    f"已根据封面与 story 首条生成 {len(scenes)} 个场景，并写入 scene_content。",
                )

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()
        return True

    def _copy_notebooklm_scene_gen_instruction(
        self,
        *,
        parent,
        video_detail: dict,
        scene_content: list,
        nb_mode: str,
        main_character: str = "",
        channel_path: str = "",
    ) -> bool:
        """复制 NotebookLM slideshow / video 生成指令到剪贴板（并追加到频道剪贴板）。"""
        if not scene_content:
            messagebox.showwarning(
                "无 Scene JSON",
                "无有效 scene_content，请先填写 Scene JSON 数组。",
                parent=parent,
            )
            return False
        host_str = project_manager.LAST_NARRATOR
        clip_body = config_prompt.build_notebooklm_gen_instruction_clipbody(
            mode=nb_mode,
            video_detail=video_detail,
            scene_content=scene_content,
            visual_style=project_manager.LAST_VISUAL_STYLE,
            main_character=(main_character or "").strip(),
            host_narrator=(host_str or "").strip(),
            host_display=project_manager.LAST_HOST_DISPLAY,
        )
        clip_tag = (
            "gen_slideshow_instruction"
            if nb_mode == "slideshow"
            else "gen_video_instruction"
        )
        _copy_text_to_clipboard(parent, clip_body)
        if clip_body and (channel_path or "").strip():
            channel_clipboard_append_item(channel_path, clip_body, clip_tag)
        return bool(clip_body)

    def _show_scene_content_editor(
        self,
        parent,
        video_detail: dict,
        *,
        on_saved=None,
        main_character: str = "",
        channel_path: str = "",
        persist_fn=None,
    ) -> list | None:
        """编辑 ``video_detail['scene_content']``（JSON array）；确认后写回频道列表。"""
        persist = persist_fn or (
            lambda vd, parent=None: self._persist_video_detail_story(vd, parent=parent)
        )
        result_holder: list[list | None] = [None]
        dlg = tk.Toplevel(parent)
        dlg.title("场景内容 / Scene")
        dlg.geometry("920x820")
        dlg.minsize(640, 560)
        dlg.transient(parent)
        dlg.grab_set()
        dlg.update_idletasks()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"920x820+{(sw - 920) // 2}+{(sh - 820) // 2}")

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        ttk.Label(
            frm,
            text=(
                f"{title}\n"
                "选 LM 提示；导向说明填入 {instruction}；切换/编辑时预览并复制到剪贴板。"
                "「智能生成」用所选提示词生成 scene_content 并自动保存。"
                "下方 JSON 区可手工编辑；保存时须为有效 JSON 数组。"
            ),
            wraplength=860,
        ).pack(anchor=tk.W, pady=(0, 8))

        channel_key = self._channel_config_key()
        nb_prompt_choices = _scenes_prompt_choices(channel_key)
        prompt_row = ttk.Frame(frm)
        prompt_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(prompt_row, text="选LM提示").pack(side=tk.LEFT, padx=(0, 5))
        default_prompt_label = _default_scene_editor_prompt_label(
            video_detail, channel_key
        )
        prompt_combo_var = tk.StringVar(value=default_prompt_label)
        prompt_combo = ttk.Combobox(
            prompt_row,
            textvariable=prompt_combo_var,
            values=[opt[0] for opt in nb_prompt_choices],
            state="readonly" if nb_prompt_choices else "disabled",
            width=18,
        )
        prompt_combo.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(frm, text="导向说明（{instruction}，可选）：").pack(
            anchor=tk.W, pady=(0, 2)
        )
        instruction_frm = ttk.Frame(frm)
        instruction_frm.pack(fill=tk.X, pady=(0, 8))
        instruction_tx = scrolledtext.ScrolledText(
            instruction_frm, wrap=tk.WORD, width=100, height=3, font=("Arial", 9)
        )
        instruction_tx.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(frm, text="提示词预览（切换选项/编辑导向说明时更新并复制到剪贴板）：").pack(
            anchor=tk.W, pady=(0, 2)
        )
        prompt_tx = scrolledtext.ScrolledText(
            frm, wrap=tk.WORD, width=100, height=8, font=("Arial", 9)
        )
        prompt_tx.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(frm, text="scene_content（JSON 数组）：").pack(anchor=tk.W, pady=(0, 2))
        tx = scrolledtext.ScrolledText(
            frm, wrap=tk.WORD, width=100, height=20, font=("Consolas", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        scenes = video_detail.get("scene_content") or []
        if not isinstance(scenes, list):
            scenes = []
        scene_json = ""
        if scenes:
            scene_json = json.dumps(scenes, ensure_ascii=False, indent=2)
            tx.insert("1.0", scene_json)
        _bind_text_editor_replace_from_clipboard_on_double_click(tx, dlg)

        def refresh_scene_prompt(*_args):
            sel = (prompt_combo_var.get() or "").strip()
            if not sel or not nb_prompt_choices:
                prompt_tx.delete("1.0", tk.END)
                return
            instr = (instruction_tx.get("1.0", tk.END) or "").strip()
            _, prompt = self._notebooklm_prompt_text_for_label(
                video_detail, sel, instruction=instr
            )
            prompt_tx.delete("1.0", tk.END)
            if prompt:
                prompt_tx.insert("1.0", prompt)
                _copy_text_to_clipboard(dlg, prompt)

        _build_instruction_snippet_combo(
            instruction_frm, channel_key, instruction_tx, on_changed=refresh_scene_prompt
        )

        if nb_prompt_choices:
            prompt_combo.bind("<<ComboboxSelected>>", refresh_scene_prompt)
        instruction_tx.bind("<FocusOut>", refresh_scene_prompt)
        if nb_prompt_choices:
            refresh_scene_prompt()

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X)

        def _scene_list_from_editor() -> list | None:
            raw = (tx.get("1.0", tk.END) or "").strip()
            if not raw:
                return None
            try:
                parsed = json.loads(safe_clipboard_json_copy(raw))
            except (json.JSONDecodeError, TypeError):
                return None
            if not isinstance(parsed, list):
                return None
            return parsed if parsed else None

        _lang_lbl = config.llm_language_label(self.language)

        def _busy(btn):
            try:
                btn.config(state=tk.DISABLED)
                dlg.config(cursor="watch")
                dlg.update_idletasks()
            except tk.TclError:
                pass

        def _idle(btn):
            try:
                btn.config(state=tk.NORMAL)
                dlg.config(cursor="")
            except tk.TclError:
                pass

        def on_smart_generate():
            self._run_scene_smart_generate_async(
                dlg,
                video_detail,
                (prompt_combo_var.get() or "").strip(),
                lambda merged: (tx.delete("1.0", tk.END), tx.insert("1.0", merged)),
                get_instruction=lambda: (instruction_tx.get("1.0", tk.END) or ""),
                on_busy=lambda: _busy(smart_btn),
                on_idle=lambda: _idle(smart_btn),
                persist_fn=persist,
                on_saved=on_saved,
            )

        def on_copy_slideshow_instruction():
            scenes = _scene_list_from_editor()
            if scenes is None:
                messagebox.showwarning(
                    "无 Scene JSON",
                    "请先在编辑区填写有效的 scene_content JSON 数组。",
                    parent=dlg,
                )
                return
            self._copy_notebooklm_scene_gen_instruction(
                parent=dlg,
                video_detail=video_detail,
                scene_content=scenes,
                nb_mode="slideshow",
                main_character=main_character,
                channel_path=channel_path,
            )

        def on_copy_video_instruction():
            scenes = _scene_list_from_editor()
            if scenes is None:
                messagebox.showwarning(
                    "无 Scene JSON",
                    "请先在编辑区填写有效的 scene_content JSON 数组。",
                    parent=dlg,
                )
                return
            self._copy_notebooklm_scene_gen_instruction(
                parent=dlg,
                video_detail=video_detail,
                scene_content=scenes,
                nb_mode="video",
                main_character=main_character,
                channel_path=channel_path,
            )

        def on_confirm():
            raw = (tx.get("1.0", tk.END) or "").strip()
            if not raw:
                if not messagebox.askyesno(
                    "清空场景",
                    "内容为空，将删除本条 scene_content。继续？",
                    parent=dlg,
                ):
                    return
                video_detail.pop("scene_content", None)
                result_holder[0] = []
            else:
                try:
                    parsed = json.loads(safe_clipboard_json_copy(raw))
                except (json.JSONDecodeError, TypeError) as e:
                    show_auto_close_popup(
                        dlg,
                        "JSON 无效",
                        f"无法解析 scene_content：\n{e}",
                        kind="error",
                    )
                    return
                if not isinstance(parsed, list):
                    show_auto_close_popup(
                        dlg,
                        "JSON 无效",
                        "scene_content 必须是 JSON 数组（以 [ 开头的 list）。",
                        kind="error",
                    )
                    return
                if not parsed:
                    messagebox.showwarning(
                        "无效场景",
                        "解析后无有效场景条目，请检查 JSON 结构。",
                        parent=dlg,
                    )
                    return
                video_detail["scene_content"] = parsed
                result_holder[0] = parsed
            if not persist(video_detail, parent=dlg):
                return
            dlg.destroy()
            if callable(on_saved):
                on_saved()

        smart_btn = ttk.Button(btn_row, text="智能生成", command=on_smart_generate)
        smart_btn.pack(side=tk.LEFT, padx=(0, 8))
        if not nb_prompt_choices:
            smart_btn.config(state=tk.DISABLED)
        ttk.Button(
            btn_row,
            text=f"Slideshow 指令 ({_lang_lbl})",
            command=on_copy_slideshow_instruction,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            btn_row,
            text=f"Video 指令 ({_lang_lbl})",
            command=on_copy_video_instruction,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="保存", command=on_confirm).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.wait_window()
        return result_holder[0]

    def open_content_field_editor(
        self,
        parent,
        video_detail: dict,
        field: str,
        *,
        persist_fn=None,
        on_saved=None,
        on_content_summarized=None,
        on_story_title_updated=None,
        main_character: str = "",
        channel_path: str = "",
    ):
        """统一入口：story / analyzed_content / scene_content 编辑（与摘要窗按钮相同）。"""
        if field == "story":
            return self._show_video_story_editor(
                parent,
                video_detail,
                allow_empty=True,
                persist_fn=persist_fn,
                on_title_updated=on_story_title_updated,
                main_character=main_character,
                channel_path=channel_path or self.channel_path or "",
            )
        if field == "analyzed_content":
            return self._show_analyzed_content_editor(
                parent,
                video_detail,
                on_saved=on_saved,
                on_content_summarized=on_content_summarized,
                persist_fn=persist_fn,
            )
        if field == "scene_content":
            return self._show_scene_content_editor(
                parent,
                video_detail,
                on_saved=on_saved,
                main_character=main_character,
                channel_path=channel_path or self.channel_path or "",
                persist_fn=persist_fn,
            )
        if field == "poem":
            return self._show_poem_editor(
                parent,
                video_detail,
                on_saved=on_saved,
                persist_fn=persist_fn,
            )
        messagebox.showwarning("错误", f"未知字段：{field}", parent=parent)
        return None

    def _show_transcript_script_viewer(self, parent, video_detail: dict) -> None:
        """只读展示转录原文（来自 transcribed_file，不可保存回列表）。"""
        body = (config.read_transcript_text_from_video_detail(video_detail) or "").strip()
        tf = (video_detail.get("transcribed_file") or "").strip()
        if not body:
            hint = f"\n\n文件：{tf}" if tf else ""
            messagebox.showwarning(
                "转录脚本",
                f"无转录原文。请先下载并完成转录。{hint}",
                parent=parent,
            )
            return

        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        top = tk.Toplevel(parent)
        top.title("转录脚本 / Script")
        top.minsize(560, 400)
        top.transient(parent)
        top.grab_set()

        hdr = ttk.Frame(top, padding=(12, 10, 12, 0))
        hdr.pack(fill=tk.X)
        ttk.Label(
            hdr,
            text="转录原文（只读，来自 transcribed_file；不可在此保存）",
            font=("Arial", 10),
        ).pack(anchor=tk.W)
        ttk.Label(hdr, text=title, wraplength=860, font=("Arial", 11, "bold")).pack(
            anchor=tk.W, pady=(4, 2)
        )
        if tf:
            ttk.Label(hdr, text=tf, wraplength=860, font=("Arial", 9)).pack(
                anchor=tk.W, pady=(0, 8)
            )

        tx = scrolledtext.ScrolledText(
            top, wrap=tk.WORD, width=100, height=30, font=("Consolas", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        tx.insert("1.0", body)
        tx.configure(state=tk.DISABLED)
        _copy_text_to_clipboard(top, body)

        bf = ttk.Frame(top, padding=(12, 0, 12, 12))
        bf.pack(fill=tk.X)

        def _copy():
            _copy_text_to_clipboard(top, body)

        ttk.Button(bf, text="复制全文", command=_copy).pack(side=tk.LEFT)
        ttk.Button(bf, text="关闭", command=top.destroy).pack(side=tk.RIGHT)

        w, h = 900, 640
        top.update_idletasks()
        x = max(0, (top.winfo_screenwidth() - w) // 2)
        y = max(0, (top.winfo_screenheight() - h) // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.protocol("WM_DELETE_WINDOW", top.destroy)


    def check_video_status(self,video_detail):
        """检查单个视频的下载、转录和摘要状态"""
        status_parts = []
        video_file = None
        audio_file = None
        
        # 使用可重用的方法生成文件名前缀（用于匹配，使用50字符）
        filename_prefix = self.downloader.generate_video_prefix( video_detail )
        
        # 检查是否已下载 - 只扫描 .mp4 文件
        for filename in os.listdir(f"{self.youtube_dir}/media"):
            # 只检查 .mp4 文件
            if not filename_prefix in filename:
                continue
            if filename.lower().endswith('.mp4'):
                video_file = os.path.join(f"{self.youtube_dir}/media", filename)
                video_detail['video_path'] = video_file
            elif filename.lower().endswith('.mp3'):
                audio_file = os.path.join(f"{self.youtube_dir}/media", filename)
                video_detail['audio_path'] = audio_file
            elif filename.lower().endswith('.wav'):
                audio_file = os.path.join(f"{self.youtube_dir}/media", filename)
                a = self.downloader.ffmpeg_audio_processor.to_mp3(audio_file)
                safe_remove(audio_file)
                audio_file = f"{self.youtube_dir}/media/{filename_prefix}.mp3"
                safe_copy_overwrite(a, audio_file)
                video_detail['audio_path'] = audio_file
        
        if video_file and not audio_file:
            a = self.downloader.ffmpeg_audio_processor.extract_audio_from_video(video_file, "mp3")
            audio_file = f"{self.youtube_dir}/media/{filename_prefix}.mp3"
            safe_copy_overwrite(a, audio_file)
            video_detail['audio_path'] = audio_file

        if video_file or audio_file:
            status_parts.append("✅ 已下载")
        else:
            status_parts.append("⬜ 未下载")
        
        # 检查是否已转录 - 检查 .srt 文件（转录生成的字幕文件）
        has_transcript = bool((video_detail.get("transcribed_file") or "").strip())
        if not has_transcript:
            for filename in os.listdir(f"{self.youtube_dir}/media"):
                if filename_prefix in filename and (
                    filename.endswith(".srt")
                    or filename.endswith(".json")
                    or filename.endswith(".txt")
                ):
                    video_detail['transcribed_file'] = os.path.join(f"{self.youtube_dir}/media", filename)
                    has_transcript = True
                    break
        if has_transcript:
            status_parts.append("✅ 已转录")
        else:
            status_parts.append("⬜ 未转录")
        
        
        return " ".join(status_parts), video_file, audio_file


    def get_video_detail(self, row_key):
        """按树 tag（``id`` 或 ``url``）或 ``project_profile.pid`` 查找列表行。"""
        key = (row_key or "").strip()
        if not key:
            return None
        for video in self.downloader.channel_videos:
            if (video.get("url") or "").strip() == key or (video.get("id") or "").strip() == key:
                return video
        for video in self.downloader.channel_videos:
            if _video_detail_project_pid(video) == key:
                return video
        return None


    def match_media_file(self, video_detail, field, postfixs):
        prefix = self.downloader.generate_video_prefix(video_detail)
        for file in os.listdir(f"{self.youtube_dir}/media"):
            if not prefix in file:
                continue
            for postfix in postfixs:
                if file.endswith(postfix):
                    file = os.path.join(f"{self.youtube_dir}/media", file)
                    video_detail[field] = file
                    return video_detail
        return None


    def update_text_content(self, video_detail, transcribed_file=None):
        """确保 ``transcribed_file`` 已绑定；``content`` 仅在迁移到文件后移除。"""
        if not video_detail:
            return None
        if transcribed_file:
            video_detail["transcribed_file"] = transcribed_file
        config.migrate_content_to_transcribed_file(
            video_detail,
            media_dir=_infer_channel_list_item_media_dir(
                video_detail, getattr(self, "channel_path", "") or ""
            ),
        )
        return video_detail

    def _format_analyze_prompt(self, video_detail=None) -> str:
        raw = config_channel.get_channel_analyze_prompt(
            self._channel_config_key(),
            language=self.language,
        )

        url = ""
        if isinstance(video_detail, dict):
            url = (video_detail.get("url") or "").strip()
        lang_label = config.llm_language_label(self.language)
        try:
            return raw.format(url=url, language=lang_label)
        except KeyError:
            return raw

    def generate_analyzed_content_for_video(
        self, video_detail, *, force_rewrite: bool = False
    ) -> bool:
        """用 LLM 从转录/字幕文本生成 ``analyzed_content``（纯文本，当前频道语言）。"""
        if not isinstance(video_detail, dict):
            return False
        if not force_rewrite and video_detail.get("analyzed_content"):
            return True
        text_content = self._analyze_content_source_text(video_detail)
        url = (video_detail.get("url") or "").strip()
        if not text_content and not url:
            return False
        if text_content and len(text_content) < 100 and not url:
            return False
        prompt = self._format_analyze_prompt(video_detail)
        lang_label = config.llm_language_label(self.language)
        user_prompt = text_content if text_content else (f"YouTube URL: {url}" if url else " ")
        rewritten = self.llm_api_local.generate_text(
            prompt.format(url=url, language=lang_label),
            user_prompt,
        )
        rewritten = (rewritten or "").strip()
        if not rewritten:
            return False
        video_detail["analyzed_content"] = rewritten
        return True

    def _generate_analyzed_content_summary_text(
        self,
        video_detail: dict,
        *,
        parent=None,
        source_text: str | None = None,
    ) -> str | None:
        """LLM 内容概括 → ``analyzed_content`` 纯文本（与摘要窗原「内容概括」相同逻辑）。"""
        text_content = self._analyze_content_source_text(
            video_detail, override=source_text
        )
        url = (video_detail.get("url") or "").strip()
        if not text_content and not url:
            messagebox.showwarning(
                "内容概括",
                "无转录原文且无 YouTube 链接，也无法从编辑区取得内容。",
                parent=parent,
            )
            return None
        prompt = self._format_analyze_prompt(video_detail)
        lang_label = config.llm_language_label(self.language)
        user_prompt = text_content if text_content else f"YouTube URL: {url}"
        rewritten = self.llm_api.generate_text(
            prompt.format(language=lang_label, url=url),
            user_prompt,
        )
        rewritten = (rewritten or "").strip()
        if not rewritten:
            messagebox.showwarning(
                "内容概括",
                "LLM 未返回内容。",
                parent=parent,
            )
            return None
        return rewritten


    def show_analyzed_content_popup(self, video_detail: dict, *, parent=None) -> None:
        """弹窗只读展示 ``analyzed_content``。"""
        parent = parent or self.root
        ac = video_detail.get("analyzed_content")
        body = (ac if isinstance(ac, str) else str(ac or "")).strip()
        if not body:
            messagebox.showwarning(
                "分析结果",
                "未生成 analyzed_content 或内容为空。",
                parent=parent,
            )
            return
        title = _youtube_row_display_title(video_detail) or "YouTube 视频"
        top = tk.Toplevel(parent)
        top.title("分析内容 / analyzed content")
        top.minsize(560, 400)
        top.transient(parent)
        top.grab_set()

        hdr = ttk.Frame(top, padding=(12, 10, 12, 0))
        hdr.pack(fill=tk.X)
        ttk.Label(
            hdr,
            text="analyzed_content（只读预览）",
            font=("Arial", 10),
        ).pack(anchor=tk.W)
        ttk.Label(hdr, text=title, wraplength=860, font=("Arial", 11, "bold")).pack(
            anchor=tk.W, pady=(4, 8)
        )

        tx = scrolledtext.ScrolledText(
            top, wrap=tk.WORD, width=100, height=30, font=("Consolas", 10)
        )
        tx.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        tx.insert("1.0", body)
        tx.configure(state=tk.DISABLED)

        bf = ttk.Frame(top, padding=(12, 0, 12, 12))
        bf.pack(fill=tk.X)

        def _copy():
            try:
                top.clipboard_clear()
                top.clipboard_append(body)
                top.update()
            except tk.TclError:
                pass

        ttk.Button(bf, text="复制全文", command=_copy).pack(side=tk.LEFT)
        ttk.Button(bf, text="关闭", command=top.destroy).pack(side=tk.RIGHT)

        w, h = 900, 640
        top.update_idletasks()
        sw = top.winfo_screenwidth()
        sh = top.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        try:
            top.deiconify()
            top.lift()
            top.focus_force()
            top.attributes("-topmost", True)
            top.after(200, lambda: top.attributes("-topmost", False))
        except tk.TclError:
            pass
        try:
            top.grab_set()
        except tk.TclError:
            pass
        top.protocol("WM_DELETE_WINDOW", top.destroy)

    def _bind_yt_text_download_channel_list(self) -> None:
        """按 ``YT_text_download.json`` 绑定当前欢迎屏频道的 list JSON（不再弹窗选频道文件）。"""
        ch_id = config_channel.get_channel_id(self.channel)
        list_path = config.yt_text_download_list_json_path(ch_id)
        os.makedirs(os.path.dirname(list_path), exist_ok=True)
        self.downloader.channel_list_json = list_path
        self.downloader.channel_videos = []
        self.downloader.latest_date = datetime.now()
        if os.path.isfile(list_path):
            try:
                with open(list_path, "r", encoding="utf-8") as f:
                    self.downloader.channel_videos = json.load(f)
                if not isinstance(self.downloader.channel_videos, list):
                    self.downloader.channel_videos = []
                else:
                    _normalize_channel_videos_for_storage(
                        self.downloader.channel_videos, self.channel_path or ""
                    )
                    dates = [
                        datetime.strptime(v["upload_date"], "%Y%m%d")
                        for v in self.downloader.channel_videos
                        if isinstance(v, dict) and v.get("upload_date")
                    ]
                    if dates:
                        self.downloader.latest_date = max(dates)
            except Exception as e:
                print(f"❌ 读取视频列表失败: {e}")
                self.downloader.channel_videos = []
        print(f"✅ YT 文字下载列表: {list_path}")


    def prepare_category_for_content(self, video_detail, topic_choices):
        valid_content = video_detail.get("analyzed_content")
        if not valid_content:
            valid_content = config.read_transcript_text_from_video_detail(video_detail)

        # LLM API 调用在信号量保护下（已在上层 with 语句中）
        result = self.llm_api_local.generate_json(
            config_prompt.GET_TOPIC_TYPES_COUNSELING_STORY_SYSTEM_PROMPT.format(language='Chinese', topic_choices=topic_choices), 
            valid_content,
            expect_list=False
        )
        if result:
            if result.get('topic_subtype', '') and result.get('topic_subtype', '').strip():
                video_detail['topic_subtype'] = result.get('topic_subtype', '')
                video_detail.pop('topic_type', None)
            if result.get('topic_category', '') and result.get('topic_category', '').strip():
                video_detail['topic_category'] = result.get('topic_category', '')
            raw_tags = result.get('tags')
            if isinstance(raw_tags, list):
                tags_list = [str(t).strip() for t in raw_tags if t and str(t).strip()]
                if tags_list:
                    video_detail['tags'] = tags_list
            elif isinstance(raw_tags, str) and raw_tags.strip():
                video_detail["tags"] = parse_tags_list(raw_tags)
            # 保存到文件（在锁内，确保数据一致性）
            try:
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                dn = _youtube_row_display_title(video_detail)
                print(f"✅ 摘要生成完成并已保存: {dn[:50] or 'Unknown'}")
            except Exception as e:
                print(f"❌ 保存 channel_list_json 失败: {e}")


    def _open_publish_video_dialog(
        self,
        parent,
        title_prefix: str,
        mp4_path: str,
        video_detail: dict,
        refresh_tree,
        *,
        review_script_text: str = "",
    ):
        """从 INPUT_MEDIA_PATH 匹配的成品 mp4 上传；顺序与 GUI_wf.publish_video 相同（先标题/描述，再定时）。"""
        ch_key = os.path.basename(self.channel_path)
        cfg = config_channel.get_channel_config(ch_key)
        if not cfg:
            show_auto_close_popup(parent, "错误", "未找到频道配置", kind="error")
            return
        if not mp4_path or not os.path.isfile(mp4_path):
            messagebox.showwarning("提示", f"未找到 mp4 文件：\n{mp4_path}", parent=parent)
            return

        story_text = project_manager.story_field_flat_text(
            video_detail.get("story") if isinstance(video_detail, dict) else ""
        )
        poem_text = (
            (video_detail.get("poem") or "").strip()
            if isinstance(video_detail, dict)
            else ""
        )
        flow = ask_publish_metadata_then_schedule(
            parent,
            language=self.language,
            default_title=self._youtube_story_title_from_video_detail(video_detail),
            scene_content_list=scene_content_list_for_publish(
                language=self.language,
                video_detail=video_detail if isinstance(video_detail, dict) else None,
            ),
            analyzed_content = video_detail.get("analyzed_content"),
            story_text=story_text,
            poem_text=poem_text,
            review_script_text=review_script_text,
            video_detail=video_detail if isinstance(video_detail, dict) else None,
            generate_text_fn=self.llm_api_local.generate_text,
            schedule_dialog_fn=ask_publish_schedule_dialog,
            mp4_path_hint=mp4_path,
            metadata_dialog_title="发布前 — 标题与描述",
            schedule_dialog_title="发布成品视频到 YouTube",
        )
        if flow is None:
            return

        title = flow["title"]
        summary = flow["description"]
        publish_at = flow["publish_at"]
        disp_name = title_prefix + config.chinese_convert(
            title.strip().replace(" ", "_").replace("\n", "_"), self.language
        )

        root_win = self.root

        def worker():
            watch = ""
            try:
                _run_on_main_tk_and_wait(
                    root_win,
                    lambda: _set_publish_review_publishing(parent, True),
                    timeout=10,
                )
                vid, published_iso = self.downloader.upload_video(
                    mp4_path,
                    None,
                    disp_name,
                    summary,
                    self.language,
                    None,
                    cfg["channel_key"],
                    cfg.get("channel_id") or ch_key,
                    cfg["channel_category_id"],
                    [],
                    privacy="unlisted",
                    publish_at=publish_at,
                )
                if publish_at is not None:
                    pub_str = publish_at.strftime("%Y-%m-%d %H:%M")
                else:
                    pub_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                video_detail["publish"] = pub_str
                _apply_publish_create_date(
                    video_detail,
                    publish_at=publish_at,
                    published_iso=published_iso or "",
                )
                vid_s = str(vid).strip() if vid is not None else ""
                if vid_s:
                    watch = f"https://www.youtube.com/watch?v={vid_s}"
                    video_detail["url"] = watch
                with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)

                tg_lines = []
                try:
                    from utility.telegram_notify import notify_youtube_publish_extras

                    tg_lines = notify_youtube_publish_extras(
                        mp4_path=mp4_path,
                        watch_url=watch or "",
                        title_line=disp_name,
                        summary=summary,
                    )
                except Exception as _tg_e:
                    tg_lines = [f"Telegram（旁路异常）: {_tg_e}"]

                # 审阅窗口若正在播放同一 mp4，先主线程释放句柄，否则归档 move/copy 易 WinError 32
                try:
                    _run_on_main_tk_and_wait(
                        self.root,
                        lambda: _release_publish_review_if_same_mp4(parent, mp4_path),
                        timeout=25,
                    )
                except Exception:
                    pass

                archive_msg = _move_published_input_media_files(mp4_path, video_detail)

                def ok_ui():
                    _set_publish_review_publishing(parent, False)
                    try:
                        refresh_tree()
                    except Exception:
                        pass
                    msg = f"已上传，YouTube 视频 ID: {vid}"
                    if watch:
                        msg = f"{msg}\n{watch}"
                    if archive_msg:
                        msg = f"{msg}\n\n{archive_msg}"
                    if tg_lines:
                        msg = f"{msg}\n\n--- Telegram ---\n" + "\n".join(tg_lines)
                    par = _tk_dialog_parent(parent, root_win)
                    show_auto_close_popup(par, "成功", msg)

                root_win.after(0, ok_ui)
            except Exception as e:
                err = str(e)

                def err_ui():
                    _set_publish_review_publishing(parent, False)
                    par = _tk_dialog_parent(parent, root_win)
                    show_auto_close_popup(par, "上传失败", err, kind="error")

                root_win.after(0, err_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _open_publish_review_dialog(self, parent, mp4_path: str, video_detail: dict, on_refresh):
        """打开成品审阅窗口（预览、转写、重合成、发布）。"""
        from gui.publish_review_dialog import PublishReviewDialog

        PublishReviewDialog(
            parent,
            mp4_path,
            video_detail,
            self,
            getattr(self, "workflow_gui", None),
            on_refresh,
        )

    def _show_channel_videos_dialog(self):
        # 创建视频管理对话框
        dialog = tk.Toplevel(self.root)
        dialog.title(f"热门视频管理 - {self.downloader.channel_name}")
        dialog.geometry("2100x1150")
        dialog.transient(self.root)
        
        # 顶部信息和控制栏
        top_frame = ttk.Frame(dialog)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 第一行：信息标签和刷新按钮
        info_frame = ttk.Frame(top_frame)
        info_frame.pack(fill=tk.X, pady=(0, 5))
        
        info_text = f"频道: {self.downloader.channel_name} | 共 {len(self.downloader.channel_videos)} 个视频"
        info_label = ttk.Label(info_frame, text=info_text, font=("Arial", 12, "bold"))
        info_label.pack(side=tk.LEFT)
        
        #for video in self.downloader.channel_videos:
        #    video.pop('component_tags', None)
        #       transcribed_file = video.get('transcribed_file', '')
        #    if transcribed_file:
        #        content = config.fetch_text_from_json(transcribed_file)
        #        # if content is None or empty, then remove this video from self.downloader.channel_videos
        #        if content:
        #            video['content'] = content
        #        else:
        #            self.downloader.channel_videos.remove(video)
        #
        #with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
        #    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
        
        def _reload_channel_list_from_disk() -> None:
            path = (self.downloader.channel_list_json or "").strip()
            if not path or not os.path.isfile(path):
                return
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, OSError):
                return
            if not isinstance(loaded, list):
                return
            _normalize_channel_videos_for_storage(loaded, self.channel_path or "")
            self.downloader.channel_videos = loaded

        # 添加刷新按钮（从磁盘重载列表，避免与 JSON 不同步）
        ttk.Button(
            info_frame,
            text="🔄 刷新",
            command=lambda: (_reload_channel_list_from_disk(), populate_tree()),
        ).pack(side=tk.RIGHT, padx=5)
        
        # 第二行：过滤和排序控制
        control_frame = ttk.Frame(top_frame)
        control_frame.pack(fill=tk.X)
        
        # 最小观看次数过滤
        ttk.Label(control_frame, text="最小观看次数:").pack(side=tk.LEFT, padx=(0, 5))
        min_view_var = tk.StringVar(value="0")
        min_view_entry = ttk.Entry(control_frame, textvariable=min_view_var, width=15)
        min_view_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # 排序方式
        sort_mode_var = tk.StringVar(value="hot_degree")  # 默认按热度排序
        
        def toggle_sort():
            """切换排序方式"""
            current_mode = sort_mode_var.get()
            if current_mode == "hot_degree":
                sort_mode_var.set("view_count")
                sort_button.config(text="排序: 观看次数 ↓")
            elif current_mode == "view_count":
                sort_mode_var.set("upload_date")
                sort_button.config(text="排序: 上传日期 ↓")
            elif current_mode == "upload_date":
                sort_mode_var.set("duration")
                sort_button.config(text="排序: 时长 ↓")
            else:  # duration
                sort_mode_var.set("hot_degree")
                sort_button.config(text="排序: 热度 ↓")
            populate_tree()
        
        sort_button = ttk.Button(control_frame, text="排序: 热度 ↓", command=toggle_sort)
        sort_button.pack(side=tk.LEFT, padx=5)
        
        # 绑定回车键自动应用过滤
        min_view_entry.bind('<Return>', lambda e: populate_tree())
        
        # Smart Select 功能
        ttk.Label(control_frame, text="智能选择:").pack(side=tk.LEFT, padx=(10, 5))
        smart_select_var = tk.StringVar()
        smart_select_entry = ttk.Entry(control_frame, textvariable=smart_select_var, width=20)
        smart_select_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        # 添加主题类型选择
        # 从 self.topic_choices 中提取 topic_category 字段并去重
        
        topic_category_var = tk.StringVar()
        topic_category_combo = ttk.Combobox(control_frame, textvariable=topic_category_var, values=self.topic_categories, state="readonly", width=20)
        topic_category_combo.pack(side=tk.LEFT, padx=(0, 5))
        
        # 绑定选择事件，将选中的值保存到 self.main_topic_category
        def on_topic_category_selected(event=None):
            selected_value = topic_category_var.get()
            if selected_value:
                self.main_topic_category = selected_value
        
        topic_category_combo.bind('<<ComboboxSelected>>', on_topic_category_selected)
        
        # 关联视频 ID（| 分隔，与摘要窗口「标注」同一字段；双向关联由「找类似案例」写入）
        ttk.Label(control_frame, text="关联ID:").pack(side=tk.LEFT, padx=(10, 5))
        batch_related_var = tk.StringVar(value="")
        batch_related_entry = ttk.Entry(control_frame, textvariable=batch_related_var, width=26)
        batch_related_entry.pack(side=tk.LEFT, padx=(0, 4))

        def on_apply_related_batch():
            val = (batch_related_var.get() or "").strip()
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请先选择要设置关联 ID 的视频", parent=dialog)
                return
            selected_urls = set()
            for item in selected_items:
                item_tags = _treeview_item_tags_safe(tree, item)
                if item_tags:
                    url = item_tags[0]
                    selected_urls.add(url)
                    vd = self.get_video_detail(url)
                    if vd:
                        vd["status"] = val
            with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            populate_tree()
            for item in tree.get_children():
                item_tags = _treeview_item_tags_safe(tree, item)
                if item_tags and item_tags[0] in selected_urls:
                    tree.selection_add(item)

        ttk.Button(control_frame, text="应用到选中", command=on_apply_related_batch).pack(side=tk.LEFT, padx=(0, 5))

        # 画面风格：与欢迎屏一致，只读展示（LAST_VISUAL_STYLE）
        ttk.Label(control_frame, text="画面风格:").pack(side=tk.LEFT, padx=(10, 5))
        ttk.Label(control_frame, text=project_manager.LAST_VISUAL_STYLE, width=22, anchor="w").pack(side=tk.LEFT, padx=(0, 5))


        def smart_select():
            """根据输入文本智能选择匹配的视频（在 title 和 content 中搜索关键字）"""
            search_text = smart_select_var.get().strip().lower()
            if not search_text:
                return
            
            tree.selection_remove(*tree.selection())
            
            # 在 title 和 content 中搜索关键字，匹配则选中
            matched_count = 0
            for item in tree.get_children():
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                url = item_tags[0]
                video_detail = self.get_video_detail(url)
                if not video_detail:
                    continue
                title = (
                    _youtube_row_source_title(video_detail)
                    + " "
                    + _youtube_row_project_title(video_detail)
                ).lower()

                transcript = config.read_transcript_text_from_video_detail(video_detail) or ""
                analyzed = video_detail.get("analyzed_content")
                content = (transcript + "\n" + analyzed).strip().lower()
                content = content.strip().lower()
                if search_text in title or search_text in content:
                    tree.selection_add(item)
                    matched_count += 1
            
            selected = tree.selection()
            stats_label.config(text=f"已选择: {len(selected)} 个视频")
            
            if matched_count > 0:
                first_matched = None
                for item in tree.get_children():
                    if item in tree.selection():
                        first_matched = item
                        break
                if first_matched:
                    tree.see(first_matched)
                    tree.focus(first_matched)
            
        # 绑定回车键
        smart_select_entry.bind('<Return>', lambda e: smart_select())

        ttk.Label(
            dialog,
            text=(
                "「分析/场景/成片」列：✓=已摘要  ⚠=场景未齐  「片」=gen_video 下已有本条成片 "
                "（成片 ``<id>.mp4``；封面 ``<id>.webp``，``id`` 为 YouTube 视频 id 或项目 pid）；"
                "摘要窗可拖放或 Ctrl+V 粘贴 mp4 / 图片（mp4 将打开审阅窗裁剪排序后拼接加水印）；"
                "拖放 mp4 后自动刷新，也可点顶部「刷新」。"
            ),
            font=("Arial", 9),
            foreground="#333",
            wraplength=1980,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 2))
        
        # 创建Treeview显示视频列表
        columns = ("title", "views", "duration", "upload_date", "status", "analyzed", "topic_category", "topic_subtype", "tags", "mark")
        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", 
                            yscrollcommand=scrollbar.set, selectmode="extended")
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        
        # 设置列标题和宽度
        tree.heading("#0", text="序号")
        tree.heading("title", text="标题")
        tree.heading("views", text="观看次数")
        tree.heading("duration", text="时长")
        tree.heading("upload_date", text="上传日期")
        tree.heading("status", text="状态")
        tree.heading(
            "analyzed",
            text="分析/场景/成片",
        )
        tree.heading("topic_category", text="主题分类")
        tree.heading("topic_subtype", text="主题子类型")
        tree.heading("tags", text="标签")
        tree.heading("mark", text="关联ID")

        _configure_channel_list_treeview(tree)
        

        def _scene_content_nonempty(v):
            sc = v.get("scene_content")
            if not sc:
                return False
            if isinstance(sc, list):
                return bool(sc)
            if isinstance(sc, str):
                t = sc.strip()
                if not t:
                    return False
                try:
                    parsed = json.loads(t)
                    return bool(parsed) if isinstance(parsed, list) else bool(parsed)
                except json.JSONDecodeError:
                    return bool(t)
            return False

        def populate_tree():
            """填充或刷新树视图"""
            # 清空现有项目
            for item in tree.get_children():
                tree.delete(item)
            
            # 获取最小观看次数
            try:
                min_view_count = int(min_view_var.get() or "0")
            except ValueError:
                min_view_count = 0
            
            # 过滤视频：只显示观看次数大于等于最小值的视频
            filtered_videos = []
            for video in self.downloader.channel_videos:
                view_count = video.get('view_count', 0)
                if view_count >= min_view_count:
                    filtered_videos.append(video)
            
            # 排序视频
            sort_mode = sort_mode_var.get()
            if sort_mode == "hot_degree":
                # 计算每个视频的热度值（每日观看次数）
                def calculate_hot_degree(video):
                    view_count = video.get('view_count', 0)
                    upload_date = video.get('upload_date', '')
                    if upload_date and len(upload_date) == 8:
                        try:
                            # 热度 = 观看次数 / 日期范围天数
                            date_obj = datetime.strptime(upload_date, '%Y%m%d')
                            days = (self.downloader.latest_date - date_obj).days + 1
                            return view_count / (days if days > 0 else 1)
                        except:
                            pass
                    # 如果无法计算，返回0
                    return 0.0
                
                filtered_videos.sort(key=calculate_hot_degree, reverse=True)

            elif sort_mode == "upload_date":
                # 按上传日期降序排序（最新的在前）
                filtered_videos.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
            elif sort_mode == "view_count":
                # 按观看次数降序排序
                filtered_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
            elif sort_mode == "duration":
                # 按时长降序排序（时长长的在前）
                def _duration_key(v):
                    d = v.get('duration') or 0
                    if isinstance(d, str):
                        d = float(d) if d else 0
                    return int(float(d))
                filtered_videos.sort(key=_duration_key, reverse=True)
            
            # 检查视频状态并填充数据
            downloaded_count = 0
            transcribed_count = 0
            summarized_count = 0
            hottest_degree = 0.0
            input_publish_map = _scan_input_media_publish_map()

            for idx, video in enumerate(filtered_videos, 1):
                #video.pop('text_content', None)
                # 格式化时长
                duration_sec = video.get('duration', 0)
                # 确保 duration_sec 是数字类型，并转换为整数
                if duration_sec:
                    if isinstance(duration_sec, str):
                        duration_sec = float(duration_sec)
                    duration_sec = int(float(duration_sec))  # 转换为整数
                    minutes = duration_sec // 60
                    seconds = duration_sec % 60
                    duration_str = f"{minutes}:{seconds:02d}"
                else:
                    duration_str = "N/A"
                
                # 格式化观看次数
                view_count = video.get('view_count', 0)
                view_str = f"{view_count:,}" if view_count else "N/A"
                
                # 格式化上传日期（支持 YYYYMMDD 或 YYYY-MM-DD，有日期即显示，不再依赖 latest_date）
                ud_raw = video.get('upload_date') or ''
                upload_date = str(ud_raw).strip() if ud_raw else ''
                ud_8 = (upload_date.replace('-', '')[:8] if upload_date else '')
                if ud_8 and len(ud_8) == 8:
                    upload_date_str = f"{ud_8[:4]}-{ud_8[4:6]}-{ud_8[6:]}"
                    if self.downloader.latest_date:
                        try:
                            days = (self.downloader.latest_date - datetime.strptime(ud_8, '%Y%m%d')).days + 1
                            degree = view_count / (days if days > 0 else 1)
                            if hottest_degree < degree:
                                hottest_degree = degree
                        except (ValueError, TypeError):
                            pass
                else:
                    upload_date_str = "N/A"
                
                # 检查视频状态
                status_str, video_file, audio_file = self.check_video_status(video)
                
                # 统计
                if "✅ 已下载" in status_str:
                    downloaded_count += 1
                if "✅ 已转录" in status_str:
                    transcribed_count += 1
                if "✅ 已摘要" in status_str:
                    summarized_count += 1
                
                # 获取主题相关字段
                topic_category = video.get('topic_category', '')
                topic_subtype = video.get('topic_subtype', '')
                problem_tags = video.get('tags', '')
                if isinstance(problem_tags, list):
                    problem_tags = " | ".join(str(t) for t in problem_tags if t is not None)
                elif not isinstance(problem_tags, str):
                    problem_tags = str(problem_tags) if problem_tags else ""

                tag_cell = problem_tags
                if len(tag_cell) > 120:
                    tag_cell = tag_cell[:120] + "…"

                # status：用户可编辑的关联视频 ID，| 分隔（旧版 1/2/3 或下载 success/failed 仍显示为可读）
                user_status = _status_display_for_related_field(video.get("status", ""))
                if len(user_status) > 80:
                    user_status = user_status[:77] + "..."
                analyzed_mark = ""
                if video.get("analyzed_content"):
                    analyzed_mark += "✓"
                if not _scene_content_nonempty(video):
                    analyzed_mark += "⚠"
                # gen_video 下任一候选 stem 的 .mp4 存在则标「片」
                if _gen_video_publish_mp4_if_ready(video):
                    analyzed_mark += "片"
                mp4_for_publish = _resolve_review_publish_mp4_path(
                    video, input_publish_map
                )
                row_title = _youtube_row_list_display_title(
                    video, max_src_chars=_CHANNEL_LIST_TREE_TITLE_MAX_SRC_CHARS
                )
                row_title_full = _youtube_row_list_display_title(video)
                tree.insert("", tk.END, text=str(idx), 
                           values=(
                               row_title,
                               view_str,
                               duration_str,
                               upload_date_str,
                               status_str,
                               analyzed_mark,
                               topic_category[:30] if topic_category else '',
                               topic_subtype[:30] if topic_subtype else "",
                               tag_cell,
                               user_status
                           ),
                           tags=(   _channel_list_row_tree_key(video), 
                                    row_title_full, 
                                    video_file or '', 
                                    audio_file or '', 
                                    str(view_count), 
                                    video.get('upload_date', ''), 
                                    str(duration_sec), 
                                    self.downloader.channel_name,
                                    mp4_for_publish)
                                )
            
            _normalize_channel_videos_for_storage(self.downloader.channel_videos, self.channel_path or "")
            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)

            # 更新顶部信息标签
            info_text = f"频道: {self.downloader.channel_name} | 共 {len(filtered_videos)}/{len(self.downloader.channel_videos)} 个视频 | 已下载: {downloaded_count} | 已转录: {transcribed_count} | 已摘要: {summarized_count} | 热度: {hottest_degree:.2f}"
            info_label.config(text=info_text)
        

        # 初始填充树视图
        populate_tree()
        
        # 选择统计标签
        stats_label = ttk.Label(dialog, text="已选择: 0 个视频", font=("Arial", 10))
        stats_label.pack(pady=5)
        
        def update_selection_count():
            selected = tree.selection()
            stats_label.config(text=f"已选择: {len(selected)} 个视频")
        tree.bind("<<TreeviewSelect>>", lambda e: update_selection_count())

        def _unique_video_details_from_tree_selection():
            """同一 URL 在树上可能对应多行；批量操作时按 URL 去重，每个 video_detail 只处理一次。"""
            seen_urls = set()
            details = []
            for item in tree.selection():
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                url_key = (item_tags[0] or "").strip()
                if not url_key or url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                vd = self.get_video_detail(url_key)
                if vd is not None:
                    details.append(vd)
            return details
        

        def delete_selected_videos():
            """删除选中的视频：从列表移除并删除相关文件"""
            if not tree.selection():
                return
            uniq_details = _unique_video_details_from_tree_selection()
            if not uniq_details:
                return
            
            # 确认删除
            if not messagebox.askyesno("确认删除", f"确定要删除 {len(uniq_details)} 个视频吗？\n\n这将从列表中移除并删除相关的文件（mp4、srt、json）。",
                                           parent=dialog):
                return
            
            deleted_count = 0
            failed_count = 0
            
            # 收集要删除的视频ID和文件
            videos_to_remove = []
            files_to_delete = []
            
            for video_detail in uniq_details:
                videos_to_remove.append(video_detail)
                filename_prefix = self.downloader.generate_video_prefix(video_detail)
                for filename in os.listdir(f"{self.youtube_dir}/media"):
                    if filename_prefix in filename:
                        file_path = os.path.join(f"{self.youtube_dir}/media", filename)
                        # 收集SRT和TXT文件
                        if (
                            filename.endswith(".srt")
                            or filename.endswith(".json")
                            or filename.endswith(".txt")
                        ):
                            files_to_delete.append(file_path)
                for filename in os.listdir(f"{self.youtube_dir}/media"):
                    if filename_prefix in filename:
                        file_path = os.path.join(f"{self.youtube_dir}/media", filename)
                        # 收集SRT和TXT文件
                        if filename.endswith('.mp4') or filename.endswith('.mp3') or filename.endswith('.wav'):
                            files_to_delete.append(file_path)
            
            # 删除文件
            for file_path in files_to_delete:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"✅ 已删除文件: {os.path.basename(file_path)}")
            
            # 从videos列表中移除
            for video_detail in videos_to_remove:
                if video_detail in self.downloader.channel_videos:
                    self.downloader.channel_videos.remove(video_detail)
                    deleted_count += 1
            
            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")
            
            # 刷新列表
            populate_tree()
            
            # 显示结果
            if failed_count > 0:
                show_auto_close_popup(
                    dialog,
                    "删除完成",
                    f"已删除 {deleted_count} 个视频\n\n{failed_count} 个文件删除失败",
                    kind="error",
                )
            else:
                show_auto_close_popup(
                    dialog,
                    "删除完成",
                    f"已成功删除 {deleted_count} 个视频及其相关文件",
                )
        
        # 绑定Delete键
        def on_key_press(event):
            if event.keysym == 'Delete':
                delete_selected_videos()
        tree.bind('<KeyPress>', on_key_press)
        # 确保tree可以获得焦点以便接收键盘事件
        tree.focus_set()

        tree.bind("<Button-1>", lambda e: tree.focus_set())

        # 摘要窗口单例：切换上一条/下一条时复用同一 Toplevel，仅重建内容
        summary_window_ref = {"w": None}

        class _SummaryNavFakeEvt:
            y = None

        def _nav_summary_delta(delta):
            """Ctrl+←/→：按列表顺序切换条目并刷新摘要窗。"""
            sw = summary_window_ref.get("w")
            if not sw or not sw.winfo_exists():
                return "break"
            ctx = getattr(sw, "_summary_drop_ctx", None)
            if not isinstance(ctx, dict):
                return "break"
            items = list(tree.get_children())
            if not items:
                return "break"

            i = None
            selected = tree.selection()
            if selected and selected[0] in items:
                i = items.index(selected[0])
            else:
                vd = ctx.get("vd")
                if isinstance(vd, dict):
                    cur_key = _channel_list_row_tree_key(vd)
                    if cur_key:
                        try:
                            i = next(
                                idx
                                for idx, it in enumerate(items)
                                if (_treeview_item_tags_safe(tree, it) or [None])[0] == cur_key
                            )
                        except StopIteration:
                            pass
            if i is None:
                return "break"

            j = i + delta
            if j < 0 or j >= len(items):
                return "break"
            nxt = items[j]
            tree.selection_set(nxt)
            tree.see(nxt)
            tree.focus(nxt)
            on_focus(_SummaryNavFakeEvt(), ctx.get("nav_low_priority", False))
            return "break"

        def _bind_ctrl_arrow_nav(widget):
            for seq, delta in (
                ("<Control-Left>", -1),
                ("<Control-Right>", 1),
                ("<Control-KeyPress-Left>", -1),
                ("<Control-KeyPress-Right>", 1),
            ):
                widget.bind(
                    seq,
                    lambda e, d=delta: _nav_summary_delta(d),
                    add="+",
                )

        def _bind_summary_nav_subtree(widget):
            _bind_ctrl_arrow_nav(widget)
            for ch in widget.winfo_children():
                _bind_summary_nav_subtree(ch)

        def _video_detail_from_tree_event(event):
            if hasattr(event, "y") and event.y:
                item = tree.identify_row(event.y)
            else:
                selected = tree.selection()
                if not selected:
                    return None
                item = selected[0]
            if not item:
                return None
            if item not in tree.selection():
                tree.selection_set(item)
            item_tags = _treeview_item_tags_safe(tree, item)
            if not item_tags:
                return None
            return self.get_video_detail(item_tags[0])

        def _video_detail_has_raw_for_project(vd):
            if not isinstance(vd, dict):
                return False
            return (
                bool(vd.get("analyzed_content"))
                and _scene_content_nonempty(vd)
            )

        def _resummarize_one_video_detail(vd):
            if not isinstance(vd, dict):
                return
            self.update_text_content(vd)
            if not self.generate_analyzed_content_for_video(vd, force_rewrite=True):
                messagebox.showwarning(
                    "重摘",
                    "无法重新摘要：缺少足够转录原文，或生成失败。",
                    parent=dialog,
                )
                return
            self.prepare_category_for_content(vd, self.topic_choices)
            try:
                with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
            populate_tree()
            show_auto_close_popup(dialog, "重摘", "已重新生成 analyzed content。")

        def _run_project_start_for_video_detail(
            vd,
            parent,
            *,
            forced_action=None,
            topic_category=None,
            topic_subtype=None,
            topic_tags=None,
            on_reopen_summary=None,
            after_persist=None,
        ):
            """启动/打开工作流项目。forced_action: None=完整流程；open=仅打开；new=仅新建。"""
            if not isinstance(vd, dict):
                return

            def _topic_category_val(cfg=None):
                return (
                    (topic_category or "").strip()
                    or ((cfg or {}).get("topic_category") or "").strip()
                    or (vd.get("topic_category") or "").strip()
                )

            def _topic_subtype_val(cfg=None):
                return (
                    (topic_subtype or "").strip()
                    or ((cfg or {}).get("topic_subtype") or "").strip()
                    or (vd.get("topic_subtype") or "").strip()
                )

            def _topic_tags_val(cfg=None):
                if topic_tags is not None and str(topic_tags).strip():
                    parsed = parse_tags_list(str(topic_tags))
                    if parsed:
                        return parsed
                if cfg and cfg.get("tags") is not None:
                    return cfg.get("tags")
                tags = vd.get("tags")
                if isinstance(tags, list):
                    return tags or None
                if isinstance(tags, str) and tags.strip():
                    return parse_tags_list(tags) or None
                return None

            existing_pid = _video_detail_project_pid(vd)
            list_idx = -1
            try:
                list_idx = (self.downloader.channel_videos or []).index(vd)
            except ValueError:
                pass
            list_path = (self.downloader.channel_list_json or "").strip()

            from project_manager import (
                create_project_with_initial_raw,
                LAST_NARRATOR,
                LAST_VISUAL_STYLE,
            )

            def _persist_channel_list_and_refresh_tree(
                select_key: str = "",
                *,
                reopen_summary: bool = False,
            ) -> None:
                try:
                    _normalize_channel_videos_for_storage(
                        self.downloader.channel_videos, self.channel_path or ""
                    )
                    with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                        json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                except OSError:
                    pass
                try:
                    populate_tree()
                except Exception:
                    pass
                u = (select_key or "").strip()
                if u:
                    try:
                        for item in tree.get_children():
                            t = _treeview_item_tags_safe(tree, item)
                            if t and t[0] == u:
                                tree.selection_set(item)
                                tree.see(item)
                                tree.focus(item)
                                break
                    except tk.TclError:
                        pass
                if reopen_summary and u and callable(on_reopen_summary):
                    try:
                        on_reopen_summary()
                    except Exception:
                        pass
                elif callable(after_persist):
                    try:
                        after_persist()
                    except Exception:
                        pass

            def _open_bound_project(
                cfg: dict,
                cfg_pid: str,
                *,
                topic_list_path: str | None = None,
            ) -> None:
                tc = _topic_category_val(cfg)
                if not tc:
                    messagebox.showwarning(
                        "无法打开",
                        f"PID：{cfg_pid}\n\n缺少 topic_category，请先保存主题分类。",
                        parent=parent,
                    )
                    return

                launch_cfg = dict(cfg)
                launch_cfg["topic_category"] = tc
                if not (launch_cfg.get("channel") or "").strip():
                    launch_cfg["channel"] = os.path.basename(self.channel_path)

                target_path = (topic_list_path or "").strip()
                target_ix = -1
                if target_path:
                    target_ix = project_manager.find_list_row_index_by_pid(target_path, cfg_pid)
                else:
                    target_path, target_ix, _ = project_manager.find_project_topic_list_row(launch_cfg)

                if target_ix < 0 and not topic_list_path:
                    yn_fix = messagebox.askyesno(
                        "主题分表缺少该项目",
                        f"list/{config.topic_category_list_file_basename(tc)} 中未找到 pid「{cfg_pid}」。\n\n"
                        "是否写入主题分表？",
                        parent=parent,
                    )
                    if not yn_fix:
                        return
                    try:
                        topic_row = copy.deepcopy(vd)
                        _apply_project_config_to_list_row(
                            topic_row, launch_cfg, channel_path=self.channel_path or ""
                        )
                        target_path = _upsert_topic_category_program_list_row(
                            self.channel_path, tc, topic_row
                        )
                        target_ix = project_manager.find_list_row_index_by_pid(
                            target_path, cfg_pid
                        )
                    except Exception as exc:
                        show_auto_close_popup(parent, "写入主题分表失败", str(exc), kind="error")
                        return

                if target_ix < 0:
                    show_auto_close_popup(
                        parent,
                        "无法打开",
                        f"主题分表中找不到 pid「{cfg_pid}」。",
                        kind="error",
                    )
                    return

                opened = _launch_gui_wf_from_list_json(target_path, target_ix, parent=parent)
                if not opened:
                    _launch_gui_wf_open_pid(cfg_pid, parent=parent)

            def _after_new_project_created(
                selected_config,
                *,
                superseded_pid: str = "",
            ):
                _pid = (selected_config.get("pid") or "").strip()
                if not _pid:
                    return
                ch_path = self.channel_path or ""
                list_path = (self.downloader.channel_list_json or "").strip()
                tc = (
                    (vd.get("topic_category") or selected_config.get("topic_category") or "")
                    .strip()
                )
                viewing_topic_list = _is_viewing_topic_category_program_list(
                    ch_path, list_path, tc
                )
                old_pid = (superseded_pid or "").strip()

                if viewing_topic_list:
                    # 在主题分表中「新建项目」：保留源行，追加独立项目行（计数 +1）
                    new_row = _clone_channel_video_for_new_project(vd, selected_config)
                    _normalize_channel_list_item_for_storage(new_row, ch_path)
                    self.downloader.channel_videos.append(new_row)
                    select_key = _channel_list_row_tree_key(new_row)
                else:
                    # 在频道热门总表中：仅更新源 YouTube 行，不向总表克隆重复行
                    _apply_project_config_to_list_row(
                        vd, selected_config, channel_path=ch_path
                    )
                    self.downloader.channel_videos = _drop_cloned_duplicates_of_row(
                        self.downloader.channel_videos, vd
                    )
                    select_key = _channel_list_row_tree_key(vd)
                    if old_pid and old_pid != _pid:
                        _remove_pid_from_topic_category_lists(ch_path, old_pid)

                _persist_channel_list_and_refresh_tree(select_key, reopen_summary=False)

                if not tc:
                    messagebox.showwarning(
                        "项目已创建",
                        f"PID：{_pid}\n\n缺少 topic_category，未写入主题分表。\n"
                        "请先保存主题分类后再打开工作流。",
                        parent=parent,
                    )
                    return
                if viewing_topic_list:
                    # 当前列表即主题分表，persist 已写入；勿再 upsert 追加导致磁盘多一行而内存不同步
                    topic_list_path = list_path
                else:
                    try:
                        topic_list_path = _upsert_topic_category_program_list_row(
                            ch_path, tc, copy.deepcopy(vd)
                        )
                    except Exception as exc:
                        show_auto_close_popup(
                            parent,
                            "项目已创建",
                            f"PID：{_pid}\n\n写入主题分表失败：\n{exc}",
                            kind="error",
                        )
                        return

                if not messagebox.askyesno(
                    "项目已创建",
                    f"PID：{_pid}\n\n要打开魔法工作流吗？",
                    parent=parent,
                ):
                    return
                _open_bound_project(selected_config, _pid, topic_list_path=topic_list_path)

            def _create_new_project_from_raw(
                analyzed_content,
                scene_content,
                *,
                narrator=None,
                visual_style=None,
                host_display=None,
                language=None,
                topic_category_kw=None,
                topic_subtype_kw=None,
                topic_tags_kw=None,
                superseded_pid: str = "",
            ):
                if not analyzed_content.strip() or not _scene_content_nonempty(
                    {"scene_content": scene_content}
                ):
                    messagebox.showwarning(
                        "提示",
                        "analyzed_content 须为非空文本；scene_content 须已填写，无法启动新项目。",
                        parent=parent,
                    )
                    return
                ch = os.path.basename(self.channel_path)
                lang = (language or getattr(self, "language", None) or "tw").strip() or "tw"
                result, selected_config = create_project_with_initial_raw(
                    parent=self.root,
                    channel=ch,
                    language=lang,
                    narrator=narrator if narrator is not None else LAST_NARRATOR,
                    visual_style=visual_style if visual_style is not None else LAST_VISUAL_STYLE,
                    host_display=host_display or config_prompt.HARRATOR_DISPLAY_OPTIONS[-1],
                    analyzed_content=analyzed_content,
                    scene_content=scene_content,
                    topic_category=topic_category_kw if topic_category_kw is not None else _topic_category_val(),
                    topic_subtype=topic_subtype_kw if topic_subtype_kw is not None else _topic_subtype_val(),
                    topic_tags=topic_tags_kw if topic_tags_kw is not None else _topic_tags_val(),
                )
                if result == "new" and selected_config:
                    _after_new_project_created(
                        selected_config,
                        superseded_pid=superseded_pid,
                    )

            def _load_bound_project_cfg():
                cfg = None
                if list_idx >= 0 and list_path and os.path.isfile(list_path):
                    cfg = project_manager.project_config_from_list_item(vd, list_path, list_idx)
                if not cfg or not cfg.get("pid"):
                    if existing_pid:
                        cfg = project_manager.load_project_config_by_pid(existing_pid)
                return cfg

            if forced_action == "open":
                if not existing_pid:
                    messagebox.showwarning("无法打开", "本条尚无 project_profile / 绑定项目。", parent=parent)
                    return
                cfg = _load_bound_project_cfg()
                cfg_pid = (cfg.get("pid") or "").strip() if isinstance(cfg, dict) else ""
                if not cfg_pid:
                    messagebox.showwarning(
                        "无法打开已有项目",
                        f"未找到 pid「{existing_pid}」的项目配置。",
                        parent=parent,
                    )
                    return
                if cfg_pid != existing_pid:
                    messagebox.showwarning(
                        "项目配置不一致",
                        f"列表 pid 为「{existing_pid}」，配置内 pid 为「{cfg_pid}」。",
                        parent=parent,
                    )
                    return
                _open_bound_project(cfg, cfg_pid)
                return

            if forced_action == "new":
                _create_new_project_from_raw(
                    vd.get("analyzed_content"),
                    vd.get("scene_content"),
                    language=vd.get("language"),
                    topic_category_kw=_topic_category_val(),
                    topic_subtype_kw=_topic_subtype_val(),
                    topic_tags_kw=_topic_tags_val(),
                    superseded_pid=existing_pid or "",
                )
                return

            if existing_pid:
                cfg = _load_bound_project_cfg()
                if isinstance(cfg, dict) and (cfg.get("pid") or "").strip():
                    cfg_pid = (cfg.get("pid") or "").strip()
                    if cfg_pid != existing_pid:
                        messagebox.showwarning(
                            "项目配置不一致",
                            f"本条 ``project_profile.pid`` 为「{existing_pid}」，但载入的配置内 pid 为「{cfg_pid}」。\n"
                            "将按「新建项目」流程继续（需有 RAW 内容）。",
                            parent=parent,
                        )
                    else:
                        picked = askchoice(
                            "已有绑定项目",
                            [
                                ("open", f"打开已有项目（{cfg_pid}）"),
                                (
                                    "clone",
                                    "参照该项目新建（复制 RAW 等到新项目，可再改）",
                                ),
                            ],
                            parent=parent,
                        )
                        if not picked:
                            return
                        _action = picked[1]
                        if _action == "open":
                            _open_bound_project(cfg, cfg_pid)
                            return
                        if _action == "clone":
                            ac = cfg.get("analyzed_content") or vd.get("analyzed_content")
                            sc = cfg.get("scene_content") or vd.get("scene_content")
                            _create_new_project_from_raw(
                                ac,
                                sc,
                                narrator=cfg.get("narrator"),
                                visual_style=cfg.get("visual_style"),
                                host_display=cfg.get("host_display"),
                                language=cfg.get("language"),
                                topic_category_kw=_topic_category_val(cfg),
                                topic_subtype_kw=_topic_subtype_val(cfg),
                                topic_tags_kw=_topic_tags_val(cfg),
                                superseded_pid=cfg_pid,
                            )
                            return
                else:
                    messagebox.showwarning(
                        "无法打开已有项目",
                        f"未找到 pid「{existing_pid}」的项目配置（列表中无 project_profile，且主题分表/列表中也未找到）。\n"
                        "将按「新建项目」流程继续。",
                        parent=parent,
                    )

            _create_new_project_from_raw(
                vd.get("analyzed_content"),
                vd.get("scene_content"),
                topic_category_kw=_topic_category_val(),
                topic_subtype_kw=_topic_subtype_val(),
                topic_tags_kw=_topic_tags_val(),
            )

        def on_enter_key(event):
            on_focus(event, low_priority=False)

        def on_double_click(event):
            vd = _video_detail_from_tree_event(event)
            if not vd:
                return

            choices = [("edit", "打开摘要编辑")]
            if (vd.get("analyzed_content","")):
                choices.append(
                    ("review_analyzed", "查看 analyzed content（分析内容预览）")
                )
            existing_pid = _video_detail_project_pid(vd)
            if existing_pid:
                choices.append(("open_project", f"打开已有项目（{existing_pid}）"))
            if _video_detail_has_raw_for_project(vd):
                choices.append(("new_project", "新建项目（基于 analyzed / scene）"))
            choices.append(("resummarize", "重摘（重新摘要 analyzed content）"))

            title = f"选择操作 — {_youtube_row_display_title(vd)}"
            if len(title) > 72:
                title = title[:69] + "…"
            picked = askchoice(title, choices, parent=dialog)
            if not picked:
                return
            _, action = picked

            if action == "edit":
                on_focus(event, low_priority=True)
            elif action == "review_analyzed":
                self.show_analyzed_content_popup(vd, parent=dialog)
            elif action == "open_project":
                _run_project_start_for_video_detail(vd, dialog, forced_action="open")
            elif action == "new_project":
                _run_project_start_for_video_detail(vd, dialog, forced_action="new")
            elif action == "resummarize":
                _resummarize_one_video_detail(vd)

        def on_focus(event, low_priority=False):
            # 处理鼠标事件和键盘事件
            if hasattr(event, 'y') and event.y:
                # 鼠标事件：通过坐标识别行
                item = tree.identify_row(event.y)
            else:
                # 键盘事件：获取当前选中的项
                selected = tree.selection()
                if not selected:
                    return
                item = selected[0]
            
            if not item:
                return

            if item not in tree.selection():
                tree.selection_set(item)
            
            item_tags = _treeview_item_tags_safe(tree, item)
            if not item_tags:
                return
            video_detail = self.get_video_detail(item_tags[0])
            if not video_detail:
                return

            # get index of the selected item & save to a variable
            selected_index = tree.item(item, "text").split(".")[0]
            topic_type = video_detail.get('topic_subtype', '')
            topic_category = video_detail.get('topic_category', '')
            topic_subtype = video_detail.get('topic_subtype', '')
            topic_status = _status_display_for_related_field(video_detail.get("status", ""))
            topic_tags = video_detail.get('tags', '')
            if isinstance(topic_tags, list):
                topic_tags = ' | '.join(topic_tags)
            elif not isinstance(topic_tags, str):
                topic_tags = str(topic_tags) if topic_tags else ''
            if not low_priority or not topic_type or not topic_type.strip() or not topic_category or not topic_category.strip() :
                # show a messagebox to let user know the summary is generating (non-blocking)
                # self.root.after(0, lambda: messagebox.showinfo("提示", "摘要生成中，请稍后...", parent=self.root))
                self.update_text_content(video_detail)
                topic_type = video_detail.get('topic_subtype', '')
                topic_category = video_detail.get('topic_category', '')
                topic_subtype = video_detail.get('topic_subtype', '')
                topic_tags = video_detail.get('tags', '')
                if isinstance(topic_tags, list):
                    topic_tags = ' | '.join(topic_tags)
                elif not isinstance(topic_tags, str):
                    topic_tags = str(topic_tags) if topic_tags else ''

            # 摘要窗口：首次新建，之后 Ctrl+左/右切换条目时复用同一窗口并重建内容
            if summary_window_ref.get("w") and summary_window_ref["w"].winfo_exists():
                summary_window = summary_window_ref["w"]
                summary_window.geometry("1060x520")
                for child in summary_window.winfo_children():
                    child.destroy()
            else:
                summary_window = tk.Toplevel(dialog)
                summary_window_ref["w"] = summary_window
                summary_window.geometry("1060x520")
                summary_window.resizable(True, True)
                summary_window.transient(dialog)
            if not getattr(summary_window, "_summary_drop_ctx", None):
                summary_window._summary_drop_ctx = {"mgr": None, "vd": None}
            summary_window._summary_drop_ctx["mgr"] = self
            summary_window._summary_drop_ctx["vd"] = video_detail
            summary_window._summary_drop_ctx["refresh_channel_tree"] = populate_tree
            _dnd_title_suffix = ""
            if not _TK_DND_AVAILABLE:
                _dnd_title_suffix = "（未安装 tkinterdnd2，拖放不可用）"
            elif not _tkinter_dnd_root_capable(summary_window):
                _dnd_title_suffix = "（拖放需根窗为 TkinterDnD.Tk；GUI_pm 已改为该方式，请重开程序）"
            summary_window._summary_drop_ctx["summary_title_index"] = selected_index
            summary_window._summary_drop_ctx["summary_dnd_title_suffix"] = _dnd_title_suffix
            _refresh_summary_window_title(summary_window, video_detail)
            main_frame = ttk.Frame(summary_window, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # 视频名称（第一行，可编辑；保存信息时一并写回列表）
            has_project_profile = project_manager.list_json_row_has_project_profile(
                video_detail
            )
            title_frame = ttk.LabelFrame(main_frame, text="视频名称", padding=10)
            title_frame.pack(fill=tk.X, pady=(0, 10))
            source_title_var = tk.StringVar(
                value=_youtube_row_source_title(video_detail)
            )
            project_title_var = tk.StringVar(
                value=_youtube_row_project_title(video_detail)
            )
            story_meta_title = _youtube_row_story_meta_title(video_detail)
            story_meta_var = tk.StringVar(value=story_meta_title)
            show_second_title_row = True
            if has_project_profile:
                ttk.Label(
                    title_frame,
                    text="原视频标题:",
                    font=("Arial", 10, "bold"),
                ).grid(row=0, column=0, sticky="w", padx=(5, 4), pady=4)
                source_title_entry = ttk.Entry(
                    title_frame, textvariable=source_title_var
                )
                source_title_entry.grid(
                    row=0, column=1, sticky="ew", padx=(0, 5), pady=4
                )
                ttk.Label(
                    title_frame,
                    text="项目 meta (project_profile):",
                    font=("Arial", 10, "bold"),
                ).grid(row=1, column=0, sticky="w", padx=(5, 4), pady=4)
                project_title_entry = ttk.Entry(
                    title_frame, textvariable=project_title_var
                )
                project_title_entry.grid(row=1, column=1, sticky="ew", padx=(0, 5), pady=4)
                title_frame.columnconfigure(1, weight=1)
            else:
                ttk.Label(
                    title_frame,
                    text="标题:",
                    font=("Arial", 10, "bold"),
                ).grid(row=0, column=0, sticky="w", padx=(5, 4), pady=4)
                source_title_entry = ttk.Entry(
                    title_frame, textvariable=source_title_var
                )
                source_title_entry.grid(
                    row=0, column=1, sticky="ew", padx=5, pady=4
                )
                title_frame.columnconfigure(1, weight=1)
                project_title_entry = None
                ttk.Label(
                    title_frame,
                    text="Story meta:",
                    font=("Arial", 10, "bold"),
                ).grid(row=1, column=0, sticky="w", padx=(5, 4), pady=4)
                ttk.Label(
                    title_frame,
                    textvariable=story_meta_var,
                    anchor="w",
                    wraplength=720,
                ).grid(row=1, column=1, sticky="ew", padx=(0, 5), pady=4)

            feature_media_var = tk.StringVar(value="")
            media_btn_row = ttk.Frame(title_frame)
            media_btn_row.grid(
                row=2 if show_second_title_row else 1,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(6, 2),
            )
            ttk.Label(
                media_btn_row,
                textvariable=feature_media_var,
                font=("Arial", 9),
            ).pack(side=tk.LEFT, anchor=tk.W, padx=(5, 10))
            open_feature_folder_btn = ttk.Button(
                media_btn_row,
                text="打开成片文件夹",
                width=16,
            )
            open_feature_folder_btn.pack(side=tk.LEFT, padx=(0, 6))
            edit_clip_segments_btn = ttk.Button(
                media_btn_row,
                text="编辑成片片段",
                width=14,
            )
            edit_clip_segments_btn.pack(side=tk.LEFT, padx=(0, 6))
            copy_cover_clipboard_btn = ttk.Button(
                media_btn_row,
                text="复制封面到剪贴板",
                width=18,
            )
            copy_cover_clipboard_btn.pack(side=tk.LEFT, padx=(0, 6))

            def refresh_feature_media_row():
                if not summary_window.winfo_exists():
                    return
                mp4_p = _find_gen_video_mp4_for_row(video_detail)
                webp_p = _find_gen_video_webp_for_row(video_detail)
                seg_n = len(_get_gen_video_clip_segments(video_detail))
                parts = []
                if mp4_p:
                    parts.append(f"成片: {os.path.basename(mp4_p)}")
                if webp_p:
                    parts.append(f"封面: {os.path.basename(webp_p)}")
                if seg_n:
                    parts.append(f"片段配置: {seg_n} 段")
                if parts:
                    feature_media_var.set("  |  ".join(parts))
                else:
                    gen_hint = _gen_video_storage_dir() or "(未配置 publish/gen_video)"
                    feature_media_var.set(
                        f"尚未拖入成片/封面（拖入 MP4（审阅裁剪/排序后拼接）或图片到本窗，保存至 {gen_hint}）"
                    )
                try:
                    copy_cover_clipboard_btn.config(
                        state=tk.NORMAL if webp_p else tk.DISABLED
                    )
                except tk.TclError:
                    pass
                try:
                    edit_clip_segments_btn.config(
                        state=tk.NORMAL if seg_n else tk.DISABLED
                    )
                except tk.TclError:
                    pass

            def on_open_feature_media_folder():
                mp4_p = _find_gen_video_mp4_for_row(video_detail)
                webp_p = _find_gen_video_webp_for_row(video_detail)
                _open_feature_media_in_explorer(mp4_p, webp_p)

            def on_copy_cover_to_clipboard():
                webp_p = _find_gen_video_webp_for_row(video_detail)
                if not webp_p:
                    messagebox.showwarning(
                        "提示",
                        "尚无封面 WebP。\n请拖入图片或 Ctrl+V 粘贴图片到本窗口。",
                        parent=summary_window,
                    )
                    return
                if _copy_image_file_to_clipboard(summary_window, webp_p):
                    show_auto_close_popup(
                        summary_window,
                        "已复制",
                        f"封面已复制到剪贴板：\n{os.path.basename(webp_p)}",
                    )

            open_feature_folder_btn.config(command=on_open_feature_media_folder)
            edit_clip_segments_btn.config(
                command=lambda: _on_summary_reopen_gen_video_clip_review(summary_window)
            )
            copy_cover_clipboard_btn.config(command=on_copy_cover_to_clipboard)
            refresh_feature_media_row()
            if isinstance(summary_window._summary_drop_ctx, dict):
                summary_window._summary_drop_ctx[
                    "refresh_feature_media_row"
                ] = refresh_feature_media_row

                def refresh_title_fields():
                    try:
                        source_title_var.set(_youtube_row_source_title(video_detail))
                        if has_project_profile:
                            project_title_var.set(
                                _youtube_row_project_title(video_detail)
                            )
                        else:
                            story_meta_var.set(
                                _youtube_row_story_meta_title(video_detail)
                            )
                    except (NameError, tk.TclError):
                        pass
                    _refresh_summary_window_title(summary_window, video_detail)

                summary_window._summary_drop_ctx[
                    "refresh_title_fields"
                ] = refresh_title_fields
            
            # 主题信息编辑区域
            topic_frame = ttk.LabelFrame(main_frame, text="主题信息", padding=10)
            topic_frame.pack(fill=tk.X, pady=(0, 10))
            
            # 主题信息两行：分类+子类型 | 标签+关联 ID
            ttk.Label(topic_frame, text="主题分类:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky='w', padx=(5, 2), pady=5)
            category_var = tk.StringVar(value=topic_category)
            category_combo = ttk.Combobox(topic_frame, textvariable=category_var, values=self.topic_categories, state="readonly", width=16)
            category_combo.grid(row=0, column=1, padx=(0, 8), pady=5, sticky='ew')

            ttk.Label(topic_frame, text="主题子类型:", font=("Arial", 10, "bold")).grid(row=0, column=2, sticky='w', padx=(0, 2), pady=5)
            subtype_var = tk.StringVar(value=topic_subtype)
            subtype_combo = ttk.Combobox(topic_frame, textvariable=subtype_var, values=[], state="readonly", width=16)
            subtype_combo.grid(row=0, column=3, padx=(0, 5), pady=5, sticky='ew')

            ttk.Label(topic_frame, text="主题标签:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky='w', padx=(5, 2), pady=5)
            tags_var = tk.StringVar(value=topic_tags)
            tags_row = ttk.Frame(topic_frame)
            tags_row.grid(row=1, column=1, padx=(0, 8), pady=5, sticky='ew')
            tags_entry = ttk.Entry(tags_row, textvariable=tags_var)
            tags_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            def _on_tag_pick(feature: str, option: str):
                merged = merge_tag_pick(parse_tags_list(tags_var.get() or ""), feature, option)
                tags_var.set(", ".join(merged))

            def _open_tag_menu():
                m = build_tag_cascade_menu(
                    summary_window,
                    getattr(self, "tag_features_map", None) or {},
                    _on_tag_pick,
                )
                post_menu_below_widget(m, tags_add_btn)

            tags_add_btn = ttk.Button(tags_row, text="添加标签", command=_open_tag_menu)
            tags_add_btn.pack(side=tk.LEFT, padx=(6, 0))

            ttk.Label(topic_frame, text="关联视频ID:", font=("Arial", 10, "bold")).grid(row=1, column=2, sticky='w', padx=(0, 2), pady=5)
            status_var = tk.StringVar(value=topic_status)
            status_entry = ttk.Entry(topic_frame, textvariable=status_var)
            status_entry.grid(row=1, column=3, padx=(0, 5), pady=5, sticky='ew')
            
            def update_subtypes(*args):
                """根据选择的分类更新子类型选项"""
                selected_category = category_var.get()
                subtypes = []
                if selected_category and self.topic_choices:
                    for item in self.topic_choices:
                        if isinstance(item, dict) and item.get('topic_category') == selected_category:
                            for subtype_item in item.get('topic_subtypes', []):
                                if isinstance(subtype_item, dict):
                                    # 从 topic_subtypes 数组中获取每个项的 topic_subtype 字段
                                    subtype_name = subtype_item.get('topic_subtype', '')
                                    if subtype_name and subtype_name not in subtypes:
                                        subtypes.append(subtype_name)
                subtype_combo['values'] = subtypes
                # 使用 video_detail 当前值，避免闭包中的 topic_subtype 过时（如 do_re_category 刚更新后）
                current_subtype = (video_detail.get('topic_subtype') or subtype_var.get() or '').strip()
                if current_subtype in subtypes:
                    subtype_var.set(current_subtype)
                else:
                    subtype_var.set('')

            def do_re_category():
                """重新分类：重新分类，保存回 video_detail 并持久化"""
                self.prepare_category_for_content(video_detail, self.topic_choices)
                # 3. 同步 UI 显示
                category_var.set(video_detail.get("topic_category", ""))
                subtype_var.set(video_detail.get("topic_subtype", ""))
                tags_list = video_detail.get("tags", [])
                tags_var.set(", ".join(tags_list) if isinstance(tags_list, list) else str(tags_list or ""))
                update_subtypes()
                try:
                    populate_tree()
                except Exception:
                    pass

            def do_story_view():
                def _after_story_title():
                    try:
                        refresh_title_fields()
                    except (NameError, tk.TclError):
                        pass

                text = self.open_content_field_editor(
                    summary_window,
                    video_detail,
                    "story",
                    on_story_title_updated=_after_story_title,
                    main_character=(character_var.get() or "").strip(),
                    channel_path=self.channel_path or "",
                )
                if text is not None:
                    show_auto_close_popup(summary_window, "已保存", "story 已更新。")
                    try:
                        populate_tree()
                    except Exception:
                        pass
                    try:
                        refresh_title_fields()
                    except (NameError, tk.TclError):
                        pass

            def do_poem_view():
                text = self.open_content_field_editor(
                    summary_window,
                    video_detail,
                    "poem",
                    on_saved=_after_content_field_saved,
                )
                if text is not None:
                    show_auto_close_popup(summary_window, "已保存", "poem 已更新。")
                    try:
                        populate_tree()
                    except Exception:
                        pass

            def do_image_prompt():
                raw_story = video_detail.get("story")
                if isinstance(raw_story, list):
                    story_raw = json.dumps(raw_story, ensure_ascii=False, indent=2)
                else:
                    story_raw = (raw_story if isinstance(raw_story, str) else str(raw_story or ""))
                self._copy_image_prompt_instruction(
                    parent=summary_window,
                    video_detail=video_detail,
                    story_raw=story_raw,
                    main_character=(character_var.get() or "").strip(),
                    channel_path=self.channel_path or "",
                )

            # 绑定事件：用 trace 保证主题分类变更时一定触发子类型更新（<<ComboboxSelected>> 在某些环境下可能不触发）
            def _on_category_var_write(*args):
                update_subtypes()
            category_var.trace_add('write', _on_category_var_write)
            
            # 保存按钮
            def save_story_info():
                """保存主题信息"""
                _apply_video_detail_titles_from_ui(
                    video_detail,
                    source_title=source_title_var.get(),
                    project_title=project_title_var.get()
                    if has_project_profile
                    else "",
                    channel_path=self.channel_path or "",
                )
                category = category_var.get().strip()
                subtype = subtype_var.get().strip()
                tags_text = tags_var.get().strip()
                st = status_var.get()
                
                # 解析标签：KEY=value 与旧版纯文本；| 或「逗号+下一段 KEY=」分隔
                tags_list = parse_tags_list(tags_text) if tags_text else []
                
                # 更新视频详情
                if category:
                    video_detail['topic_category'] = category
                else:
                    video_detail.pop('topic_category', None)
                if subtype:
                    video_detail['topic_subtype'] = subtype
                else:
                    video_detail.pop('topic_subtype', None)
                if tags_list:
                    video_detail['tags'] = tags_list
                else:
                    video_detail.pop('tags', None)
                st = (st or "").strip()
                if st:
                    video_detail["status"] = st
                else:
                    video_detail.pop("status", None)
                # 保存到文件
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                
                # 刷新树视图（如果对话框还存在）
                try:
                    populate_tree()
                except:
                    pass
                try:
                    refresh_publish_row()
                except Exception:
                    pass
                try:
                    _refresh_summary_window_title(summary_window, video_detail)
                except Exception:
                    pass

                show_auto_close_popup(summary_window, "成功", "视频名称与主题信息已保存")

            def _on_title_entry_return(_event=None):
                save_story_info()

            source_title_entry.bind("<Return>", _on_title_entry_return)
            if project_title_entry is not None:
                project_title_entry.bind("<Return>", _on_title_entry_return)

            def on_find_similar_cases():
                cur_id = _video_youtube_id(video_detail)
                if not cur_id:
                    messagebox.showwarning("提示", "当前视频缺少 YouTube id，无法建立关联", parent=summary_window)
                    return
                ref_sum = (
                    (video_detail.get("story") or video_detail.get("summary") or "")
                    .strip()
                )
                if not ref_sum:
                    messagebox.showwarning("提示", "当前视频 story 为空，请先填写或生成 story 后再找类似案例", parent=summary_window)
                    return

                _channel_key = os.path.basename(self.channel_path)

                reference_filter_prompt = config_channel.get_channel_config(_channel_key).get('channel_prompt', {}).get('prompt_reference_filter', '')
                reference_filter_prompt = reference_filter_prompt.format(topic=video_detail['topic_category'] + " - " + video_detail['topic_subtype'])

                editor = ReferenceEditorDialog(
                    summary_window,
                    current_story = video_detail.get("analyzed_content"),
                    reference_filter=reference_filter_prompt,
                )

                prepared = editor.show()
                if not prepared:
                    return
                ch_list = self.downloader.channel_videos
                # 当前视频：把每条参考对应的 YouTube id 合并进 status（| 分隔、去重）
                # 每条参考在 channel_videos 里对应一条：把当前视频 cur_id 合并进其 status
                urls_to_select = []
                for item in prepared:
                    if not isinstance(item, dict):
                        continue
                    ref_v = _find_channel_video_for_reference_item(item, ch_list)
                    ref_yid = ""
                    if ref_v:
                        ref_yid = _video_youtube_id(ref_v)
                        ref_v["status"] = _merge_related_id_status(ref_v.get("status"), cur_id)
                        k = _channel_list_row_tree_key(ref_v)
                        if k:
                            urls_to_select.append(k)
                    if not ref_yid:
                        ref_yid = _reference_item_youtube_id(item)
                    if ref_yid:
                        video_detail["status"] = _merge_related_id_status(video_detail.get("status"), ref_yid)

                # save the video_detail to the channel_list_json
                with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                # populate the tree, and select the current video & matched reference rows
                _urls = urls_to_select

                def _after_find_similar():
                    populate_tree()
                    try:
                        tree.selection_set(_channel_list_row_tree_key(video_detail))
                    except Exception:
                        pass
                    if _urls:
                        try:
                            tree.selection_add(*_urls)
                        except Exception:
                            pass

                dialog.after(0, _after_find_similar)

            def _select_tree_row_for_key(target_key: str):
                u = (target_key or "").strip()
                if not u:
                    return
                try:
                    for item in tree.get_children():
                        t = _treeview_item_tags_safe(tree, item)
                        if t and t[0] == u:
                            tree.selection_set(item)
                            tree.see(item)
                            tree.focus(item)
                            break
                except tk.TclError:
                    pass

            # 操作按钮区（整行宽；发布状态单独一行，避免挤掉右侧按钮）
            button_frame = ttk.Frame(topic_frame)
            button_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=5, pady=(8, 5))

            publish_info_var = tk.StringVar(value="发布: …")
            pub_row = ttk.Frame(button_frame)
            pub_row.pack(fill=tk.X, anchor=tk.W)
            ttk.Label(pub_row, textvariable=publish_info_var).pack(side=tk.LEFT, anchor=tk.W)

            right_btns = ttk.Frame(button_frame)
            right_btns.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))

            def on_review_publish():
                imap = _scan_input_media_publish_map()
                mp4 = _resolve_review_publish_mp4_path(video_detail, imap)
                if not mp4 or not os.path.isfile(mp4):
                    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "")
                    messagebox.showwarning(
                        "提示",
                        "当前不可审阅：请先在「摘要」窗拖入 MP4 加水印，或在 publish/gen_video 下放好\n"
                        f"与本条 YouTube id 同名的成品：\n"
                        f"{gen_dir or '(未配置路径)'}\\\\<视频id>.mp4\n\n"
                        "（仍支持旧逻辑：INPUT_MEDIA_PATH 下 __*__.txt + 同名 .mp4）",
                        parent=summary_window,
                    )
                    return

                def after_publish():
                    try:
                        populate_tree()
                    except Exception:
                        pass
                    try:
                        refresh_publish_row()
                    except Exception:
                        pass
                    try:
                        _select_tree_row_for_key(_channel_list_row_tree_key(video_detail))
                    except Exception:
                        pass
                    try:
                        update_selection_count()
                    except Exception:
                        pass

                self._open_publish_review_dialog(summary_window, mp4, video_detail, after_publish)

            pub_btn = ttk.Button(right_btns, text="审阅发布", command=on_review_publish)
            pub_btn.pack(side=tk.LEFT, padx=(0, 6))

            def refresh_publish_row():
                if not summary_window.winfo_exists():
                    return
                imap = _scan_input_media_publish_map()
                txt, st, _ = _publish_cell_display(video_detail, imap)
                mp_resolved = _resolve_review_publish_mp4_path(video_detail, imap)
                urow = (video_detail.get("url") or "").strip()
                pub_hist = (video_detail.get("publish") or "").strip()
                ud = (video_detail.get("upload_date") or "").strip()
                if st == "published" or pub_hist or urow or ud:
                    parts = []
                    if urow:
                        parts.append(
                            f"url:{urow[:64]}{'…' if len(urow) > 64 else ''}"
                        )
                    if pub_hist:
                        parts.append(f"记录:{pub_hist}")
                    if ud:
                        parts.append(f"upload_date:{ud}")
                    extra = ("  |  " + "  |  ".join(parts)) if parts else ""
                    publish_info_var.set(f"发布: {txt}{extra}")
                else:
                    publish_info_var.set(f"发布: {txt}")

                btn_state = (
                    tk.NORMAL
                    if mp_resolved and os.path.isfile(mp_resolved)
                    else tk.DISABLED
                )
                try:
                    pub_btn.config(state=btn_state)
                except tk.TclError:
                    pass
                try:
                    refresh_feature_media_row()
                except Exception:
                    pass

            refresh_publish_row()
            if isinstance(summary_window._summary_drop_ctx, dict):
                summary_window._summary_drop_ctx["refresh_publish_row"] = refresh_publish_row

            ttk.Label(right_btns, text="  |").pack(side=tk.LEFT, padx=(2, 2))
            ttk.Label(right_btns, text="|  ").pack(side=tk.LEFT, padx=(2, 2))

            ttk.Button(right_btns, text="保存", command=save_story_info).pack(side=tk.LEFT, padx=(0, 5))

            def _after_content_field_saved():
                try:
                    populate_tree()
                except Exception:
                    pass

            def do_review_analyzed():
                def _after_content_summary():
                    do_re_category()

                self.open_content_field_editor(
                    summary_window,
                    video_detail,
                    "analyzed_content",
                    on_saved=_after_content_field_saved,
                    on_content_summarized=_after_content_summary,
                )

            def do_review_scene():
                self.open_content_field_editor(
                    summary_window,
                    video_detail,
                    "scene_content",
                    on_saved=_after_content_field_saved,
                    main_character=(character_var.get() or "").strip(),
                    channel_path=self.channel_path or "",
                )

            def do_review_script():
                self._show_transcript_script_viewer(summary_window, video_detail)

            ttk.Button(right_btns, text="找类似", command=on_find_similar_cases).pack(side=tk.LEFT, padx=(5, 5))


            ttk.Label(right_btns, text="  |").pack(side=tk.LEFT, padx=(2, 2))
            ttk.Label(right_btns, text="|  ").pack(side=tk.LEFT, padx=(2, 2))

            image_en_btn = ttk.Button(right_btns, text="风格", command=lambda: copy_style_character())
            image_en_btn.pack(side=tk.LEFT, padx=(0, 5))

            ttk.Button(right_btns, text="分析", command=do_review_analyzed).pack(
                side=tk.LEFT, padx=(5, 5)
            )
            ttk.Button(right_btns, text="场景", command=do_review_scene).pack(
                side=tk.LEFT, padx=(5, 5)
            )
            ttk.Button(right_btns, text="故事", command=do_story_view).pack(side=tk.LEFT, padx=(5, 5))
            ttk.Button(right_btns, text="诗歌", command=do_poem_view).pack(side=tk.LEFT, padx=(5, 5))
            ttk.Button(right_btns, text="IMAGE", command=do_image_prompt).pack(
                side=tk.LEFT, padx=(5, 5)
            )

            ttk.Label(right_btns, text="  |").pack(side=tk.LEFT, padx=(2, 2))
            ttk.Label(right_btns, text="|  ").pack(side=tk.LEFT, padx=(2, 2))
            ttk.Button(right_btns, text="脚本", command=do_review_script).pack(
                side=tk.LEFT, padx=(5, 5)
            )

            
            # 输入列（分类/子类型/标签/关联ID）均分剩余宽度
            for _c in (1, 3):
                topic_frame.columnconfigure(_c, weight=1, uniform='topic_inputs')
            
            # 初始化子类型选项
            if topic_category:
                update_subtypes()
            
            prompt_choice_frame = ttk.Frame(main_frame)
            prompt_choice_frame.pack(anchor=tk.W, pady=(0, 5))

            ttk.Label(prompt_choice_frame, text="主角").pack(side=tk.LEFT, padx=(0, 5))
            char_labels = list(config.CHARACTER_PERSON_OPTIONS)
            character_var = tk.StringVar(value=char_labels[0])
            character_combo = ttk.Combobox(prompt_choice_frame, textvariable=character_var, values=char_labels, state="readonly", width=12)
            character_combo.pack(side=tk.LEFT, padx=(0, 5))
            character_combo.current(0)

            ttk.Label(prompt_choice_frame, text="   |   ").pack(side=tk.LEFT, padx=(10, 10))

            # 画面风格 / 旁白 / Host 显示：与欢迎屏一致，只读（LAST_*）
            ttk.Label(prompt_choice_frame, text="风格:").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(prompt_choice_frame, text=project_manager.LAST_VISUAL_STYLE, width=16, anchor="w").pack(side=tk.LEFT, padx=(0, 5))

            ttk.Label(prompt_choice_frame, text="   |   ").pack(side=tk.LEFT, padx=(10, 10))

            # 旁白：欢迎屏 narrator；Host 显示：欢迎屏选择
            ttk.Label(prompt_choice_frame, text="旁白").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(prompt_choice_frame, text=str(project_manager.LAST_NARRATOR or ""), width=14, anchor="w").pack(side=tk.LEFT, padx=(0, 5))

            ttk.Label(prompt_choice_frame, text="   |   ").pack(side=tk.LEFT, padx=(10, 10))

            ttk.Label(prompt_choice_frame, text="HOST").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(prompt_choice_frame, text=project_manager.LAST_HOST_DISPLAY, width=18, anchor="w").pack(side=tk.LEFT, padx=(0, 5))


            def copy_style_character():
                try:
                    pending_scene: list[dict | None] = [None]

                    def _apply_scene_dict(scene_raw) -> None:
                        scene_list = scene_raw if isinstance(scene_raw, list) else []
                        if not scene_list:
                            return
                        video_detail["scene_content"] = scene_list
                        pending_scene[0] = None
                        with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                            json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                        dialog.after(0, populate_tree)

                    def _video_scene_list() -> list:
                        sc = video_detail.get("scene_content")
                        return sc if isinstance(sc, list) else []

                    has_scene = bool(_video_scene_list())

                    def _show_scene_clipboard_menu():
                        choices: list[tuple[str, str]] = [("cross_channel", "全频道剪贴板")]
                        if pending_scene[0]:
                            choices.append(
                                ("paste_scene", "将所选内容写入 scene_content (JSON)")
                            )
                        if has_scene:
                            choices.append(
                                (
                                    "gen_slideshow_instruction",
                                    f"Scene JSON → Slideshow 图像指令 ({config.llm_language_label(self.language)})",
                                )
                            )
                            choices.append(
                                (
                                    "gen_video_instruction",
                                    f"Scene JSON → Video+Audio 指令 ({config.llm_language_label(self.language)})",
                                )
                            )

                        picked = askchoice("场景 / 剪贴板", choices, parent=summary_window)
                        if not picked:
                            return
                        mode = picked[1]

                        if mode == "cross_channel":
                            picked_scene = ask_cross_channel_clipboard_pick(
                                summary_window,
                                summary_window,
                                self.channel_path or "",
                            )
                            if picked_scene is not None:
                                pending_scene[0] = picked_scene
                            _show_scene_clipboard_menu()
                            return

                        if mode == "paste_scene":
                            if not pending_scene[0]:
                                messagebox.showwarning(
                                    "未选择内容",
                                    "请先在「全频道剪贴板」中选择一条 Scene JSON。",
                                    parent=summary_window,
                                )
                                _show_scene_clipboard_menu()
                                return
                            _apply_scene_dict(pending_scene[0])
                            _show_scene_clipboard_menu()
                            return

                        if mode in ("gen_slideshow_instruction", "gen_video_instruction"):
                            scene_for_gen = _video_scene_list()
                            nb_mode = (
                                "slideshow"
                                if mode == "gen_slideshow_instruction"
                                else "video"
                            )
                            self._copy_notebooklm_scene_gen_instruction(
                                parent=summary_window,
                                video_detail=video_detail,
                                scene_content=scene_for_gen,
                                nb_mode=nb_mode,
                                main_character=(character_var.get() or "").strip(),
                                channel_path=self.channel_path or "",
                            )
                            return

                    _show_scene_clipboard_menu()

                except Exception as ex:
                    show_auto_close_popup(
                        summary_window,
                        "场景/剪贴板",
                        f"操作失败: {ex}",
                        kind="error",
                    )


            def on_category_change(e):
                update_subtypes()

            category_combo.bind('<<ComboboxSelected>>', on_category_change)

            summary_window._summary_drop_ctx["nav_low_priority"] = low_priority
            if not getattr(summary_window, "_summary_nav_root_bound", False):
                _bind_ctrl_arrow_nav(summary_window)
                summary_window._summary_nav_root_bound = True
            _bind_summary_nav_subtree(main_frame)

            _register_summary_gen_media_drop_targets(summary_window, main_frame)
            _register_summary_gen_media_paste_bindings(summary_window, main_frame)

            summary_window.focus_set()

        # 绑定双击事件
        tree.bind("<Double-1>", on_double_click)
        # 绑定 Enter 键（键盘）
        tree.bind("<Return>", on_enter_key)
        if not getattr(dialog, "_summary_nav_tree_bound", False):
            _bind_ctrl_arrow_nav(tree)
            _bind_ctrl_arrow_nav(dialog)
            dialog._summary_nav_tree_bound = True
        
        # 底部按钮框架（先创建框架，按钮在后面定义函数后添加）
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)


        def update_video_list():
            """重新抓取当前频道视频列表，与现有列表比较，将新视频弹窗展示供用户勾选添加"""
            if not self.downloader.channel_list_json or not self.downloader.channel_videos:
                messagebox.showwarning("提示", "当前没有加载视频列表", parent=dialog)
                return
            channel_id = None
            for v in self.downloader.channel_videos:
                cid = (v.get('channel_id') or '').strip()
                if cid and len(cid) >= 10:
                    channel_id = cid
                    break
            if not channel_id:
                # 从任意视频重新拉取基本信息（含 channel_id）
                for v in self.downloader.channel_videos:
                    video_url = v.get('url', '').strip()
                    if video_url and ('youtube.com/watch' in video_url or 'youtu.be/' in video_url):
                        try:
                            video_data = self.downloader.get_video_detail(video_url, '')
                            if video_data:
                                cid = (video_data.get('channel_id') or '').strip()
                                if cid and len(cid) >= 10:
                                    channel_id = cid
                                    v['channel_id'] = cid
                                    for fld in ('channel', 'uploader'):
                                        if fld in video_data and video_data[fld]:
                                            v[fld] = video_data[fld]
                                    with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                        json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                                    break
                        except Exception:
                            continue
            if not channel_id:
                show_auto_close_popup(dialog, "错误", "无法获取频道ID，请使用「获取热门视频列表」重新导入频道", kind="error")
                return
            channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

            def fetch_task():
                result = self.downloader.fetch_channel_new_videos(channel_url, max_videos=5000)
                dialog.after(0, lambda: _show_new_videos_popup(result))

            def _show_new_videos_popup(result):
                if result is None:
                    show_auto_close_popup(dialog, "错误", "抓取视频列表失败", kind="error")
                    return
                new_videos, all_fetched = result
                updated_count = 0
                # 用最新抓取数据更新已有视频（观看次数、上传日期等），不浪费本次调用
                if all_fetched:
                    for v in self.downloader.channel_videos:
                        vid = v.get('id') or ''
                        if not vid:
                            t = _youtube_row_display_title(v).lower()
                            for fid, fdata in all_fetched.items():
                                if _youtube_row_display_title(fdata).lower() == t:
                                    vid = fid
                                    break
                        if vid and vid in all_fetched:
                            fetched = all_fetched[vid]
                            for fld in getattr(
                                self.downloader,
                                "YOUTUBE_META_FIELDS",
                                (
                                    "title",
                                    "url",
                                    "duration",
                                    "view_count",
                                    "uploader",
                                    "channel",
                                    "channel_id",
                                    "upload_date",
                                    "thumbnail",
                                    "description",
                                ),
                            ):
                                if fld == "upload_date" and not _should_update_upload_date(v):
                                    continue
                                if fld in fetched:
                                    v[fld] = fetched[fld]
                            v.pop("video_title", None)
                            updated_count += 1
                    if updated_count:
                        _normalize_channel_videos_for_storage(self.downloader.channel_videos, self.channel_path or "")
                        with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                            json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                        if self.downloader.channel_videos and any(v.get('upload_date') for v in self.downloader.channel_videos):
                            self.downloader.latest_date = max(
                                (datetime.strptime(v["upload_date"], "%Y%m%d") for v in self.downloader.channel_videos if v.get("upload_date")),
                                default=self.downloader.latest_date
                            )
                        populate_tree()
                if not new_videos:
                    msg = "没有发现新视频"
                    if updated_count:
                        msg += f"，已更新 {updated_count} 个现有视频的观看次数等信息"
                    show_auto_close_popup(dialog, "提示", msg + "。")
                    return

                popup = tk.Toplevel(dialog)
                popup.title("新视频 - 选择要添加的视频")
                popup.geometry("900x500")
                popup.transient(dialog)

                cols = ("title", "views", "duration", "upload_date")
                tree_frame = ttk.Frame(popup)
                tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                scrollbar = ttk.Scrollbar(tree_frame)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                new_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                        yscrollcommand=scrollbar.set, selectmode="extended")
                new_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scrollbar.config(command=new_tree.yview)

                new_tree.heading("title", text="标题")
                new_tree.heading("views", text="观看次数")
                new_tree.heading("duration", text="时长")
                new_tree.heading("upload_date", text="上传日期")
                _configure_video_pick_treeview(new_tree)

                def fmt_duration(sec):
                    if not sec:
                        return "-"
                    m, s = divmod(int(sec), 60)
                    h, m = divmod(m, 60)
                    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

                def fmt_upload_date(ud):
                    if not ud:
                        return "-"
                    ud = str(ud).replace("-", "")[:8]
                    if len(ud) == 8:
                        return f"{ud[:4]}-{ud[4:6]}-{ud[6:]}"
                    return ud or "-"

                video_to_iid = {}
                for i, v in enumerate(new_videos):
                    view_count = v.get('view_count', 0)
                    views_str = f"{view_count:,}" if isinstance(view_count, (int, float)) else str(view_count)
                    duration_str = fmt_duration(v.get('duration', 0))
                    upload_date = fmt_upload_date(v.get('upload_date', ''))
                    title = _youtube_row_display_title(v)[:120]
                    iid = new_tree.insert("", tk.END, values=(title, views_str, duration_str, upload_date))
                    video_to_iid[iid] = v

                def add_selected():
                    selected = new_tree.selection()
                    to_add = [video_to_iid[iid] for iid in selected if iid in video_to_iid]
                    if not to_add:
                        messagebox.showinfo("提示", "请至少选择一个视频", parent=popup)
                        return
                    for v in to_add:
                        self.downloader.channel_videos.append(v)
                    self.downloader.channel_videos.sort(key=lambda x: x.get('view_count', 0), reverse=True)
                    _normalize_channel_videos_for_storage(self.downloader.channel_videos, self.channel_path or "")
                    with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                        json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                    popup.destroy()
                    populate_tree()
                    show_auto_close_popup(dialog, "成功", f"已添加 {len(to_add)} 个视频到列表")

                btn_frame = ttk.Frame(popup)
                btn_frame.pack(fill=tk.X, padx=10, pady=5)
                ttk.Button(btn_frame, text="全选", command=lambda: [new_tree.selection_add(item) for item in new_tree.get_children()]).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="取消全选", command=lambda: new_tree.selection_remove(*new_tree.get_children())).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="添加选中", command=add_selected).pack(side=tk.RIGHT, padx=5)
                ttk.Button(btn_frame, text="关闭", command=popup.destroy).pack(side=tk.RIGHT, padx=5)

            show_auto_close_popup(dialog, "提示", "正在抓取频道视频列表，请稍候...")
            thread = threading.Thread(target=fetch_task)
            thread.daemon = True
            thread.start()


        def fetch_info_selected():
            """对选中的、无 upload_date 的视频重新拉取元信息，更新后保存列表"""
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return
            videos = []
            for video_detail in _unique_video_details_from_tree_selection():
                if video_detail and not (video_detail.get('upload_date') or '').strip():
                    videos.append(video_detail)
            if not videos:
                show_auto_close_popup(dialog, "提示", "所选视频均已包含 upload_date，无需更新")
                return
            if not messagebox.askyesno("确认", f"将为 {len(videos)} 个视频重新拉取 upload_date 等信息，是否继续？", parent=dialog):
                return
            self.downloader._check_and_update_cookies(wait_forever=False)
            total = len(videos)
            success_count = [0]
            failed_count = [0]

            def fetch_task():
                for idx, video_detail in enumerate(videos, 1):
                    try:
                        url = video_detail.get('url', '')
                        if not url:
                            failed_count[0] += 1
                            continue
                        _ln = _youtube_row_display_title(video_detail)
                        print(f"[{idx}/{total}] 拉取信息: {_ln[:50]}")
                        fresh = self.downloader.get_video_detail(url, self.downloader.channel_name or 'Unknown')
                        if fresh and fresh.get('upload_date'):
                            ud = str(fresh['upload_date'] or '').strip()
                            if ud:
                                if len(ud) == 10:
                                    ud = ud.replace('-', '')
                                video_detail['upload_date'] = ud[:8]
                                print(f"  ✅ 已更新 upload_date: {ud[:8]}")
                            for k in ('title', 'duration', 'view_count', 'uploader', 'channel', 'channel_id', 'thumbnail', 'description'):
                                if k in fresh and fresh[k] is not None:
                                    video_detail[k] = fresh[k]
                            video_detail.pop('video_title', None)
                            success_count[0] += 1
                        else:
                            failed_count[0] += 1
                        try:
                            with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"  ❌ 失败: {e}")
                        failed_count[0] += 1
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                dialog.after(
                    0,
                    lambda: [
                        populate_tree(),
                        show_auto_close_popup(
                            dialog,
                            "完成",
                            f"成功: {success_count[0]} 个，失败: {failed_count[0]} 个",
                        ),
                    ],
                )

            threading.Thread(target=fetch_task, daemon=True).start()

        def download_selected():
            if not tree.selection():
                return
            # 获取选中视频的信息（按 URL 去重）
            selected_videos = _unique_video_details_from_tree_selection()
            # filter out the videos that are already downloaded
            def needs_download(video):
                audio_path = video.get('audio_path') or ''
                return not audio_path or not os.path.exists(audio_path)
            
            selected_videos = [video for video in selected_videos if needs_download(video)]
            if not selected_videos:
                return
            
            # 确认下载
            if not messagebox.askyesno("确认下载", f"确定要下载 {len(selected_videos)} 个视频吗？", parent=dialog):
                return
                    
            self.downloader._check_and_update_cookies()

            total = len(selected_videos)
            completed = [0]
            failed = [0]

            def download_task():
                for idx, video_detail in enumerate(selected_videos, 1):
                    try:
                        dn = _youtube_row_display_title(video_detail)
                        # 已存在 mp3 则跳过
                        prefix = self.downloader.generate_video_prefix(video_detail)
                        mp3_path = f"{self.youtube_dir}/media/{prefix}.mp3"
                        if os.path.exists(mp3_path):
                            video_detail['audio_path'] = mp3_path
                            video_detail["audio_download_status"] = "success"
                            completed[0] += 1
                            print(f"[{idx}/{total}] 跳过（已存在）: {dn}")
                            try:
                                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                            continue
                        print(f"[{idx}/{total}] 下载: {dn}")
                        file_path = self.downloader.download_audio_only(video_detail)
                        if file_path and os.path.exists(file_path):
                            file_fix = self.youtube_dir + "/media/" + self.downloader.generate_video_prefix(video_detail)+".mp3"
                            os.rename(file_path, file_fix)
                            video_detail['audio_path'] = file_fix
                            file_path = file_fix
                        #if file_path and os.path.exists(file_path):
                        #    video_detail['video_path'] = file_path
                        #    video_detail['audio_path'] = self.downloader.ffmpeg_audio_processor.extract_audio_from_video(file_path, "mp3")
                        
                        if file_path and os.path.exists(file_path):
                            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                            print(f"✅ 完成: {os.path.basename(file_path)} ({file_size:.1f} MB)")
                            video_detail["audio_download_status"] = "success"
                            completed[0] += 1
                            try:
                                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                        else:
                            print(f"❌ 失败: {dn}")
                            video_detail["audio_download_status"] = "failed"
                            failed[0] += 1
                        
                    except Exception as e:
                        print(f"❌ 错误: {_youtube_row_display_title(video_detail)} - {str(e)}")
                        video_detail["audio_download_status"] = "failed"
                        failed[0] += 1
                
                # 下载完成
                print(f"\n{'='*50}")
                print(f"批量下载完成！")
                print(f"成功: {completed[0]} 个")
                print(f"失败: {failed[0]} 个")
                
                with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
                    json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
                    print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")
                # 在主线程中刷新列表
                dialog.after(0, populate_tree)
            
            # 在后台线程中下载
            thread = threading.Thread(target=download_task)
            thread.daemon = True
            thread.start()


        _TRANSCRIPT_FILE_SUFFIXES = [
            ".srt",
            ".zh.srt",
            ".en.srt",
            ".json",
            ".zh.json",
            ".en.json",
            ".txt",
        ]

        def _video_already_has_transcript(video_detail):
            if (video_detail.get("transcribed_file") or "").strip():
                self.update_text_content(video_detail)
                return True
            if self.match_media_file(
                video_detail, "transcribed_file", _TRANSCRIPT_FILE_SUFFIXES
            ):
                self.update_text_content(video_detail)
                return True
            return False

        def _save_channel_list_json():
            try:
                with open(self.downloader.channel_list_json, "w", encoding="utf-8") as f:
                    json.dump(
                        self.downloader.channel_videos,
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
            except Exception:
                pass

        def _sync_transcribe_upload_date(video_detail):
            if (
                video_detail.get("upload_date")
                and _should_update_upload_date(video_detail)
            ):
                for v in self.downloader.channel_videos:
                    if v.get("url") == video_detail.get("url"):
                        v["upload_date"] = video_detail["upload_date"]
                        break

        def _apply_transcribe_success(video_detail, transcribed_file):
            self.update_text_content(video_detail, transcribed_file)
            _sync_transcribe_upload_date(video_detail)
            _save_channel_list_json()

        def _collect_videos_needing_transcript(*, require_audio=False):
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return None
            videos = []
            for video_detail in _unique_video_details_from_tree_selection():
                if _video_already_has_transcript(video_detail):
                    continue
                if require_audio and not self.downloader._ensure_audio_path(video_detail):
                    continue
                videos.append(video_detail)
            return videos

        def _run_transcribe_batch(
            videos_to_transcribe,
            *,
            task_name,
            confirm_title,
            confirm_verb,
            empty_warning,
            transcribe_fn,
            fail_message,
            pre_task=None,
        ):
            if videos_to_transcribe is None:
                return
            if not videos_to_transcribe:
                messagebox.showwarning("提示", empty_warning, parent=dialog)
                return
            message = f"将{confirm_verb} {len(videos_to_transcribe)} 个视频\n\n是否继续？"
            if not messagebox.askyesno(confirm_title, message, parent=dialog):
                return
            if pre_task:
                pre_task()

            def task():
                success_count = 0
                failed_count = 0
                try:
                    for video_detail in videos_to_transcribe:
                        time.sleep(0.05)
                        try:
                            transcribed_file = transcribe_fn(video_detail)
                            if transcribed_file:
                                print(f"  ✅ {task_name}成功")
                                _apply_transcribe_success(video_detail, transcribed_file)
                                success_count += 1
                            else:
                                print(f"  ❌ {fail_message}")
                                failed_count += 1
                        except Exception as e:
                            print(f"  ❌ {task_name}失败: {str(e)}")
                            failed_count += 1
                    _save_channel_list_json()
                    print(f"\n{'='*50}")
                    print(f"{task_name}完成！成功: {success_count} 个，失败: {failed_count} 个")
                finally:
                    def _refresh():
                        populate_tree()
                        try:
                            show_auto_close_popup(
                                dialog,
                                f"{task_name}完成",
                                f"成功: {success_count} 个，失败: {failed_count} 个",
                            )
                        except Exception:
                            pass

                    dialog.after(0, _refresh)

            threading.Thread(target=task, daemon=True).start()

        def audio_transcribe_selected():
            _run_transcribe_batch(
                _collect_videos_needing_transcript(require_audio=True),
                task_name="音频转录",
                confirm_title="确认音频转录",
                confirm_verb="用本地音频转录",
                empty_warning="没有可音频转录的视频（需已下载音频且尚未转录）",
                transcribe_fn=lambda vd: self.downloader.transcribe_audio_detail(
                    vd, self.language
                ),
                fail_message="音频转录失败",
            )

        def transcribe_selected():
            _run_transcribe_batch(
                _collect_videos_needing_transcript(require_audio=False),
                task_name="转录",
                confirm_title="确认转录",
                confirm_verb="转录",
                empty_warning="没有可转录的视频",
                transcribe_fn=lambda vd: self.downloader.transcribe_video_detail(
                    vd, self.language, batch_mode=True
                ),
                fail_message=(
                    "转录失败：无法下载字幕或音频转录失败"
                    if config.TRANSCRIBE_FALLBACK_TO_AUDIO
                    else "转录失败：无法下载字幕（音频转录 fallback 已关闭）"
                ),
                pre_task=lambda: (
                    self.downloader.reset_batch_transcribe_strategy(),
                    self.downloader._check_and_update_cookies(wait_forever=False),
                ),
            )


        def tag_selected():
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            for video_detail in _unique_video_details_from_tree_selection():
                self.update_text_content(video_detail)
                self.prepare_category_for_content(video_detail, self.topic_choices)

            populate_tree()


        def list_summary():
            # new list for items in the list, only item with summary, include fields:
            # analyzed_content, title, url, topic_category, topic_subtype, tags
            summary_list = []
            seen_urls = set()
            for item in tree.get_children():
                item_tags = _treeview_item_tags_safe(tree, item)
                if not item_tags:
                    continue
                video_detail = self.get_video_detail(item_tags[0])
                if not video_detail:
                    continue
                url_key = (video_detail.get('url') or item_tags[0] or '').strip()
                if not url_key or url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                if video_detail.get("analyzed_content"):
                    summary_list.append({
                        'analyzed_content': video_detail.get("analyzed_content"),
                        'title': _youtube_row_display_title(video_detail),
                        'url': video_detail.get('url', ''),
                        'id': video_detail.get('id', ''),
                        'topic_category': video_detail.get('topic_category', ''),
                        'topic_subtype': video_detail.get('topic_subtype', ''),
                        'tags': video_detail.get('tags', ''),
                    })
            if not summary_list:
                messagebox.showwarning("提示", "没有可简表的视频", parent=dialog)
                return

            # save the summary_list to windows Download folder, file name same as channel_list_json, but with _summary.txt suffix
            with open(os.path.join(os.path.expanduser("~"), "Downloads", os.path.basename(self.downloader.channel_list_json)+"_summary.txt"), "w", encoding="utf-8") as f:
                json.dump(summary_list, f, ensure_ascii=False, indent=2)


        def summarize_selected(rewrite=False):
            if not tree.selection():
                messagebox.showwarning("提示", "请至少选择一个视频", parent=dialog)
                return

            summary_list = []
            for video_detail in _unique_video_details_from_tree_selection():
                if not rewrite and video_detail.get("analyzed_content"):
                    summary_list.append( video_detail.get("analyzed_content") )
                    continue

                if not self.generate_analyzed_content_for_video(
                    video_detail, force_rewrite=rewrite
                ):
                    continue

                summary_list.append( video_detail.get("analyzed_content") )

                self.prepare_category_for_content(video_detail, self.topic_choices)

            if summary_list:
                summaries = ""
                for i, summary_content in enumerate(summary_list):
                    summaries += f"----------------------\nCase-Story {i+1}:\n {summary_content}\n\n"

                input_media_path = config.INPUT_MEDIA_PATH
                file_path = os.path.join(input_media_path, 'adjust_classification_on_case_study_summaries.txt')
                if os.path.exists(file_path):
                    os.remove(file_path)
                with open(file_path, 'w', encoding='utf-8') as f:
                    classification_prompt = "Attached is the existing topics classification, each topic has a subtype. Below are some new case-study content, please adjust the existing topics, and then classify the new content clearly (find non-confusing category/subtype). These are typical psychological consultation problem case-studies:\n\n"
                    f.write(classification_prompt + summaries)

            populate_tree()


        # 在所有函数定义后创建按钮
        ttk.Button(bottom_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="输出简表", command=list_summary).pack(side=tk.RIGHT, padx=5)

        ttk.Button(bottom_frame, text="摘要选择", command=lambda: summarize_selected(False)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="分类选择", command=tag_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="转录选择", command=transcribe_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="音频转录", command=audio_transcribe_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="下载选择", command=download_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="信息更新", command=fetch_info_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="列表更新", command=update_video_list).pack(side=tk.RIGHT, padx=5)


    def transcribe_media(self, transcribe):
        """选择本地 MP4/MP3：预览播放 → 转写，同目录保存 TXT 并复制到剪贴板。"""
        _ = transcribe
        from gui.transcribe_media_dialog import open_transcribe_media_dialog

        path = filedialog.askopenfilename(
            parent=self.root,
            title="选择 MP4 或 MP3",
            filetypes=[
                ("音视频", "*.mp4 *.mp3"),
                ("MP4", "*.mp4"),
                ("MP3", "*.mp3"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        path = os.path.abspath(path)
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".mp4", ".mp3"):
            messagebox.showwarning("提示", "请选择 .mp4 或 .mp3 文件", parent=self.root)
            return
        open_transcribe_media_dialog(self.root, self, path)

    def download_youtube(self, transcribe, analyze):
        """下载YouTube视频并转录"""
        # 弹出对话框让用户输入URL
        dialog = tk.Toplevel(self.root)
        dialog.title("YouTube下载")
        dialog.minsize(480, 160)
        dialog.transient(self.root)
        dialog.grab_set()
        w, h = 600, 200
        dialog.update_idletasks()
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        dialog.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        
        # YouTube URL输入
        url_frame = ttk.Frame(dialog)
        url_frame.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(url_frame, text="YouTube链接:").pack(side=tk.LEFT)
        url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=url_var, width=50)
        url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        result_var = tk.StringVar(value="cancel")
        
        def on_confirm():
            url = url_var.get().strip()
            if not url:
                show_auto_close_popup(dialog, "错误", "请输入YouTube链接", kind="error")
                return
            result_var.set("confirm")
            dialog.destroy()
        
        def on_cancel():
            result_var.set("cancel")
            dialog.destroy()
        
        # 按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        ttk.Button(button_frame, text="确认", command=on_confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        # 等待对话框关闭
        self.root.wait_window(dialog)
        if result_var.get() == "cancel":
            return
        
        # 在对话框关闭后，通过 StringVar 获取值（它们仍然存在）
        video_url = url_var.get().strip()
        video_url = _normalize_youtube_watch_url(video_url)
        
        print(f"📥 开始下载YouTube视频并转录...")
        print(f"URL: {video_url}")

        self.downloader._check_and_update_cookies()
        try:
            video_data = self.downloader.get_video_detail(video_url, channel_name='')
        except Exception as e:
            err = str(e)
            print(f"❌ {err}")
            self.root.after(
                0,
                lambda m=err: show_auto_close_popup(self.root, "YouTube 下载失败", m, kind="error"),
            )
            return
        if not video_data:
            self.root.after(0, lambda: show_auto_close_popup(self.root, "错误", "获取视频详情失败", kind="error"))
            return

        if not transcribe:
            self.downloader.download_video_highest_resolution(video_data)
            return

        self._bind_yt_text_download_channel_list()

        is_new_video = self.downloader.is_video_new(video_data)
        if not is_new_video:
            print(f"✅ 视频已存在，跳过下载...")
            return

        # 1. 优先尝试下载 caption（不 fetch 基本信息、不弹窗），按 zh/zh-Hans/.../en 硬试
        transcribed_file = self.downloader.try_download_caption_with_priority(video_data)
        if transcribed_file:
            print(f"✅ 已从字幕获取文本")

        # 2. 若无 caption，按 config 决定是否下载音频并用 Whisper 转录
        if not transcribed_file and config.TRANSCRIBE_FALLBACK_TO_AUDIO:
            file_path = self.downloader.download_audio_only(video_data)
            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path) / (1024 * 1024)
                video_data["audio_path"] = file_path
                video_data["file_size_mb"] = file_size
                video_data["audio_download_status"] = "success"
            else:
                self.root.after(0, lambda: show_auto_close_popup(self.root, "错误", "视频下载失败", kind="error"))
                return
            transcribed_file = self.downloader.download_captions(
                video_data, self.language, allow_audio_fallback=True
            )
        if not transcribed_file:
            print(f"❌ YouTube视频转录失败")
            self.root.after(0, lambda: show_auto_close_popup(self.root, "错误", "YouTube视频转录失败：未生成字幕文件", kind="error"))
            return

        video_data['transcribed_file'] = transcribed_file
        print(f"✅ YouTube视频转录完成！")
        self.downloader.channel_videos.append(video_data)
        this_video_date = datetime.strptime(video_data["upload_date"], "%Y%m%d")
        if this_video_date > self.downloader.latest_date:
            self.downloader.latest_date = this_video_date
        self.update_text_content(video_data)
        analyzed_ok = False
        if analyze:
            analyzed_ok = self.generate_analyzed_content_for_video(
                video_data, force_rewrite=True
            )
            if analyzed_ok:
                print("✅ analyzed_content 已生成")
            else:
                print("⚠️ analyzed_content 未生成（文本不足或 LLM 失败）")
        _normalize_channel_videos_for_storage(self.downloader.channel_videos, self.channel_path or "")

        with open(self.downloader.channel_list_json, 'w', encoding='utf-8') as f:
            json.dump(self.downloader.channel_videos, f, ensure_ascii=False, indent=2)
            print(f"✅ 已保存更新后的视频列表到: {self.downloader.channel_list_json}")

        def _finish_download_ui():
            if analyze:
                if analyzed_ok:
                    self.show_analyzed_content_popup(video_data, parent=self.root)
                else:
                    messagebox.showwarning(
                        "分析未完成",
                        "转录已完成，但 analyzed_content 未生成（文本不足或 LLM 失败）。",
                        parent=self.root,
                    )
            else:
                show_auto_close_popup(
                    self.root,
                    "转录完成",
                    "YouTube 视频转录完成！",
                )

        try:
            self.root.update_idletasks()
            _finish_download_ui()
            self.root.update()
        except Exception:
            self.root.after(0, _finish_download_ui)
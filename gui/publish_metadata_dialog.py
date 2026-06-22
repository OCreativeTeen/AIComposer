"""YouTube 发布前：统一选择/编辑标题与描述。"""

from __future__ import annotations

import json
import threading
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.scrolledtext as scrolledtext
import tkinter.ttk as ttk
from typing import Callable

import config
import config_prompt
import project_manager

DESCRIPTION_STORY_SEPARATOR = "────────────────"

SOURCE_STORY = "story"
SOURCE_VOICEOVER = "voiceover"
SOURCE_SCENE_FULL = "scene_full"
SOURCE_ANALYZED = "analyzed"
SOURCE_REVIEW_SCRIPT = "review_script"


def resolve_publish_default_title(
    *,
    language: str,
    default_title: str = "",
    video_detail: dict | None = None,
) -> str:
    """YouTube 默认标题：story 首条 title/caption → 列表行 title → ``default_title``。"""
    lang = language or "zh"
    t = ""
    if isinstance(video_detail, dict):
        t = project_manager.story_first_entry_heading(video_detail.get("story"))
        if not t:
            t = (
                video_detail.get("title") or video_detail.get("video_title") or ""
            ).strip()
    if not t:
        t = (default_title or "").strip()
    return config.chinese_convert(t, lang) if t else ""


def build_caption_choices_from_scenes(
    scenes: list, *, max_n: int = 5
) -> tuple[list[str], list[str | None]]:
    labels = ["— 从场景字幕选择（可选）—"]
    payloads: list[str | None] = [None]
    for idx in range(min(max_n, len(scenes or []))):
        sc = scenes[idx]
        if not isinstance(sc, dict):
            continue
        cap = (sc.get("caption") or "").strip()
        if not cap:
            continue
        short = cap if len(cap) <= 48 else cap[:45] + "…"
        labels.append(f"场景 {idx + 1}: {short}")
        payloads.append(cap)
    return labels, payloads


def first_voiceover_from_scene_content(scene_content_list: list, language: str) -> str:
    """取首场景 ``voiceover`` 原文（兼容旧调用）。"""
    if not scene_content_list:
        return ""
    first = scene_content_list[0]
    if isinstance(first, dict):
        vo = (first.get("voiceover") or "").strip()
    else:
        vo = ""
    return config.chinese_convert(vo, language).strip()


def all_scene_speaking_voiceover_text(
    scene_content_list: list, language: str
) -> str:
    """全部场景的 ``speaking`` + ``voiceover``，逐场景列出。"""
    parts: list[str] = []
    for sc in scene_content_list or []:
        if not isinstance(sc, dict):
            continue
        lines: list[str] = []
        for key in ("speaking", "voiceover"):
            v = config.chinese_convert((sc.get(key) or "").strip(), language)
            if v:
                lines.append(v)
        if lines:
            parts.append("\n".join(lines))
    return "\n\n".join(parts)


def full_scene_content_text(scene_content_list: list) -> str:
    """完整 ``scene_content`` 序列化为 JSON 供编辑区展示。"""
    slim: list[dict] = []
    for item in scene_content_list or []:
        if not isinstance(item, dict):
            continue
        row = {
            k: item.get(k)
            for k in (
                "caption",
                "speaking",
                "voiceover",
                "visual",
                "ratio",
                "story",
                "action",
                "note",
            )
            if item.get(k) not in (None, "", [], {})
        }
        if row:
            slim.append(row)
    if not slim:
        return ""
    return json.dumps(slim, ensure_ascii=False, indent=2)


def append_poem_to_description(body: str, poem: str) -> str:
    body = (body or "").strip()
    poem = (poem or "").strip()
    if not poem:
        return body
    sep_block = f"\n\n{DESCRIPTION_STORY_SEPARATOR}\n\n"
    if body:
        return body + sep_block + poem
    return poem


def default_publish_description_source(
    *,
    story_raw=None,
    analyzed: str = "",
    scenes: list | None = None,
    review_script: str = "",
    language: str = "",
) -> str:
    """描述素材默认来源：审阅文稿 → 全部 story → 场景 speaking/voiceover → 分析内容 → 场景 JSON。"""
    if (review_script or "").strip():
        return SOURCE_REVIEW_SCRIPT
    if project_manager.publish_story_source_text(story_raw):
        return SOURCE_STORY
    if all_scene_speaking_voiceover_text(scenes or [], language or "zh"):
        return SOURCE_VOICEOVER
    if (analyzed or "").strip():
        return SOURCE_ANALYZED
    if scenes:
        return SOURCE_SCENE_FULL
    return SOURCE_STORY


def scene_content_list_for_publish(
    *,
    language: str,
    project_config: dict | None = None,
    workflow_scenes: list | None = None,
    video_detail: dict | None = None,
) -> list:
    """从项目配置、工作流场景或频道列表行解析 ``scene_content``。"""
    if isinstance(video_detail, dict):
        sc = video_detail.get("scene_content")
        return sc if isinstance(sc, list) else []
    pc = project_config or {}
    sc_list = pc.get("scene_content")
    if not isinstance(sc_list, list):
        sc_list = []
    scenes = workflow_scenes or []
    if not sc_list and scenes:
        sc_list = [
            {
                k: (s.get(k) or "")
                for k in ("speaking", "voiceover", "visual", "caption", "ratio")
            }
            for s in scenes
            if isinstance(s, dict)
        ]
    return sc_list


def ask_publish_metadata_then_schedule(
    parent,
    *,
    language: str,
    default_title: str,
    scene_content_list: list,
    analyzed_content: str,
    story_text: str,
    poem_text: str,
    generate_text_fn: Callable[[str, str], str],
    schedule_dialog_fn: Callable[..., tuple | None],
    caption_scenes: list | None = None,
    mp4_path_hint: str | None = None,
    review_script_text: str = "",
    video_detail: dict | None = None,
    metadata_dialog_title: str = "上传视频 — 标题与描述",
    metadata_confirm_label: str = "确定",
    schedule_dialog_title: str = "上传至 YouTube",
) -> dict | None:
    """先标题/描述，再发布时间（与 ``GUI_wf.publish_video`` 顺序一致）。

    成功返回 ``{"title", "description", "mode", "publish_at"}``；任一步取消返回 ``None``。
    """
    cap_source = caption_scenes if caption_scenes is not None else scene_content_list
    cap_labels, cap_payloads = build_caption_choices_from_scenes(cap_source)

    meta = ask_publish_title_and_description(
        parent,
        language=language,
        default_title=default_title,
        caption_labels=cap_labels,
        caption_payloads=cap_payloads,
        scene_content_list=scene_content_list,
        analyzed_content=analyzed_content,
        story_text=story_text,
        poem_text=poem_text,
        review_script_text=review_script_text,
        video_detail=video_detail,
        generate_text_fn=generate_text_fn,
        dialog_title=metadata_dialog_title,
        confirm_label=metadata_confirm_label,
    )
    if meta is None:
        return None

    choice = schedule_dialog_fn(
        parent,
        mp4_path_hint=mp4_path_hint,
        dialog_title=schedule_dialog_title,
    )
    if choice is None:
        return None
    mode, publish_at = choice
    publish_at = publish_at if mode == "scheduled" else None
    return {
        "title": meta["title"],
        "description": meta["description"],
        "mode": mode,
        "publish_at": publish_at,
    }


def _read_clipboard_text(host) -> str:
    try:
        return host.clipboard_get()
    except tk.TclError:
        return ""


def _bind_clipboard_replace_on_double_click(tx, host) -> None:
    def _on_double(_event=None):
        clip = (_read_clipboard_text(host) or "").strip()
        if not clip:
            return "break"
        tx.delete("1.0", tk.END)
        tx.insert("1.0", clip)
        return "break"

    tx.bind("<Double-Button-1>", _on_double, add="+")


def ask_publish_title_and_description(
    parent,
    *,
    language: str,
    default_title: str = "",
    caption_labels: list[str] | None = None,
    caption_payloads: list[str | None] | None = None,
    scene_content_list: list | None = None,
    analyzed_content: str = "",
    story_text: str = "",
    poem_text: str = "",
    review_script_text: str = "",
    video_detail: dict | None = None,
    generate_text_fn: Callable[[str, str], str],
    dialog_title: str = "上传视频 — 标题与描述",
    confirm_label: str = "确定",
) -> dict | None:
    """返回 ``{"title": str, "description": str}``；取消返回 ``None``。"""
    lang = language or "zh"
    scenes = scene_content_list or []
    analyzed = config.chinese_convert((analyzed_content or "").strip(), lang)
    poem = config.chinese_convert((poem_text or "").strip(), lang)
    review_script = config.chinese_convert((review_script_text or "").strip(), lang)

    story_raw = None
    if isinstance(video_detail, dict):
        story_raw = video_detail.get("story")
    if story_raw is None and (story_text or "").strip():
        story_raw = story_text
    story_source = config.chinese_convert(
        project_manager.publish_story_source_text(story_raw), lang
    )
    scene_sv = all_scene_speaking_voiceover_text(scenes, lang)

    resolved_title = resolve_publish_default_title(
        language=lang,
        default_title=default_title,
        video_detail=video_detail,
    )

    cap_labels = caption_labels or ["— 从场景字幕选择（可选）—"]
    cap_payloads = caption_payloads if caption_payloads is not None else [None]

    result_holder: dict | None = None
    dlg = tk.Toplevel(parent)
    dlg.title(dialog_title)
    dlg.geometry("860x720")
    dlg.minsize(640, 520)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.update_idletasks()
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"860x720+{(sw - 860) // 2}+{(sh - 720) // 2}")

    frm = ttk.Frame(dlg, padding=12)
    frm.pack(fill=tk.BOTH, expand=True)

    title_box = ttk.LabelFrame(frm, text="YouTube 标题", padding=8)
    title_box.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(
        title_box,
        text="可直接编辑；默认取 story 首条标题，否则用原视频标题；也可从场景字幕下拉填入。",
        wraplength=800,
    ).pack(anchor=tk.W, pady=(0, 6))

    title_var = tk.StringVar(value=resolved_title or "")
    title_entry = ttk.Entry(title_box, textvariable=title_var, width=90)
    title_entry.pack(fill=tk.X, pady=(0, 6))
    if resolved_title:
        title_entry.select_range(0, len(resolved_title))
        title_entry.icursor(tk.END)
    else:
        title_entry.icursor(0)
    title_entry.focus_set()

    if len(cap_labels) > 1:
        ttk.Label(title_box, text="从场景字幕填入：").pack(anchor=tk.W)
        cb = ttk.Combobox(title_box, values=cap_labels, state="readonly", width=86)
        cb.pack(fill=tk.X, pady=(2, 0))
        cb.set(cap_labels[0])

        def on_scene_pick(_event=None):
            i = cb.current()
            if 0 <= i < len(cap_payloads) and cap_payloads[i]:
                title_var.set(cap_payloads[i])
                title_entry.icursor(tk.END)
                title_entry.focus_set()
            cb.set(cap_labels[0])

        cb.bind("<<ComboboxSelected>>", on_scene_pick)

    desc_box = ttk.LabelFrame(frm, text="YouTube 描述", padding=8)
    desc_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    def _raw_source_text(source: str) -> str:
        if source == SOURCE_STORY:
            return story_source
        if source == SOURCE_VOICEOVER:
            return scene_sv
        if source == SOURCE_SCENE_FULL:
            return full_scene_content_text(scenes)
        if source == SOURCE_ANALYZED:
            return analyzed
        if source == SOURCE_REVIEW_SCRIPT:
            return review_script
        return ""

    def _load_source_raw(*, show_empty_warning: bool = False) -> bool:
        src = source_var.get()
        text = _raw_source_text(src)
        if not text:
            if show_empty_warning:
                if src == SOURCE_STORY:
                    messagebox.showwarning(
                        "提示", "story 内容为空。", parent=dlg
                    )
                elif src == SOURCE_VOICEOVER:
                    messagebox.showwarning(
                        "提示", "未找到场景 speaking / voiceover。", parent=dlg
                    )
                elif src == SOURCE_SCENE_FULL:
                    messagebox.showwarning(
                        "提示", "场景内容为空。", parent=dlg
                    )
                elif src == SOURCE_REVIEW_SCRIPT:
                    messagebox.showwarning(
                        "提示", "审阅文稿 / 转写内容为空。", parent=dlg
                    )
                else:
                    messagebox.showwarning(
                        "提示", "分析内容为空。", parent=dlg
                    )
            return False
        desc_tx.delete("1.0", tk.END)
        desc_tx.insert("1.0", text)
        return True

    default_source = default_publish_description_source(
        story_raw=story_raw,
        analyzed=analyzed,
        scenes=scenes,
        review_script=review_script,
        language=lang,
    )
    source_var = tk.StringVar(value=default_source)
    src_row = ttk.Frame(desc_box)
    src_row.pack(fill=tk.X, pady=(0, 6))

    ttk.Label(src_row, text="素材来源：").pack(side=tk.LEFT, padx=(0, 8))

    rb_story = ttk.Radiobutton(
        src_row,
        text="Story / 故事",
        variable=source_var,
        value=SOURCE_STORY,
        command=lambda: _load_source_raw(show_empty_warning=True),
    )
    rb_story.pack(side=tk.LEFT, padx=(0, 10))
    rb_analyzed = ttk.Radiobutton(
        src_row,
        text="分析内容",
        variable=source_var,
        value=SOURCE_ANALYZED,
        command=lambda: _load_source_raw(show_empty_warning=True),
    )
    rb_analyzed.pack(side=tk.LEFT, padx=(0, 10))
    rb_scene = ttk.Radiobutton(
        src_row,
        text="场景内容（全部）",
        variable=source_var,
        value=SOURCE_SCENE_FULL,
        command=lambda: _load_source_raw(show_empty_warning=True),
    )
    rb_scene.pack(side=tk.LEFT, padx=(0, 10))
    rb_voice = ttk.Radiobutton(
        src_row,
        text="场景 speaking & voiceover（全部）",
        variable=source_var,
        value=SOURCE_VOICEOVER,
        command=lambda: _load_source_raw(show_empty_warning=True),
    )
    rb_voice.pack(side=tk.LEFT, padx=(0, 10))
    rb_review = ttk.Radiobutton(
        src_row,
        text="审阅文稿 / 转写",
        variable=source_var,
        value=SOURCE_REVIEW_SCRIPT,
        command=lambda: _load_source_raw(show_empty_warning=True),
    )
    rb_review.pack(side=tk.LEFT)

    if not story_source:
        rb_story.state(["disabled"])
    if not analyzed:
        rb_analyzed.state(["disabled"])
    if not scenes:
        rb_voice.state(["disabled"])
        rb_scene.state(["disabled"])
    elif not scene_sv:
        rb_voice.state(["disabled"])
    if not review_script:
        rb_review.state(["disabled"])

    append_poem_var = tk.BooleanVar(value=False)
    poem_chk = ttk.Checkbutton(
        desc_box,
        text="在描述下方附加 poem / 诗歌（空两行 + 分隔线；需本条有 poem 内容）",
        variable=append_poem_var,
    )
    poem_chk.pack(anchor=tk.W, pady=(0, 6))
    if not poem:
        poem_chk.state(["disabled"])

    ttk.Label(
        desc_box,
        text="默认优先：全部 story（heart_message+speaking）→ 场景 speaking/voiceover → 分析内容；"
        "选定来源后编辑区显示原始素材（可改）。"
        "点「生成描述概述」由 LLM 根据编辑区内容生成简短 YouTube 描述；"
        "双击编辑区可用剪贴板替换全文。勾选 poem 时，确认发布前会自动在描述下方追加诗歌。",
        wraplength=800,
    ).pack(anchor=tk.W, pady=(0, 6))

    desc_tx = scrolledtext.ScrolledText(
        desc_box, wrap=tk.WORD, width=92, height=18, font=("Arial", 10)
    )
    desc_tx.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
    _bind_clipboard_replace_on_double_click(desc_tx, dlg)

    btn_row = ttk.Frame(desc_box)
    btn_row.pack(fill=tk.X)
    gen_btn = ttk.Button(btn_row, text="生成描述概述")
    gen_btn.pack(side=tk.LEFT, padx=(0, 8))

    llm_label = config.llm_language_label(lang)

    def _set_busy(busy: bool):
        state = tk.DISABLED if busy else tk.NORMAL
        try:
            gen_btn.config(state=state)
            dlg.config(cursor="watch" if busy else "")
        except tk.TclError:
            pass

    def on_generate():
        source_text = (desc_tx.get("1.0", tk.END) or "").strip()
        if not source_text:
            messagebox.showwarning(
                "提示", "编辑区无内容，请先选择素材来源或手动输入。", parent=dlg
            )
            return

        prompt = config_prompt.YOUTUBE_PUBLISH_DESCRIPTION_PROMPT.format(
            language=llm_label
        )

        def worker():
            err = [None]
            text = [""]
            try:
                out = generate_text_fn(prompt, source_text)
                text[0] = config.chinese_convert(out or "", lang).strip()
            except Exception as e:
                err[0] = e

            def done():
                _set_busy(False)
                if err[0] is not None:
                    messagebox.showerror("生成失败", str(err[0]), parent=dlg)
                    return
                if not text[0]:
                    messagebox.showwarning(
                        "提示", "LLM 未返回有效描述。", parent=dlg
                    )
                    return
                desc_tx.delete("1.0", tk.END)
                desc_tx.insert("1.0", text[0])

            dlg.after(0, done)

        _set_busy(True)
        threading.Thread(target=worker, daemon=True).start()

    gen_btn.config(command=on_generate)

    footer = ttk.Frame(frm)
    footer.pack(fill=tk.X)

    def on_confirm():
        nonlocal result_holder
        raw_title = (title_var.get() or "").strip()
        if not raw_title:
            messagebox.showwarning("提示", "请填写标题。", parent=dlg)
            return
        body = (desc_tx.get("1.0", tk.END) or "").strip()
        if not body:
            messagebox.showwarning("提示", "描述不能为空。", parent=dlg)
            return
        if append_poem_var.get() and poem:
            body = append_poem_to_description(
                config.chinese_convert(body, lang), poem
            )
        else:
            body = config.chinese_convert(body, lang)
        result_holder = {"title": raw_title, "description": body}
        dlg.destroy()

    ttk.Button(footer, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(footer, text=confirm_label, command=on_confirm).pack(side=tk.RIGHT)

    _load_source_raw()

    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
    dlg.wait_window()
    return result_holder

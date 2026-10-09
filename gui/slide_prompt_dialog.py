"""幻灯提示：单图或幻灯片，以及画面上的字。两个入口共用。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import config
import config_prompt
import project_manager
from gui.video_prompt_dialog import _place_popup_near


def open_slide_prompt_dialog(
    parent,
    anchor,
    *,
    get_scenes,
    get_style,
    copy_text,
    host_narrator: str = "",
    get_place=None,
    main_character: str = "",
    get_video_detail=None,
    get_slide_path=None,
) -> None:
    """先选目标和对画面文字。PDF 讲稿是另一组。按一次「拷贝提示词」就拷走并关闭。"""
    dlg = tk.Toplevel(parent)
    dlg.title("幻灯提示")
    dlg.transient(parent)
    dlg.resizable(False, False)
    dlg.withdraw()

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)
    hint = ttk.Label(main, wraplength=640, justify=tk.LEFT)
    hint.pack(anchor=tk.W)
    groups = ttk.Frame(main)
    groups.pack(anchor=tk.W, pady=(8, 8))
    actions = ttk.Frame(main)
    actions.pack(fill=tk.X)

    analysis_var = tk.StringVar(value="none")
    target_var = tk.StringVar(value="slideshow")
    text_var = tk.StringVar(value="none")

    analysis_box = ttk.LabelFrame(groups, text="PDF 讲稿", padding=(8, 4))
    analysis_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    ttk.Radiobutton(analysis_box, text="无", value="none", variable=analysis_var).pack(anchor=tk.W)
    for label, _template in config_prompt.SLIDE_ANALYSIS_PROMPT_CHOICES:
        ttk.Radiobutton(analysis_box, text=label, value=label, variable=analysis_var).pack(anchor=tk.W)

    target_box = ttk.LabelFrame(groups, text="目标", padding=(8, 4))
    target_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    target_buttons = []
    for value, label in config_prompt.SLIDE_FLOW_TARGET_CHOICES:
        btn = ttk.Radiobutton(target_box, text=label, value=value, variable=target_var)
        btn.pack(anchor=tk.W)
        target_buttons.append(btn)

    text_box = ttk.LabelFrame(groups, text="画面文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    text_buttons = []
    for value, label in config_prompt.SLIDE_FLOW_TEXT_CHOICES:
        btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
        btn.pack(anchor=tk.W)
        text_buttons.append(btn)

    def refresh_choices(*_args) -> None:
        analysis_on = analysis_var.get() != "none"
        for btn in target_buttons + text_buttons:
            btn.configure(state=("disabled" if analysis_on else "normal"))
        if analysis_on:
            hint.config(text="按这份 PDF 写讲稿。选好后按「拷贝提示词」。目标和画面文字先不用。")
        elif target_var.get() == "single":
            hint.config(text="单图把这些场景画进一张图。PDF 讲稿选「无」。选好后按「拷贝提示词」。")
        else:
            hint.config(text="幻灯片是每场一张图。PDF 讲稿选「无」。选好后按「拷贝提示词」。")

    def copy_prompt() -> None:
        analysis_label = (analysis_var.get() or "").strip()
        if analysis_label and analysis_label != "none":
            template = ""
            for label, body in config_prompt.SLIDE_ANALYSIS_PROMPT_CHOICES:
                if label == analysis_label:
                    template = body
                    break
            if not template:
                messagebox.showwarning("幻灯提示", "没有这条讲稿。", parent=dlg)
                return
            video_detail = get_video_detail() if callable(get_video_detail) else None
            slide_path = ""
            if callable(get_slide_path):
                slide_path = (get_slide_path() or "").strip()
            prompt = config_prompt.build_slide_analysis_clipbody(
                instruction=template,
                slide_path=slide_path,
                video_detail=video_detail if isinstance(video_detail, dict) else None,
            )
            try:
                copy_text(prompt, "slide_analysis_instruction")
            except TypeError:
                copy_text(prompt)
            except (tk.TclError, OSError):
                messagebox.showwarning("幻灯提示", "提示词没有放进剪贴板。", parent=dlg)
                return
            if not slide_path:
                messagebox.showinfo(
                    "幻灯提示",
                    "提示词已拷走。这一条还没有 PDF，路径没有写进去。",
                    parent=dlg,
                )
            dlg.destroy()
            return

        scenes = [s for s in (get_scenes() or []) if isinstance(s, dict)]
        if not scenes:
            messagebox.showwarning("幻灯提示", "没有可用场景", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]
        region, era = ("", "")
        if get_place is not None:
            try:
                region, era = get_place()
            except (TypeError, ValueError):
                region, era = ("", "")
        try:
            prompt = config_prompt.build_slide_flow_prompt(
                target=target_var.get(),
                text=text_var.get(),
                visual_style=style,
                scene_content=scenes,
                host_narrator=host_narrator or "",
                region=region or "",
                era=era or "",
                main_character=main_character or "",
            )
        except ValueError as exc:
            messagebox.showerror("幻灯提示", str(exc), parent=dlg)
            return
        try:
            copy_text(prompt)
        except (tk.TclError, OSError):
            messagebox.showwarning("幻灯提示", "提示词没有放进剪贴板。", parent=dlg)
            return
        dlg.destroy()

    ttk.Button(actions, text="拷贝提示词", command=copy_prompt).pack(side=tk.LEFT)
    analysis_var.trace_add("write", refresh_choices)
    target_var.trace_add("write", refresh_choices)
    refresh_choices()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

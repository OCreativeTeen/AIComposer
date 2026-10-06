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
) -> None:
    """先选目标和对画面文字。按一次「拷贝提示词」就拷走并关闭。"""
    dlg = tk.Toplevel(parent)
    dlg.title("幻灯提示")
    dlg.transient(parent)
    dlg.resizable(False, False)
    dlg.withdraw()

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)
    hint = ttk.Label(main, wraplength=480, justify=tk.LEFT)
    hint.pack(anchor=tk.W)
    groups = ttk.Frame(main)
    groups.pack(anchor=tk.W, pady=(8, 8))
    actions = ttk.Frame(main)
    actions.pack(fill=tk.X)

    target_var = tk.StringVar(value="slideshow")
    text_var = tk.StringVar(value="none")

    target_box = ttk.LabelFrame(groups, text="目标", padding=(8, 4))
    target_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.SLIDE_FLOW_TARGET_CHOICES:
        ttk.Radiobutton(target_box, text=label, value=value, variable=target_var).pack(anchor=tk.W)

    text_box = ttk.LabelFrame(groups, text="画面文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    for value, label in config_prompt.SLIDE_FLOW_TEXT_CHOICES:
        ttk.Radiobutton(text_box, text=label, value=value, variable=text_var).pack(anchor=tk.W)

    def refresh_choices(*_args) -> None:
        if target_var.get() == "single":
            hint.config(text="单图把这些场景画进一张图。选好后按「拷贝提示词」。")
        else:
            hint.config(text="幻灯片是每场一张图。选好后按「拷贝提示词」。")

    def copy_prompt() -> None:
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
    target_var.trace_add("write", refresh_choices)
    refresh_choices()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

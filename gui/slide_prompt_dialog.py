"""幻灯提示：叙事风格、单图或幻灯片，以及画面上的字。在工作流「本集内容」里打开。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import config
import config_prompt
import project_manager
from gui.video_prompt_dialog import _place_popup_near


# 记住上次的选择，下次打开直接用。
_LAST_CHOICE = {"narrative": "story", "visual": "use", "cast": "story"}


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
    """先选叙事风格，再选目标和画面文字。按一次「拷贝提示词」就拷走并关闭。"""
    dlg = tk.Toplevel(parent)
    dlg.title("幻灯提示")
    dlg.transient(parent)
    dlg.resizable(False, False)
    dlg.withdraw()

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)
    hint = ttk.Label(main, wraplength=760, justify=tk.LEFT)
    hint.pack(anchor=tk.W)
    groups = ttk.Frame(main)
    groups.pack(anchor=tk.W, pady=(8, 8))
    actions = ttk.Frame(main)
    actions.pack(fill=tk.X)

    narrative_var = tk.StringVar(value=_LAST_CHOICE["narrative"])
    target_var = tk.StringVar(value="slideshow")
    text_var = tk.StringVar(value="none")
    visual_var = tk.StringVar(value=_LAST_CHOICE["visual"])
    cast_var = tk.StringVar(value=_LAST_CHOICE["cast"])

    narrative_box = ttk.LabelFrame(groups, text="叙事风格", padding=(8, 4))
    narrative_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES:
        ttk.Radiobutton(narrative_box, text=label, value=value, variable=narrative_var).pack(anchor=tk.W)

    target_box = ttk.LabelFrame(groups, text="目标", padding=(8, 4))
    target_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.SLIDE_FLOW_TARGET_CHOICES:
        ttk.Radiobutton(target_box, text=label, value=value, variable=target_var).pack(anchor=tk.W)

    text_box = ttk.LabelFrame(groups, text="画面文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    text_buttons = []
    for value, label in config_prompt.SLIDE_FLOW_TEXT_CHOICES:
        btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
        btn.pack(anchor=tk.W)
        text_buttons.append(btn)

    story_groups = ttk.Frame(main)
    story_groups.pack(anchor=tk.W, pady=(0, 8), fill=tk.X)
    visual_box = ttk.LabelFrame(story_groups, text="场景描述 (visual)", padding=(8, 4))
    visual_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    cast_box = ttk.LabelFrame(story_groups, text="人物身份 (actor)", padding=(8, 4))
    cast_box.pack(side=tk.LEFT, anchor=tk.N)
    for value, label in config_prompt.SLIDE_FLOW_VISUAL_CHOICES:
        ttk.Radiobutton(visual_box, text=label, value=value, variable=visual_var).pack(anchor=tk.W)
    cast_buttons = []
    for value, label in config_prompt.SLIDE_FLOW_CAST_CHOICES:
        btn = ttk.Radiobutton(cast_box, text=label, value=value, variable=cast_var)
        btn.pack(anchor=tk.W)
        cast_buttons.append(btn)

    hints = {
        "story": "故事：人物在画面里表演，靠脸、动作和互动讲故事。人物身份固定按故事人物。",
        "narration": "叙事：人物少或没有，用图案、物件和背景文字讲。人物身份可以选。",
        "tech": "技术方案汇报：每张是一页架构、流程或对比图，按讲稿顺序排。画面文字和人物身份不用选。",
        "exec": "高管简报：每张一个结论，一个数字或图标。画面文字和人物身份不用选。",
    }

    def refresh_choices(*_args) -> None:
        narrative = narrative_var.get()
        presentation = narrative in ("tech", "exec")
        for btn in text_buttons:
            btn.configure(state=("disabled" if presentation else "normal"))
        cast_locked = presentation or narrative == "story"
        for btn in cast_buttons:
            btn.configure(state=("disabled" if cast_locked else "normal"))
        single = "单图把这些场景画进一张图。" if target_var.get() == "single" else "幻灯片是每场一张图。"
        hint.config(text=f"{hints.get(narrative, '')}\n{single}选好后按「拷贝提示词」。")

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
                narrative=narrative_var.get(),
                target=target_var.get(),
                text=text_var.get(),
                visual=visual_var.get(),
                cast=cast_var.get(),
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
        _LAST_CHOICE["narrative"] = narrative_var.get()
        _LAST_CHOICE["visual"] = visual_var.get()
        _LAST_CHOICE["cast"] = cast_var.get()
        dlg.destroy()

    ttk.Button(actions, text="拷贝提示词", command=copy_prompt).pack(side=tk.LEFT)
    narrative_var.trace_add("write", refresh_choices)
    target_var.trace_add("write", refresh_choices)
    refresh_choices()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

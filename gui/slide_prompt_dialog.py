"""幻灯提示（每场一张图的幻灯片）：叙事风格、画面文字，以及写进提示词的 visual、speaking、actor。在工作流「本集内容」里打开。"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import config
import config_prompt
import project_manager
from gui.video_prompt_dialog import _place_popup_near


_DEFAULT_CHOICE = {
    "narrative": "story",
    "target": "slideshow",  # 只做幻灯片；旧项目里存的 "single" 也按幻灯片
    "text": "none",
    "visual": True,
    "speaking": True,
    "actor": False,
    "actor_override": config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES[0][0],
}


def _clean_choice(saved) -> dict:
    """把项目里存的选择补全、校验，不认识的值用默认。"""
    choice = dict(_DEFAULT_CHOICE)
    if not isinstance(saved, dict):
        return choice
    for key, allowed in (
        ("narrative", {k for k, _ in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES}),
        ("text", {k for k, _ in config_prompt.SLIDE_FLOW_TEXT_CHOICES}),
    ):
        if saved.get(key) in allowed:
            choice[key] = saved[key]
    for key in ("visual", "speaking", "actor"):
        if key in saved:
            choice[key] = bool(saved[key])
    if saved.get("actor_override") in {label for label, _en in config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES}:
        choice["actor_override"] = saved["actor_override"]
    return choice


def pack_narrative_choices(parent, narrative_var, *, title: str = "叙事风格", padx=(0, 8)):
    """叙事风格单选。图片提示、幻灯提示、生场视频用同一组选项。"""
    box = ttk.LabelFrame(parent, text=title, padding=(8, 4))
    box.pack(side=tk.LEFT, anchor=tk.N, padx=padx)
    buttons = []
    for value, label in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES:
        btn = ttk.Radiobutton(box, text=label, value=value, variable=narrative_var)
        btn.pack(anchor=tk.W)
        buttons.append(btn)
    return box, buttons


def pack_scene_field_choices(
    parent,
    visual_var,
    speaking_var,
    actor_var,
    override_var,
    *,
    title: str = "写进提示词的内容",
):
    """visual / speaking / actor 勾选，外加「换成」人物覆盖。两个提示窗用这一份。"""
    options = ttk.LabelFrame(parent, text=title, padding=(8, 4))
    options.pack(side=tk.LEFT, anchor=tk.S)
    buttons = []
    for text, var in (
        ("场景描述 (visual)", visual_var),
        ("讲话 (speaking)", speaking_var),
    ):
        btn = ttk.Checkbutton(options, text=text, variable=var)
        btn.pack(anchor=tk.W)
        buttons.append(btn)
    # 换成别的人物：不选就用故事里原来的人物；选了就把画面里的人物族裔和年代覆盖掉。
    row = ttk.Frame(options)
    row.pack(anchor=tk.W, fill=tk.X)
    actor_btn = ttk.Checkbutton(row, text="人物 (actor)", variable=actor_var)
    actor_btn.pack(side=tk.LEFT)
    buttons.append(actor_btn)
    ttk.Label(row, text="  换成").pack(side=tk.LEFT)
    labels = [label for label, _en in config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES]
    ttk.Combobox(
        row, textvariable=override_var, values=labels, state="readonly", width=20
    ).pack(side=tk.LEFT, padx=(4, 0))
    return options, buttons


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
    saved_choice=None,
    save_choice=None,
) -> None:
    """先选叙事风格，再选目标、画面文字和写进提示词的内容。

    ``saved_choice`` 是项目里记下的上次选择；``save_choice(dict)`` 在关窗或拷贝时把当前选择记回项目。
    按一次「拷贝提示词」就拷走并关闭。
    """
    dlg = tk.Toplevel(parent)
    dlg.title("幻灯提示")
    dlg.transient(parent)
    dlg.resizable(False, False)
    dlg.withdraw()

    last = _clean_choice(saved_choice)

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)
    hint = ttk.Label(main, wraplength=760, justify=tk.LEFT)
    hint.pack(anchor=tk.W)
    groups = ttk.Frame(main)
    groups.pack(anchor=tk.W, pady=(8, 8))
    bottom = ttk.Frame(main)
    bottom.pack(fill=tk.X)

    narrative_var = tk.StringVar(value=last["narrative"])
    text_var = tk.StringVar(value=last["text"])
    visual_var = tk.BooleanVar(value=last["visual"])
    speaking_var = tk.BooleanVar(value=last["speaking"])
    actor_var = tk.BooleanVar(value=last["actor"])
    override_var = tk.StringVar(value=last["actor_override"])

    pack_narrative_choices(groups, narrative_var)

    text_box = ttk.LabelFrame(groups, text="画面文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    text_buttons = []
    for value, label in config_prompt.SLIDE_FLOW_TEXT_CHOICES:
        btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
        btn.pack(anchor=tk.W)
        text_buttons.append(btn)

    pack_scene_field_choices(bottom, visual_var, speaking_var, actor_var, override_var)

    hints = {
        "story": "故事：人物在画面里演这个故事。有 actor 时，讲员是故事外的评述者，其他人物是演员。",
        "narration": "叙事：用图案、物件和背景文字讲，人物少。有 actor 时，讲员是叙述者，其他人物是嘉宾。",
        "tech": "技术方案汇报：每张是一页架构、流程或对比图。有 actor 时，讲员是汇报人。",
        "exec": "高管简报：每张一个结论，一个数字或图标。有 actor 时，讲员是汇报人。",
    }

    def refresh_choices(*_args) -> None:
        narrative = narrative_var.get()
        presentation = narrative in ("tech", "exec")
        for btn in text_buttons:
            btn.configure(state=("disabled" if presentation else "normal"))
        single = "幻灯片是每场一张图。"
        hint.config(
            text=f"{hints.get(narrative, '')}\n{single}场景描述和讲话至少选一项。选好后按「拷贝提示词」。"
        )

    def remember() -> None:
        """把当前选择记回项目，下次打开直接用。"""
        if save_choice is None:
            return
        try:
            save_choice(
                {
                    "narrative": narrative_var.get(),
                    "target": "slideshow",
                    "text": text_var.get(),
                    "visual": bool(visual_var.get()),
                    "speaking": bool(speaking_var.get()),
                    "actor": bool(actor_var.get()),
                    "actor_override": override_var.get(),
                }
            )
        except Exception as exc:  # noqa: BLE001 记不下来不影响拷贝
            print(f"幻灯提示：选择没有记下：{exc}")

    def close() -> None:
        remember()
        dlg.destroy()

    def copy_prompt() -> None:
        if not (visual_var.get() or speaking_var.get()):
            messagebox.showwarning("幻灯提示", "场景描述和讲话至少要选一项。", parent=dlg)
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
                narrative=narrative_var.get(),
                target="slideshow",
                text=text_var.get(),
                use_visual=bool(visual_var.get()),
                use_speaking=bool(speaking_var.get()),
                use_actor=bool(actor_var.get()),
                visual_style=style,
                scene_content=scenes,
                host_narrator=host_narrator or "",
                region=region or "",
                era=era or "",
                main_character=main_character or "",
                actor_override=dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), ""),
            )
        except ValueError as exc:
            messagebox.showerror("幻灯提示", str(exc), parent=dlg)
            return
        try:
            copy_text(prompt)
        except (tk.TclError, OSError):
            messagebox.showwarning("幻灯提示", "提示词没有放进剪贴板。", parent=dlg)
            return
        close()

    # 拷贝按钮放在右边，字比默认大 30%，加粗。
    base_font = tkfont.nametofont("TkDefaultFont")
    big_font = tkfont.Font(
        family=base_font.actual("family"),
        size=max(1, round(abs(base_font.actual("size")) * 1.3)),
        weight="bold",
    )
    dlg._slide_copy_font = big_font  # 防止字体对象被回收
    ttk.Style().configure("SlideCopy.TButton", font=big_font, padding=(18, 10))
    ttk.Button(bottom, text="拷贝提示词", style="SlideCopy.TButton", command=copy_prompt).pack(
        side=tk.RIGHT, anchor=tk.S
    )

    dlg.protocol("WM_DELETE_WINDOW", close)
    narrative_var.trace_add("write", refresh_choices)
    refresh_choices()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

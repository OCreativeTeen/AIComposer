"""视频提示：先选叙事风格、画面、背景、演进、运镜、动画，再打开手动窗口。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import config
import config_prompt
import project_manager


def _place_popup_near(dlg: tk.Toplevel, anchor, *, below: bool) -> None:
    dlg.withdraw()
    dlg.update_idletasks()
    try:
        anchor.update_idletasks()
        ax = int(anchor.winfo_rootx())
        ay = int(anchor.winfo_rooty())
        aw = max(int(anchor.winfo_width()), 1)
        ah = max(int(anchor.winfo_height()), 1)
    except (tk.TclError, TypeError, ValueError):
        ax = int(dlg.winfo_rootx()) + 40
        ay = int(dlg.winfo_rooty()) + 80
        aw, ah = 80, 28
    w = max(int(dlg.winfo_reqwidth()), 200)
    h = max(int(dlg.winfo_reqheight()), 80)
    sw = int(dlg.winfo_screenwidth())
    sh = int(dlg.winfo_screenheight())
    gap = 8
    if below:
        x = ax
        y = ay + ah + gap
        if y + h > sh - 8:
            y = max(8, ay - h - gap)
    else:
        x = ax + aw - w
        y = ay - h - gap
        if y < 8:
            y = min(max(8, sh - h - 8), ay + ah + gap)
    x = max(8, min(x, max(8, sw - w - 8)))
    y = max(8, min(y, max(8, sh - h - 8)))
    dlg.geometry(f"{w}x{h}+{x}+{y}")
    dlg.deiconify()
    try:
        dlg.lift()
    except tk.TclError:
        pass


def open_video_prompt_dialog(
    parent,
    anchor,
    *,
    get_scenes,
    get_style,
    copy_text,
    language: str = "",
    host_narrator: str = "",
    get_image=None,
    copy_image=None,
    open_manual=None,
    simple_actions=None,
    saved_choice=None,
    save_choice=None,
) -> None:
    """生场视频：上面是简单做法（静态画面 + 声音），下面是高级做法（先选叙事风格、画面、背景、演进、运镜、动画，
    再打开手动窗口，里面放提示词和画面）。

    simple_actions: [(按钮文字, 回调), ...]，点了就关掉本窗口再调用回调。
    ``saved_choice`` 记下上次的叙事风格；关窗或打开提示时 ``save_choice(dict)`` 记回去。
    """
    opened = [s for s in (get_scenes() or []) if isinstance(s, dict)]
    transition = opened[0].get("transition") if opened else None
    is_transition = isinstance(transition, dict) and bool(transition)

    dlg = tk.Toplevel(parent)
    dlg.title("生场视频")
    dlg.transient(parent)
    dlg.resizable(False, False)
    dlg.withdraw()

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    if simple_actions:
        simple_box = ttk.LabelFrame(main, text="简单：静态画面 + 声音", padding=(8, 6))
        simple_box.pack(fill=tk.X, pady=(0, 10))

        def _run_simple(callback) -> None:
            dlg.destroy()
            callback()

        for text, callback in simple_actions:
            ttk.Button(
                simple_box, text=text, command=lambda cb=callback: _run_simple(cb)
            ).pack(side=tk.LEFT, padx=(0, 6))

    advanced = ttk.LabelFrame(main, text="高级：生成视频提示（交给 LLM）", padding=(8, 6))
    advanced.pack(fill=tk.BOTH, expand=True)
    hint = ttk.Label(advanced, wraplength=560, justify=tk.LEFT)
    hint.pack(anchor=tk.W)
    body = ttk.Frame(advanced)
    body.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
    actions = ttk.Frame(advanced)
    actions.pack(fill=tk.X)

    saved_narrative = "story"
    if isinstance(saved_choice, dict):
        picked = saved_choice.get("narrative")
        if picked in {k for k, _ in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES}:
            saved_narrative = picked
    narrative_var = tk.StringVar(value=saved_narrative)
    frame_var = tk.StringVar(value="two" if is_transition else "one")
    bg_var = tk.StringVar(value="none")
    evolve_var = tk.StringVar(value="keep")
    camera_var = tk.StringVar(value="none")
    motion_var = tk.StringVar(value="")

    from gui.slide_prompt_dialog import pack_narrative_choices

    narrative_row = ttk.Frame(body)
    narrative_row.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
    pack_narrative_choices(narrative_row, narrative_var, padx=(0, 0))

    groups = ttk.Frame(body)
    if not is_transition:
        groups.pack(anchor=tk.W)

    picture_box = ttk.LabelFrame(groups, text="画面", padding=(8, 4))
    picture_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.VIDEO_FLOW_FRAME_CHOICES:
        ttk.Radiobutton(picture_box, text=label, value=value, variable=frame_var).pack(anchor=tk.W)

    background_box = ttk.LabelFrame(groups, text="背景", padding=(8, 4))
    background_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.VIDEO_FLOW_BACKGROUND_CHOICES:
        ttk.Radiobutton(background_box, text=label, value=value, variable=bg_var).pack(anchor=tk.W)

    evolve_box = ttk.LabelFrame(groups, text="演进", padding=(8, 4))
    evolve_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    evolve_buttons = []
    for value, label in config_prompt.VIDEO_FLOW_EVOLVE_CHOICES:
        btn = ttk.Radiobutton(evolve_box, text=label, value=value, variable=evolve_var)
        btn.pack(anchor=tk.W)
        evolve_buttons.append(btn)

    camera_box = ttk.LabelFrame(groups, text="运镜", padding=(8, 4))
    camera_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.VIDEO_FLOW_CAMERA_CHOICES:
        ttk.Radiobutton(camera_box, text=label, value=value, variable=camera_var).pack(anchor=tk.W)

    motion_box = ttk.LabelFrame(groups, text="动画", padding=(8, 4))
    motion_box.pack(side=tk.LEFT, anchor=tk.N)
    for value, label in config_prompt.VIDEO_FLOW_MOTION_CHOICES:
        ttk.Radiobutton(motion_box, text=label, value=value, variable=motion_var).pack(anchor=tk.W)

    summary = None
    if is_transition:
        summary = ttk.LabelFrame(body, text="这一场是过渡", padding=(8, 4))
        summary.pack(anchor=tk.W, fill=tk.X)
        lines = ["起始画面是上一场的尾图，终止画面是下一场的起始图。"]
        for key in ("插在", "时空", "人物", "对白", "特效"):
            value = str(transition.get(key) or "").strip()
            if value:
                lines.append(f"{key}：{value}")
        ttk.Label(summary, text="\n".join(lines), justify=tk.LEFT).pack(anchor=tk.W)

    def current_choice() -> dict:
        return {"narrative": narrative_var.get()}

    def remember() -> None:
        if save_choice is None:
            return
        try:
            save_choice(current_choice())
        except Exception as exc:  # noqa: BLE001
            print(f"视频提示：选择没有记下：{exc}")

    def refresh_choices(*_args) -> None:
        two = frame_var.get() == "two"
        for btn in evolve_buttons:
            btn.configure(state=("disabled" if two else "normal"))
        go.config(text="打开提示")
        if is_transition or two:
            hint.config(text="叙事风格决定这段视频怎么讲。多画面用起始画面和终止画面。选好后打开提示窗口，两张图和提示词都在里面。选择会记下。")
        else:
            hint.config(text="叙事风格决定这段视频怎么讲。单画面先选定演进。运镜选默认就不写镜头怎么动。选好后打开提示窗口。选择会记下。")

    def close() -> None:
        remember()
        dlg.destroy()

    def on_go() -> None:
        scenes = [s for s in (get_scenes() or []) if isinstance(s, dict)]
        if not scenes:
            messagebox.showwarning("视频提示", "没有可用场景", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]
        frames = "two" if is_transition else frame_var.get()
        try:
            if is_transition:
                prompt = config_prompt.build_transition_video_prompt(
                    visual_style=style,
                    scene_content=scenes,
                    transition=transition,
                    language=language or "",
                    host_narrator=host_narrator or "",
                    narrative=narrative_var.get(),
                )
            else:
                prompt = config_prompt.build_video_flow_prompt(
                    frames=frames,
                    background=bg_var.get(),
                    evolve=evolve_var.get(),
                    visual_style=style,
                    scene_content=scenes,
                    language=language or "",
                    host_narrator=host_narrator or "",
                    camera=camera_var.get(),
                    motion=motion_var.get(),
                    narrative=narrative_var.get(),
                )
        except ValueError as exc:
            messagebox.showerror("视频提示", str(exc), parent=dlg)
            return
        images = []
        missing = []
        if get_image is not None:
            start = get_image("clip_image") or ""
            if start:
                images.append(start)
            else:
                missing.append("起始画面")
            if frames == "two":
                end = get_image("clip_image_last") or ""
                if end:
                    images.append(end)
                else:
                    missing.append("终止画面")
        if missing:
            messagebox.showinfo(
                "视频提示",
                "这一场没有" + "、".join(missing) + "。提示窗口里只放已有的图。",
                parent=dlg,
            )
        remember()
        dlg.destroy()
        if callable(open_manual):
            open_manual(prompt, images)

    go = ttk.Button(actions, text="打开提示", command=on_go)
    go.pack(side=tk.LEFT)
    dlg.protocol("WM_DELETE_WINDOW", close)
    frame_var.trace_add("write", refresh_choices)
    refresh_choices()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

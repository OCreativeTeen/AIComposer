"""视频提示：画面、背景、演进三组选择，再按选择生成提示词。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

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
) -> None:
    """打开视频提示窗口。

    ``get_image`` 和 ``copy_image`` 都给出时，先拷画面再显示提示词。
    场景窗口没有画面文件时不传这两项，选完直接显示提示词。
    ``copy_text`` 成功后窗口关闭。
    """
    with_images = get_image is not None and copy_image is not None

    dlg = tk.Toplevel(parent)
    dlg.title("视频提示")
    dlg.transient(parent)
    dlg.resizable(False, False)
    dlg.withdraw()

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)
    hint = ttk.Label(main, wraplength=560, justify=tk.LEFT)
    hint.pack(anchor=tk.W)
    body = ttk.Frame(main)
    body.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
    actions = ttk.Frame(main)
    actions.pack(fill=tk.X)

    frame_var = tk.StringVar(value="one")
    bg_var = tk.StringVar(value="none")
    evolve_var = tk.StringVar(value="keep")
    state = {"phase": "choose", "copied_start": False, "prompt": ""}

    groups = ttk.Frame(body)
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
    evolve_box.pack(side=tk.LEFT, anchor=tk.N)
    evolve_buttons = []
    for value, label in config_prompt.VIDEO_FLOW_EVOLVE_CHOICES:
        btn = ttk.Radiobutton(evolve_box, text=label, value=value, variable=evolve_var)
        btn.pack(anchor=tk.W)
        evolve_buttons.append(btn)

    box = scrolledtext.ScrolledText(body, wrap=tk.WORD, height=12, width=64)

    def refresh_choices(*_args) -> None:
        if state["phase"] != "choose":
            return
        two = frame_var.get() == "two"
        for btn in evolve_buttons:
            btn.configure(state=("disabled" if two else "normal"))
        if not with_images:
            go.config(text="显示提示词")
            if two:
                hint.config(text="多画面用起始画面和终止画面。演进这一组先不用选。选好后显示提示词。")
            else:
                hint.config(text="单画面先选定演进。选好后显示提示词。")
            return
        if two and state["copied_start"]:
            go.config(text="拷贝终止画面")
            hint.config(text="起始画面已拷贝。再拷这一场的终止画面。拷完才显示提示词。")
            return
        state["copied_start"] = False
        go.config(text="拷贝起始画面")
        if two:
            hint.config(text="多画面用起始画面和终止画面。演进这一组先不用选。先拷起始画面，再拷终止画面。")
        else:
            hint.config(text="单画面先选定演进。选好后拷贝起始画面，提示词按这些选择来写。")

    def show_prompt() -> None:
        scenes = [s for s in (get_scenes() or []) if isinstance(s, dict)]
        if not scenes:
            messagebox.showwarning("视频提示", "没有可用场景", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]
        frames = frame_var.get()
        try:
            prompt = config_prompt.build_video_flow_prompt(
                frames=frames,
                background=bg_var.get(),
                evolve=evolve_var.get(),
                visual_style=style,
                scene_content=scenes,
                language=language or "",
                host_narrator=host_narrator or "",
            )
        except ValueError as exc:
            messagebox.showerror("视频提示", str(exc), parent=dlg)
            return
        state["prompt"] = prompt
        state["phase"] = "prompt"
        groups.pack_forget()
        box.configure(state=tk.NORMAL)
        box.delete("1.0", tk.END)
        box.insert("1.0", prompt)
        box.configure(state=tk.DISABLED)
        box.pack(fill=tk.BOTH, expand=True)
        choice = config_prompt.video_flow_choice_label(frames, bg_var.get(), evolve_var.get())
        dlg.title(f"视频提示 · {choice}")
        if with_images and frames == "two":
            hint.config(text="起始画面和终止画面已拷贝。下面是按刚才的选择写的提示词。按「拷贝提示词」拷走。")
        elif with_images:
            hint.config(text="起始画面已拷贝。下面是按刚才的选择写的提示词。按「拷贝提示词」拷走。")
        else:
            hint.config(text="下面是按刚才的选择写的提示词。按「拷贝提示词」拷走。")
        go.config(text="拷贝提示词")
        dlg.update_idletasks()
        w = max(int(dlg.winfo_reqwidth()), 560)
        h = max(int(dlg.winfo_reqheight()), 420)
        x = int(dlg.winfo_x())
        y = int(dlg.winfo_y())
        dlg.geometry(f"{w}x{h}+{x}+{y}")

    def copy_prompt() -> None:
        prompt = state["prompt"]
        if not prompt:
            return
        try:
            copy_text(prompt)
        except (tk.TclError, OSError):
            messagebox.showwarning("视频提示", "提示词没有放进剪贴板。", parent=dlg)
            return
        dlg.destroy()

    def on_go() -> None:
        if state["phase"] == "prompt":
            copy_prompt()
            return
        if not with_images:
            show_prompt()
            return
        two = frame_var.get() == "two"
        if not state["copied_start"]:
            path = get_image("clip_image") or ""
            if not path:
                messagebox.showinfo("视频提示", "这一场没有起始画面。", parent=dlg)
                return
            if not copy_image(path):
                messagebox.showwarning("视频提示", "这张图没有拷到剪贴板。", parent=dlg)
                return
            state["copied_start"] = True
            if not two:
                show_prompt()
                return
            go.config(text="拷贝终止画面")
            hint.config(text="起始画面已拷贝。再拷这一场的终止画面。拷完才显示提示词。")
            return
        path = get_image("clip_image_last") or ""
        if not path:
            messagebox.showinfo("视频提示", "这一场没有终止画面。", parent=dlg)
            return
        if not copy_image(path):
            messagebox.showwarning("视频提示", "这张图没有拷到剪贴板。", parent=dlg)
            return
        show_prompt()

    go = ttk.Button(actions, text="显示提示词", command=on_go)
    go.pack(side=tk.LEFT)
    frame_var.trace_add("write", refresh_choices)
    refresh_choices()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

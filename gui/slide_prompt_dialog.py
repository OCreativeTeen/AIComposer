"""幻灯提示（每场一张图的幻灯片）：叙事风格、画面文字，以及写进提示词的 visual、speaking、actor。在工作流「本集内容」里打开。"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import config
import config_prompt
from gui.prompt_fyi import pack_background_check
import project_manager
from gui.video_prompt_dialog import _place_popup_near


_DEFAULT_CHOICE = {
    "narrative": "narration",
    "target": "slideshow",  # 只做幻灯片；旧项目里存的 "single" 也按幻灯片
    "text": "erase",
    "visual": True,
    "speaking": True,
    "actor": False,
    "image": True,
    "actor_override": config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES[0][0],
    "output": "slides",
}

# 全集生成的产物（NotebookLM Studio）：(cli_kind, 界面名)
OUTPUT_CHOICES = (
    ("slides", "幻灯片"),
    ("audio_overview", "语音概览"),
    ("video_overview", "视频概览"),
    ("infographic", "信息图"),
)


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
    if saved.get("text") == "none":
        choice["text"] = "erase"
    for key in ("visual", "speaking", "actor", "image"):
        if key in saved:
            choice[key] = bool(saved[key])
    if saved.get("actor_override") in {label for label, _en in config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES}:
        choice["actor_override"] = saved["actor_override"]
    if saved.get("output") in {k for k, _ in OUTPUT_CHOICES}:
        choice["output"] = saved["output"]
    return choice


def pack_narrative_choices(parent, narrative_var, *, title: str = "叙事风格", padx=(0, 8), actor_var=None):
    """叙事风格单选。图片提示、幻灯提示、生场视频用同一组选项。

    给了 ``actor_var`` 就在下面加一行蓝字，跟着叙事风格和「人物」勾选变，说明这次会怎么讲。
    """
    box = ttk.LabelFrame(parent, text=title, padding=(8, 4))
    box.pack(side=tk.LEFT, anchor=tk.N, padx=padx)
    buttons = []
    for value, label in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES:
        btn = ttk.Radiobutton(box, text=label, value=value, variable=narrative_var)
        btn.pack(anchor=tk.W)
        buttons.append(btn)
    if actor_var is not None:
        mode = ttk.Label(box, foreground="#1f5fbf", wraplength=340, justify=tk.LEFT)
        mode.pack(anchor=tk.W, pady=(4, 0))

        def _update(*_a):
            try:
                mode.config(text=config_prompt.narrative_mode_text(narrative_var.get(), bool(actor_var.get())))
            except tk.TclError:
                pass

        narrative_var.trace_add("write", _update)
        actor_var.trace_add("write", _update)
        _update()
    return box, buttons


def big_submit_button(dlg, parent, command, text: str = "提交"):
    """三个提示窗共用的大「提交」按钮：字号大 30%、加粗。返回按钮，由调用方 pack。"""
    base_font = tkfont.nametofont("TkDefaultFont")
    big_font = tkfont.Font(
        family=base_font.actual("family"),
        size=max(1, round(abs(base_font.actual("size")) * 1.3)),
        weight="bold",
    )
    dlg._big_submit_font = big_font  # 保持引用，否则字体被回收
    ttk.Style().configure("SlideCopy.TButton", font=big_font, padding=(18, 10))
    return ttk.Button(parent, text=text, style="SlideCopy.TButton", command=command)


def pack_scene_field_choices(
    parent,
    visual_var,
    speaking_var,
    actor_var,
    override_var,
    *,
    title: str = "写进提示词的内容",
    anchor=tk.S,
    image_var=None,
):
    """visual / speaking / actor 勾选，外加「换成」人物覆盖。两个提示窗用这一份。"""
    options = ttk.LabelFrame(parent, text=title, padding=(8, 4))
    options.pack(side=tk.LEFT, anchor=anchor, padx=((8, 0) if anchor == tk.N else 0))
    buttons = []
    if image_var is not None:
        btn = ttk.Checkbutton(options, text="场景图片 (image)", variable=image_var)
        btn.pack(anchor=tk.W)
        buttons.append(btn)
    for text, var in (
        ("场景描述 (visual)", visual_var),
        ("讲话 (speaking)", speaking_var),
    ):
        btn = ttk.Checkbutton(options, text=text, variable=var)
        btn.pack(anchor=tk.W)
        buttons.append(btn)
    # 换成别的人物：不选就用故事里原来的人物；选了就把画面里的人物族裔和年代覆盖掉。
    actor_btn = ttk.Checkbutton(options, text="人物 (actor)", variable=actor_var)
    actor_btn.pack(anchor=tk.W)
    buttons.append(actor_btn)
    # 「换成」单独一行，缩进在人物下面。
    row = ttk.Frame(options)
    row.pack(anchor=tk.W, padx=(20, 0))
    ttk.Label(row, text="换成").pack(side=tk.LEFT)
    labels = [label for label, _en in config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES]
    ttk.Combobox(
        row, textvariable=override_var, values=labels, state="readonly", width=22
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
    open_manual=None,
) -> None:
    """先选叙事风格，再选目标、画面文字和写进提示词的内容。

    ``saved_choice`` 是项目里记下的上次选择；``save_choice(dict)`` 在关窗或拷贝时把当前选择记回项目。
    按「提交」：拷走提示词并关窗；给了 ``open_manual(prompt)`` 就再交给手工 LLM 窗口（NotebookLM 演示文稿）。
    """
    dlg = tk.Toplevel(parent)
    dlg.title("全集生成")
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
    lower = ttk.Frame(main)
    lower.pack(fill=tk.X)
    bottom = ttk.Frame(lower)
    bottom.pack(side=tk.RIGHT, anchor=tk.N, padx=(16, 0))

    narrative_var = tk.StringVar(value=last["narrative"])
    text_var = tk.StringVar(value=last["text"])
    visual_var = tk.BooleanVar(value=last["visual"])
    speaking_var = tk.BooleanVar(value=last["speaking"])
    actor_var = tk.BooleanVar(value=last["actor"])
    image_var = tk.BooleanVar(value=last["image"])
    override_var = tk.StringVar(value=last["actor_override"])
    output_var = tk.StringVar(value=last["output"])

    pack_narrative_choices(groups, narrative_var, actor_var=actor_var)

    text_box = ttk.LabelFrame(groups, text="说明文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    text_buttons = []
    for value, label in config_prompt.SLIDE_FLOW_TEXT_CHOICES:
        btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
        btn.pack(anchor=tk.W)
        text_buttons.append(btn)

    # 写进提示词的内容 放在「说明文字」右边，同一行。
    from utility.content_pdf import CONTENT_PDF_NAME, CONTENT_PDF_PATH, build_content_pdf

    pack_scene_field_choices(
        groups, visual_var, speaking_var, actor_var, override_var, anchor=tk.N,
        title=f"写进 {CONTENT_PDF_NAME} 的内容", image_var=image_var,
    )

    # 背景：地域 · 时代 · 人物（全场内容），默认勾上。
    region, era = ("", "")
    if get_place is not None:
        try:
            region, era = get_place()
        except (TypeError, ValueError):
            region, era = ("", "")
    from gui.prompt_fyi import pack_background_block

    _bg_box, bg_include_var = pack_background_block(
        main, region, era, host_narrator,
        style=(get_style() or "").strip(), actor_var=actor_var,
        initial=bool(saved_choice.get("background", True)) if isinstance(saved_choice, dict) else True,
    )
    _bg_box.pack_forget()
    _bg_box.pack(in_=lower, side=tk.LEFT, anchor=tk.N, pady=(0, 6))

    hints = {
        "story": "故事：人物在画面里演这个故事。有 actor 时，讲员是故事外的评述者，其他人物是演员。",
        "narration": "叙事：用图案、物件和背景文字讲，人物少。没有讲员时，画面独自演示场景内容，讲话当作要画出来的故事内容。有讲员时，讲员在叙述，背景画面配合讲的内容。",
        "tech": "技术方案汇报：每张是一页架构、流程或对比图。有 actor 时，讲员是汇报人。",
        "exec": "高管简报：每张一个结论，一个数字或图标。有 actor 时，讲员是汇报人。",
    }

    def refresh_choices(*_args) -> None:
        narrative = narrative_var.get()
        presentation = narrative in ("tech", "exec")
        for btn in text_buttons:
            btn.configure(state=("disabled" if presentation else "normal"))
        out_label = dict(OUTPUT_CHOICES).get(output_var.get(), "幻灯片")
        single = "幻灯片是每场一页。" if output_var.get() == "slides" else ""
        hint.config(
            text=f"{single}场景描述和讲话至少选一项。按「提交」拷贝提示词，交给 NotebookLM 生成{out_label}，完成后自动打开。"
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
                    "image": bool(image_var.get()),
                    "actor_override": override_var.get(),
                    "background": bool(bg_include_var.get()),
                    "output": output_var.get(),
                }
            )
        except Exception as exc:  # noqa: BLE001 记不下来不影响拷贝
            print(f"全集生成：选择没有记下：{exc}")

    def close() -> None:
        remember()
        dlg.destroy()

    def copy_prompt() -> None:
        if not (visual_var.get() or speaking_var.get()):
            messagebox.showwarning("全集生成", "场景描述和讲话至少要选一项。", parent=dlg)
            return
        scenes = [s for s in (get_scenes() or []) if isinstance(s, dict)]
        if not scenes:
            messagebox.showwarning("全集生成", "没有可用场景", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]
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
                region="",  # 地域/时代改由背景条件统一写入
                era="",
                main_character=main_character or "",
                actor_override=dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), ""),
                output=output_var.get(),
                content_source=CONTENT_PDF_NAME,
            )
        except ValueError as exc:
            messagebox.showerror("全集生成", str(exc), parent=dlg)
            return
        prompt = config_prompt.prepend_background_condition(
            prompt, region, era, host_narrator, include=bool(bg_include_var.get())
        )
        try:
            copy_text(prompt)
        except (tk.TclError, OSError):
            messagebox.showwarning("全集生成", "提示词没有放进剪贴板。", parent=dlg)
            return
        narrative = narrative_var.get()
        try:
            dlg.config(cursor="watch")
            dlg.update_idletasks()
            pdf_path = build_content_pdf(
                scenes,
                narrative=narrative,
                use_visual=bool(visual_var.get()),
                use_speaking=bool(speaking_var.get()),
                use_actor=bool(actor_var.get()),
                use_image=bool(image_var.get()),
                keywords=text_var.get() == "keywords" and narrative not in ("tech", "exec"),
                actor_override=dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), ""),
                dest=CONTENT_PDF_PATH,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("全集生成", f"生成 {CONTENT_PDF_NAME} 失败：{exc}", parent=dlg)
            return
        finally:
            try:
                dlg.config(cursor="")
            except tk.TclError:
                pass
        kind = output_var.get()
        nb_url = current_notebook_url()
        close()
        if callable(open_manual):
            parent.after(50, lambda: open_manual(prompt, kind, nb_url, pdf_path))

    # 提交按钮放在右下角，字比默认大 30%，加粗。
    big_submit_button(dlg, bottom, copy_prompt).pack(
        side=tk.RIGHT, anchor=tk.N
    )

    # 产物（横排单选）+ 笔记本，放在提交左边。
    from utility import notebooklm_cdp

    pick_col = ttk.Frame(bottom)
    pick_col.pack(side=tk.RIGHT, anchor=tk.N, padx=(0, 12), pady=(8, 0))
    out_row = ttk.Frame(pick_col)
    out_row.pack(anchor=tk.W)
    ttk.Label(out_row, text="生成：").pack(side=tk.LEFT)
    for value, label in OUTPUT_CHOICES:
        ttk.Radiobutton(out_row, text=label, value=value, variable=output_var).pack(side=tk.LEFT, padx=(0, 6))
    nb_row = ttk.Frame(pick_col)
    nb_row.pack(anchor=tk.W, pady=(6, 0))
    ttk.Label(nb_row, text="笔记本：").pack(side=tk.LEFT)
    notebooks = [list(notebooklm_cdp.load_cached_notebooks())]
    nb_combo = ttk.Combobox(nb_row, state="readonly", width=30)
    nb_combo.pack(side=tk.LEFT)
    nb_status = ttk.Label(nb_row, text="", foreground="gray35")

    def fill_notebooks(items) -> None:
        if items:
            notebooks[0] = list(items)
        if not notebooks[0]:
            url = ""
            try:
                url = notebooklm_cdp.notebook_url()
            except Exception:
                pass
            pref = notebooklm_cdp.saved_notebook_pref()
            if pref.get("url") or url:
                notebooks[0] = [(pref.get("title") or "（默认笔记本）", pref.get("url") or url)]
        nb_combo.configure(values=[t for t, _u in notebooks[0]])
        if notebooks[0]:
            nb_combo.current(notebooklm_cdp.pick_saved_index(notebooks[0]))

    def current_notebook_url() -> str:
        i = nb_combo.current()
        if 0 <= i < len(notebooks[0]):
            title, url = notebooks[0][i]
            notebooklm_cdp.save_notebook_pref(title, url)
            return url
        return ""

    def on_nb_pick(_e=None) -> None:
        current_notebook_url()

    nb_combo.bind("<<ComboboxSelected>>", on_nb_pick)

    def refresh_notebooks() -> None:
        nb_status.config(text="刷新中…")

        box: list = []  # 后台线程只往这里放结果；Tk 线程轮询

        def poll(n=0) -> None:
            try:
                if not dlg.winfo_exists():
                    return
            except tk.TclError:
                return
            if box:
                fill_notebooks(box[0])
                nb_status.config(text=f"{len(box[0])} 个")
            elif n < 360:  # 最多等 3 分钟（可能要先启动 Chrome）
                dlg.after(500, lambda: poll(n + 1))
            else:
                nb_status.config(text="刷新失败")

        def done(items) -> None:
            box.append(list(items))

        dlg.after(500, poll)
        notebooklm_cdp.refresh_notebooks_in_background(on_done=done)

    ttk.Button(nb_row, text="刷新", width=5, command=refresh_notebooks).pack(side=tk.LEFT, padx=(6, 0))
    nb_status.pack(side=tk.LEFT, padx=(6, 0))
    fill_notebooks([])
    refresh_notebooks()  # 打开窗口就在后台刷新（必要时启动 9222 Chrome）
    output_var.trace_add("write", refresh_choices)

    dlg.protocol("WM_DELETE_WINDOW", close)
    narrative_var.trace_add("write", refresh_choices)
    refresh_choices()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

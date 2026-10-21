"""幻灯提示（每场一张图的幻灯片）：叙事风格、画面文字，以及写进提示词的 visual、speaking、actor。在工作流「本集内容」里打开。"""

from __future__ import annotations

import os
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
    "range": "episode",
}

# 范围：本集 / 本集到结束（本集和后面各集，到项目最后一集）
RANGE_CHOICES = (
    ("episode", "本集"),
    ("to_end", "本集到结束"),
)

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
    if saved.get("range") in {k for k, _ in RANGE_CHOICES}:
        choice["range"] = saved["range"]
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
    actor_avatar_dir: str = "",
    get_scene_range=None,
    get_analysis=None,
    material_pdf: str = "",
    get_cast_block=None,
    initial_source: str = "",
    on_source_change=None,
    title: str = "全集生成",
) -> None:
    """先选叙事风格，再选目标、画面文字和写进提示词的内容。

    ``saved_choice`` 是项目里记下的上次选择；``save_choice(dict)`` 在关窗或拷贝时把当前选择记回项目。
    按「提交」：拷走提示词并关窗；给了 ``open_manual(prompt)`` 就再交给手工 LLM 窗口（NotebookLM 演示文稿）。

    ``get_scene_range(range_key)`` → ``(scenes, episodes)``：range_key 是 "episode"（本集）或 "to_end"（本集到结束），
    episodes 是和 scenes 等长的每场集名。不给就只有本集（``get_scenes``），也不显示「范围」。

    「写进 content.pdf 的内容」分两节，互斥：
    - 上面「分析内容（分析报告）」：只在 STORY 窗（给了 ``get_analysis()``）可用，默认勾上。分析报告写进 content.pdf
      （不进提示词），叙事风格固定讲述；``material_pdf``（原始材料）作为背景来源：
      ``open_manual(prompt, kind, nb_url, content_pdf, "", False, extra_sources=[material_pdf])``。
    - 下面「场景内容」：原来的场景选项（场景图片 / 场景描述 / 讲话 / 人物），规则和以前完全一样。
    魔法工作流不给 ``get_analysis``：上面一节灰掉（「只在 STORY 窗口可用」），行为和以前一样。
    「注意 / FYI」：用户临时补充的短说明，勾上才放在提示词最前面；历史存在 ``saved_choice['fyi_history']``。
    """
    story_mode = get_analysis is not None
    dlg = tk.Toplevel(parent)
    dlg.title(title)
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
    range_var = tk.StringVar(value=last["range"] if get_scene_range is not None else "episode")
    analysis_var = tk.BooleanVar(value=False)
    material_var = tk.BooleanVar(value=False)

    def scene_range() -> tuple[list, list]:
        """按「范围」取场景和每场集名。"""
        if get_scene_range is not None:
            try:
                scenes_r, groups_r = get_scene_range(range_var.get())
                scenes_r = list(scenes_r or [])
                groups_r = list(groups_r or [])
                pairs = [(s, g) for s, g in zip(scenes_r, groups_r) if isinstance(s, dict)]
                return [s for s, _g in pairs], [g for _s, g in pairs]
            except Exception as exc:  # noqa: BLE001
                print(f"全集生成：取范围场景失败，改用本集：{exc}")
        scenes_e = [s for s in (get_scenes() or []) if isinstance(s, dict)]
        return scenes_e, []

    _narr_box, narr_buttons = pack_narrative_choices(groups, narrative_var, actor_var=actor_var)
    narr_note = ttk.Label(_narr_box, text="", foreground="#1f5fbf", wraplength=340, justify=tk.LEFT)
    narr_note.pack(anchor=tk.W, pady=(4, 0))

    text_box = ttk.LabelFrame(groups, text="说明文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    text_buttons = []
    for value, label in config_prompt.SLIDE_FLOW_TEXT_CHOICES:
        btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
        btn.pack(anchor=tk.W)
        text_buttons.append(btn)

    # 写进提示词的内容 放在「说明文字」右边，同一行。
    from utility.content_pdf import (
        ACTOR_PDF_NAME, ACTOR_PDF_PATH, CONTENT_PDF_NAME, CONTENT_PDF_PATH, build_actor_pdf, build_content_pdf,
        scenes_have_images,
    )

    from utility.content_pdf import build_text_pdf

    # 写进 content.pdf 的内容：上面「分析内容（分析报告）」，下面「场景内容」，两节互斥。
    content_box = ttk.LabelFrame(groups, text=f"写进 {CONTENT_PDF_NAME} 的内容", padding=(8, 4))
    content_box.pack(side=tk.LEFT, anchor=tk.N, padx=(8, 0))
    top_box = ttk.LabelFrame(content_box, text="分析内容", padding=(8, 4))
    top_box.pack(fill=tk.X, anchor=tk.W)
    analysis_btn = ttk.Checkbutton(top_box, text="分析内容（分析报告）", variable=analysis_var)
    analysis_btn.pack(anchor=tk.W)
    analysis_hint = ttk.Label(top_box, foreground="gray40", wraplength=320, justify=tk.LEFT)
    analysis_hint.pack(anchor=tk.W)
    # 第三种：材料 PDF（这一条关联的 PDF）直接拷成 content.pdf 上传。
    mat_box = ttk.LabelFrame(content_box, text="材料 PDF", padding=(8, 4))
    mat_box.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))
    material_ok = bool(story_mode and material_pdf and os.path.isfile(material_pdf))
    material_btn = ttk.Checkbutton(mat_box, text="材料 PDF（直接上传）", variable=material_var)
    material_btn.pack(anchor=tk.W)
    ttk.Label(
        mat_box, foreground="gray40", wraplength=320, justify=tk.LEFT,
        text=(f"{os.path.basename(material_pdf)} → 拷成 {CONTENT_PDF_NAME} 上传。" if material_ok
              else ("这一条没有关联的 PDF 材料。" if story_mode else "只在 STORY 窗口可用。")),
    ).pack(anchor=tk.W)
    scene_opts, scene_buttons = pack_scene_field_choices(
        content_box, visual_var, speaking_var, actor_var, override_var, anchor=tk.N,
        title="场景内容", image_var=image_var,
    )
    scene_opts.pack_forget()
    scene_opts.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))
    scene_widgets = list(scene_buttons)

    def _collect_combos(w) -> None:
        for c in w.winfo_children():
            if isinstance(c, ttk.Combobox):
                scene_widgets.append(c)
            _collect_combos(c)

    _collect_combos(scene_opts)
    scene_hint = ttk.Label(scene_opts, foreground="gray40", wraplength=320, justify=tk.LEFT)
    scene_hint.pack(anchor=tk.W)

    analysis_len = 0
    if story_mode:
        try:
            analysis_len = len((get_analysis() or "").strip())
        except Exception:  # noqa: BLE001
            analysis_len = 0
    analysis_ok = story_mode and analysis_len > 0
    try:
        has_scenes = bool(scene_range()[0])
    except Exception:  # noqa: BLE001
        has_scenes = False
    scenes_ok = has_scenes or not story_mode  # 魔法工作流照旧（没场景时提交会提示）
    scene_vars = (image_var, visual_var, speaking_var, actor_var)
    if not story_mode:
        analysis_hint.config(text="只在 STORY 窗口可用。")
    elif not analysis_ok:
        analysis_hint.config(text="还没有分析内容。")
    else:
        analysis_hint.config(
            text=f"{analysis_len} 字，写进 {CONTENT_PDF_NAME}（不进提示词）；叙事风格固定讲述。"
            + (f"\n原始材料 {os.path.basename(material_pdf)} 另外上传，只作背景。" if material_pdf else "")
        )
    if story_mode and not has_scenes:
        scene_hint.config(text="这一条还没有场景内容（scene_content），不能用。")
    elif story_mode and has_scenes:
        scene_hint.config(text=f"已有 {len(scene_range()[0])} 场。勾选这里就改用场景内容。")
    _prev_narr = [narrative_var.get()]
    _sync_busy = [False]

    def sync_sources(*_a) -> None:
        """两节互斥：勾分析就清掉并灰掉场景选项、叙事风格固定讲述；勾任何场景选项就清掉并灰掉分析。"""
        if _sync_busy[0]:
            return
        _sync_busy[0] = True
        try:
            use_a = bool(analysis_var.get())
            any_scene = any(bool(v.get()) for v in scene_vars)
            # 有场景就可以直接勾。勾上场景选项时取消分析内容，两边仍然只写一种进 content.pdf。
            if use_a and any_scene:
                analysis_var.set(False)
                use_a = False
                narrative_var.set(_prev_narr[0] or "narration")
            if any_scene and material_var.get():
                material_var.set(False)
            analysis_btn.configure(state=("normal" if analysis_ok else "disabled"))
            material_btn.configure(state=("normal" if material_ok else "disabled"))
            scene_state = "normal" if scenes_ok else "disabled"
            for w in scene_widgets:
                try:
                    w.configure(state=("readonly" if isinstance(w, ttk.Combobox) and scene_state == "normal" else scene_state))
                except tk.TclError:
                    pass
            for btn in narr_buttons:
                btn.configure(state=("disabled" if use_a else "normal"))
            narr_note.config(text=("分析内容：固定「讲述」（只有画外旁白，画面里没有人物，也没有讲员出镜）。" if use_a else ""))
        finally:
            _sync_busy[0] = False

    def on_analysis_toggle(*_a) -> None:
        if _sync_busy[0]:
            return
        if analysis_var.get():
            _prev_narr[0] = narrative_var.get()
            _sync_busy[0] = True
            try:
                for v in scene_vars:
                    v.set(False)
                material_var.set(False)
                narrative_var.set("narration")
            finally:
                _sync_busy[0] = False
        else:
            _sync_busy[0] = True
            try:
                narrative_var.set(_prev_narr[0] or "narration")
            finally:
                _sync_busy[0] = False
        sync_sources()

    def on_material_toggle(*_a) -> None:
        """材料 PDF 和另外两种互斥：勾上就清掉分析内容和场景选项。"""
        if _sync_busy[0] or not material_var.get():
            sync_sources()
            return
        was_analysis = bool(analysis_var.get())
        _sync_busy[0] = True
        try:
            analysis_var.set(False)
            for v in scene_vars:
                v.set(False)
            if was_analysis:
                narrative_var.set(_prev_narr[0] or "narration")
        finally:
            _sync_busy[0] = False
        sync_sources()

    # 初始：先按这一条记下的内容来源；否则 STORY 有分析内容默认勾上面；STORY 没场景就把场景选项清空；魔法工作流照旧。
    if initial_source == "material" and material_ok:
        material_var.set(True)
        on_material_toggle()
    elif initial_source == "scenes" and has_scenes:
        pass
    elif analysis_ok:
        analysis_var.set(True)
        on_analysis_toggle()
    elif story_mode and not has_scenes:
        for v in scene_vars:
            v.set(False)
    analysis_var.trace_add("write", on_analysis_toggle)
    material_var.trace_add("write", on_material_toggle)
    for v in scene_vars:
        v.trace_add("write", sync_sources)
    sync_sources()

    # 范围：放在「写进 content.pdf 的内容」右边。
    if get_scene_range is not None:
        range_box = ttk.LabelFrame(groups, text="范围", padding=(8, 4))
        range_box.pack(side=tk.LEFT, anchor=tk.N, padx=(8, 0))
        for value, label in RANGE_CHOICES:
            ttk.Radiobutton(range_box, text=label, value=value, variable=range_var).pack(anchor=tk.W)

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

    # 注意 / FYI：用户临时补充的短说明（和图片 / 视频提示窗同一个控件），勾上才放在提示词最前面。
    from gui.prompt_fyi import clean_fyi_history, pack_fyi_note, prepend_fyi

    _fyi_box, get_fyi_text, fyi_include_var, get_fyi_history = pack_fyi_note(
        main, history=clean_fyi_history(saved_choice) if isinstance(saved_choice, dict) else [], pady=(0, 8)
    )
    _fyi_box.pack_forget()
    _fyi_box.pack(fill=tk.X, pady=(0, 8), before=lower)

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
        span = ""
        try:
            scenes_now, groups_now = scene_range()
            span_zh, _en = config_prompt.episode_span_labels(groups_now)
            where = span_zh or (f"第 {groups_now[0]} 集" if groups_now else "本集")
            span = f"范围：{where}，共 {len(scenes_now)} 场。"
        except Exception:  # noqa: BLE001 提示行算不出来不影响
            span = ""
        if material_var.get():
            hint.config(
                text=f"材料 PDF：{os.path.basename(material_pdf)} 拷成 {CONTENT_PDF_NAME} 上传。"
                f"按「提交」拷贝提示词，交给 NotebookLM 生成{out_label}，完成后自动打开。"
            )
            return
        if analysis_var.get():
            single = "幻灯片按分析报告的结构一部分一页。" if output_var.get() == "slides" else ""
            hint.config(
                text=f"分析内容：分析报告写进 {CONTENT_PDF_NAME} 上传（不进提示词）。{single}"
                f"按「提交」拷贝提示词，交给 NotebookLM 生成{out_label}，完成后自动打开。"
            )
            return
        hint.config(
            text=f"{span}{single}场景描述和讲话至少选一项。按「提交」拷贝提示词，交给 NotebookLM 生成{out_label}，完成后自动打开。"
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
                    "range": range_var.get(),
                    "source": current_source(),
                    "fyi_history": get_fyi_history(),
                }
            )
        except Exception as exc:  # noqa: BLE001 记不下来不影响拷贝
            print(f"全集生成：选择没有记下：{exc}")

    def current_source() -> str:
        return "material" if material_var.get() else ("analysis" if analysis_var.get() else "scenes")

    def close() -> None:
        remember()
        if callable(on_source_change):
            try:
                on_source_change(current_source())
            except Exception as exc:  # noqa: BLE001
                print(f"{title}：内容来源没有记下：{exc}")
        dlg.destroy()

    def copy_analysis_prompt() -> None:
        """分析内容：分析报告 → content.pdf（来源）；提示词只有规则（+ 背景条件 + FYI），不放分析内容。"""
        try:
            analysis = (get_analysis() or "").strip()
        except Exception:  # noqa: BLE001
            analysis = ""
        if not analysis:
            messagebox.showwarning(title, "还没有分析内容。", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]
        prompt = build_analysis_prompt_text(
            output=output_var.get(),
            text=text_var.get(),
            style=style,
            region=region,
            era=era,
            host_narrator=host_narrator or "",
            background=bool(bg_include_var.get()),
            material_pdf=material_pdf,
            fyi_text=get_fyi_text(),
            fyi_include=bool(fyi_include_var.get()),
            cast_block=_safe_cast_block(get_cast_block, output_var.get()),
        )
        try:
            copy_text(prompt)
        except (tk.TclError, OSError):
            messagebox.showwarning(title, "提示词没有放进剪贴板。", parent=dlg)
            return
        try:
            dlg.config(cursor="watch")
            dlg.update_idletasks()
            pdf_path = build_text_pdf(analysis, dest=CONTENT_PDF_PATH)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(title, f"生成 {CONTENT_PDF_NAME} 失败：{exc}", parent=dlg)
            return
        finally:
            try:
                dlg.config(cursor="")
            except tk.TclError:
                pass
        print(
            f"{title}：提交（分析内容）output={output_var.get()} 分析报告 {len(analysis)} 字 → {pdf_path}；"
            f"材料={material_pdf or '-'}；提示词 {len(prompt)} 字"
        )
        kind = output_var.get()
        nb_url = current_notebook_url()
        close()
        if callable(open_manual):
            extra_sources = [material_pdf] if material_pdf else []
            parent.after(50, lambda: open_manual(prompt, kind, nb_url, pdf_path, "", False, extra_sources=extra_sources))

    def copy_material_prompt() -> None:
        """材料 PDF：删掉 working 里旧的 content.pdf，把这一条的 PDF 拷过去改名 content.pdf，照 content.pdf 流程上传。"""
        import shutil

        if not material_ok:
            messagebox.showwarning(title, "这一条没有关联的 PDF 材料。", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]
        prompt = build_analysis_prompt_text(
            output=output_var.get(), text=text_var.get(), style=style, region=region, era=era,
            host_narrator=host_narrator or "", background=bool(bg_include_var.get()), material_pdf="",
            fyi_text=get_fyi_text(), fyi_include=bool(fyi_include_var.get()),
            cast_block=_safe_cast_block(get_cast_block, output_var.get(), "panel"),
            source_kind="material",
        )
        try:
            copy_text(prompt)
        except (tk.TclError, OSError):
            messagebox.showwarning(title, "提示词没有放进剪贴板。", parent=dlg)
            return
        pdf_path = CONTENT_PDF_PATH
        try:
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            shutil.copy2(material_pdf, pdf_path)
        except OSError as exc:
            messagebox.showerror(title, f"拷贝材料 PDF 成 {CONTENT_PDF_NAME} 失败：{exc}", parent=dlg)
            return
        print(f"{title}：提交（材料 PDF）output={output_var.get()} {material_pdf} → {pdf_path}；提示词 {len(prompt)} 字")
        kind = output_var.get()
        nb_url = current_notebook_url()
        close()
        if callable(open_manual):
            parent.after(50, lambda: open_manual(prompt, kind, nb_url, pdf_path, "", False))

    def copy_prompt() -> None:
        if material_var.get():
            copy_material_prompt()
            return
        if analysis_var.get():
            copy_analysis_prompt()
            return
        if not (visual_var.get() or speaking_var.get()):
            messagebox.showwarning("全集生成", "场景描述和讲话至少要选一项。", parent=dlg)
            return
        scenes, scene_groups = scene_range()
        if not scenes:
            messagebox.showwarning("全集生成", "没有可用场景", parent=dlg)
            return
        span_zh, _span_en = config_prompt.episode_span_labels(scene_groups)
        print(f"全集生成：范围={range_var.get()} {span_zh or '单集'} 共 {len(scenes)} 场")
        cast = config_prompt.episode_actor_cast(scenes)
        if cast and not actor_var.get():
            # 场景里有人物，但「人物」没勾：不会有 Actors / actor.pdf / Actor_Reference。说清楚，让用户选。
            names = "、".join(row["name"] for row in cast[:4]) + ("……" if len(cast) > 4 else "")
            print(f"全集生成：本集场景里有人物（{names}），但「人物 (actor)」没勾，不生成 actor.pdf，提示词里也没有人物。")
            answer = messagebox.askyesnocancel(
                "全集生成",
                f"本集场景里有人物：{names}\n\n但「人物 (actor)」没勾，这次不会生成 / 上传 actor.pdf，"
                "content.pdf 和提示词里也不写人物。\n\n是 = 勾上人物再提交\n否 = 不要人物，照样提交\n取消 = 回去改",
                parent=dlg,
            )
            if answer is None:
                return
            if answer:
                actor_var.set(True)
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
                actor_source=ACTOR_PDF_NAME,
                content_images=bool(image_var.get()) and scenes_have_images(scenes),
                episodes=scene_groups,
            )
        except ValueError as exc:
            messagebox.showerror("全集生成", str(exc), parent=dlg)
            return
        # 人物：勾了人物且场景里有 actor → 以场景为准；否则以预览窗人物面板为准。都带场景生成方案的出镜规则。
        cast_src = "scenes" if (actor_var.get() and config_prompt.episode_actor_cast(scenes)) else "panel"
        cast_block = _safe_cast_block(get_cast_block, output_var.get(), cast_src)
        if cast_block.strip():
            prompt = cast_block.strip() + "\n\n---\n\n" + (prompt or "").strip()
        prompt = config_prompt.prepend_background_condition(
            prompt, region, era, host_narrator, include=bool(bg_include_var.get())
        )
        prompt = prepend_fyi(prompt, get_fyi_text(), include=bool(fyi_include_var.get()))
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
                episodes=scene_groups,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("全集生成", f"生成 {CONTENT_PDF_NAME} 失败：{exc}", parent=dlg)
            return
        finally:
            try:
                dlg.config(cursor="")
            except tk.TclError:
                pass
        actor_pdf = ""
        # 和提示词里 Actor_Reference 同一条件：带 Actors，或讲述/汇报没有讲员时的 Silent actors；没有人物就不做。
        if config_prompt.prompt_has_cast(narrative, bool(actor_var.get()), scenes):
            try:
                _ov_label = override_var.get() if dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), "") else ""
                actor_pdf, _cast = build_actor_pdf(
                    scenes, avatar_dir=actor_avatar_dir, dest=ACTOR_PDF_PATH, override_label=_ov_label,
                    style=style,  # 形象图按画面风格分目录查：avatar/<风格>/ → Realistic/ → 根目录
                )
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("全集生成", f"生成 {ACTOR_PDF_NAME} 失败：{exc}", parent=dlg)
                return
            print(f"全集生成：{ACTOR_PDF_NAME} = {actor_pdf or '（没有人物，未生成）'}")
        elif not actor_var.get():
            print(f"全集生成：「人物 (actor)」没勾，跳过 {ACTOR_PDF_NAME}。")
        else:
            print(f"全集生成：本集没有可用的人物（叙事风格 {narrative}），跳过 {ACTOR_PDF_NAME}。")
        if not actor_pdf and "Actor_Reference:" in prompt:
            prompt = config_prompt.strip_actor_reference(prompt, ACTOR_PDF_NAME)
            try:
                copy_text(prompt)
            except (tk.TclError, OSError):
                pass
            print(f"全集生成：没有 {ACTOR_PDF_NAME}，已从提示词去掉 Actor_Reference。")
        print(
            f"全集生成：提交 output={output_var.get()} narrative={narrative} 人物={bool(actor_var.get())} "
            f"Actor_Reference={'Actor_Reference:' in prompt} content.pdf={pdf_path} actor.pdf={actor_pdf or '-'}"
        )
        kind = output_var.get()
        nb_url = current_notebook_url()
        close()
        if callable(open_manual):
            cross = bool(span_zh)  # 跨集：下载回来的 PDF「写到结束」可以接着写进后面各集
            parent.after(50, lambda: open_manual(prompt, kind, nb_url, pdf_path, actor_pdf, cross))

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
    analysis_var.trace_add("write", refresh_choices)
    range_var.trace_add("write", refresh_choices)

    dlg.protocol("WM_DELETE_WINDOW", close)
    narrative_var.trace_add("write", refresh_choices)
    refresh_choices()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)


def build_analysis_prompt_text(
    *,
    output: str = "slides",
    text: str = "erase",
    style: str = "",
    region: str = "",
    era: str = "",
    host_narrator: str = "",
    background: bool = True,
    material_pdf: str = "",
    fyi_text: str = "",
    fyi_include: bool = True,
    cast_block: str = "",
    source_kind: str = "analysis",
) -> str:
    """分析内容的完整提示词：FYI（用户补充，勾上才有）→ 背景条件 → 规则。分析报告本身在 content.pdf，不在这里。"""
    from gui.prompt_fyi import prepend_fyi
    from utility.content_pdf import CONTENT_PDF_NAME

    prompt = config_prompt.build_analysis_flow_prompt(
        output=output,
        text=text,
        visual_style=style,
        content_source=CONTENT_PDF_NAME,
        material_source=os.path.basename(material_pdf) if material_pdf else "",
    )
    if source_kind == "material":
        prompt = _analysis_to_material_wording(prompt)
    if (cast_block or "").strip():
        prompt = cast_block.strip() + "\n\n---\n\n" + (prompt or "").strip()
    prompt = config_prompt.prepend_background_condition(prompt, region, era, host_narrator, include=background)
    return prepend_fyi(prompt, fyi_text, include=fyi_include)


_MATERIAL_WORDING = (
    ("分析报告", "材料"),
    ("the analysis report", "the source material"),
    ("The analysis report", "The source material"),
    ("analysis report", "source material"),
    ("the report's", "the material's"),
    ("the report", "the material"),
    ("The report", "The material"),
    ("in the report", "in the material"),
)


def _analysis_to_material_wording(prompt: str) -> str:
    """材料 PDF 直接上传时沿用分析内容的规则，只把「分析报告」改称「材料」。"""
    for a, b in _MATERIAL_WORDING:
        prompt = prompt.replace(a, b)
    return prompt


def _safe_cast_block(get_cast_block, output: str, source: str = "panel") -> str:
    if not callable(get_cast_block):
        return ""
    try:
        try:
            return get_cast_block(output, source) or ""
        except TypeError:
            return get_cast_block(output) or ""
    except Exception as exc:  # noqa: BLE001
        print(f"生成节目:人物段失败:{exc}")
        return ""

"""图片修改（原「图片提示」）：画风改变、说明文字，以及叙事风格。叙事风格和幻灯提示、生场视频共用同一组选项。"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

import config_prompt
import project_manager
from gui.slide_prompt_dialog import pack_narrative_choices, pack_scene_field_choices
from gui.video_prompt_dialog import _place_popup_near
from gui.prompt_fyi import clean_fyi_history, pack_background_check, pack_fyi_note, prepend_fyi


_DEFAULT_CHOICE = {
    "task": "keep",
    "text": "keep",
    "narrative": "narration",
    "visual": True,
    "speaking": True,
    "actor": False,
    "actor_override": config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES[0][0],
    "fix_cast": False,  # t197u: 补全/修正人物
    "backend": "qn",  # t415u: 生图后端，默认 QN（Qwen 图片编辑，ComfyUI）
}

# t415u: 图片修改窗口里直接选生图后端。MOSS / QN 走本机 ComfyUI（config.COMFYUI_QN_URL / COMFYUI_MOSS_URL，
# 和「提高分辨率」「尾帧增强」同一台），用 config_prompt.build_comfy_* 的短英文提示 + 反向提示；Grok / Gemini 走网页，要选 Chrome 账户。
PICTURE_EDIT_BACKENDS = (
    ("qn", "QN（Qwen 图片编辑）"),
    ("moss", "MOSS"),
    ("grok", "Grok"),
    ("gemini", "Gemini"),
)
DEFAULT_PICTURE_EDIT_BACKEND = "qn"
COMFY_PICTURE_BACKENDS = ("qn", "moss")


def picture_edit_backend(value) -> str:
    """t415u: 记下的后端 → 合法值；认不出用默认 QN。"""
    b = str(value or "").strip().lower()
    return b if b in {k for k, _t in PICTURE_EDIT_BACKENDS} else DEFAULT_PICTURE_EDIT_BACKEND


def _clean_choice(saved) -> dict:
    choice = dict(_DEFAULT_CHOICE)
    if not isinstance(saved, dict):
        return choice
    if saved.get("task") in {k for k, _ in config_prompt.PICTURE_FLOW_TASK_CHOICES}:
        choice["task"] = saved["task"]
    if saved.get("text") == "remove":
        choice["text"] = "express"
    elif saved.get("text") in {k for k, _ in config_prompt.PICTURE_FLOW_TEXT_CHOICES}:
        choice["text"] = saved["text"]
    if saved.get("narrative") in {k for k, _ in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES} | {"step"}:
        choice["narrative"] = saved["narrative"]
    for key in ("visual", "speaking", "actor", "fix_cast"):
        if key in saved:
            choice[key] = bool(saved[key])
    if saved.get("actor_override") in {label for label, _en in config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES}:
        choice["actor_override"] = saved["actor_override"]
    from utility.scene_image_slots import IMAGE_CHOICE_KEYS

    if saved.get("image") in IMAGE_CHOICE_KEYS:
        choice["image"] = saved["image"]
    choice["fyi_history"] = clean_fyi_history(saved)
    choice["backend"] = picture_edit_backend(saved.get("backend"))
    choice["background"] = bool(saved.get("background", True))
    return choice


def _project_video_size() -> str:
    """项目的画面比例："1920x1080" 或 "1080x1920"（项目宽高 → story_video_size → 上次选择）。"""
    cfg = project_manager.PROJECT_CONFIG if isinstance(project_manager.PROJECT_CONFIG, dict) else {}
    try:
        w, h = int(cfg.get("video_width")), int(cfg.get("video_height"))
        if w > 0 and h > 0:
            return "1920x1080" if w >= h else "1080x1920"
    except (TypeError, ValueError):
        pass
    if cfg.get("story_video_size") in ("1920x1080", "1080x1920"):
        return cfg["story_video_size"]
    return project_manager.video_size_key()


PICTURE_SUBMIT_PREF = "picture_submit_choice"


def ask_llm_and_account(parent, pref_key: str = PICTURE_SUBMIT_PREF, title: str = "提交", extra_backends=(),
                        fixed_backend=None):
    """t129u: 小窗口选 LLM（Grok / Gemini）和 Chrome 账户。返回 (backend, account) 或 None（取消 / Esc）。
    t133u: 图片 / 视频共用；``pref_key`` 分开记上次的选择。
    t152u: ``extra_backends``（如视频的 ("minimax", "MiniMax（ComfyUI）")）不用浏览器：选中时账户灰掉，返回 (backend, "")。
    t161u: ``fixed_backend``（"grok" / "gemini"）：后端已在外面选好，只选账户（不显示 LLM 一行）。"""
    import config
    from utility import chrome_account

    try:
        last = dict(config.load_yt_tools_prefs().get(pref_key) or {})
    except Exception:  # noqa: BLE001
        last = {}
    box = tk.Toplevel(parent)
    box.title(title)
    box.transient(parent)
    box.resizable(False, False)
    no_account = {v for v, _t in extra_backends}
    valid = ("grok", "gemini") + tuple(no_account)
    llm_var = tk.StringVar(master=box, value=last.get("llm") if last.get("llm") in valid else "grok")
    if fixed_backend:
        llm_var.set(fixed_backend)
    acct_var = tk.StringVar(master=box, value=chrome_account.normalize(last.get("account") or ""))
    frm = ttk.Frame(box, padding=14)
    frm.pack(fill=tk.BOTH, expand=True)
    if not fixed_backend:
        row1 = ttk.LabelFrame(frm, text="LLM", padding=(8, 4))
        row1.pack(fill=tk.X)
        for v, t in (("grok", "Grok"), ("gemini", "Gemini")) + tuple(extra_backends):
            ttk.Radiobutton(row1, text=t, value=v, variable=llm_var).pack(side=tk.LEFT, padx=(0, 12))
    row2 = ttk.LabelFrame(frm, text="账户（Chrome 用户）", padding=(8, 4))
    row2.pack(fill=tk.X, pady=(0 if fixed_backend else 8, 0))
    acct_radios = []
    for v, t in chrome_account.ACCOUNTS:
        ok = bool(chrome_account.profile_dir(v))
        rb = ttk.Radiobutton(row2, text=t + ("" if ok else "（还没建）"), value=v, variable=acct_var)
        rb.pack(anchor=tk.W)
        acct_radios.append(rb)
    res = {"v": None}

    def _sync_account(*_a):
        flag = ["disabled"] if llm_var.get() in no_account else ["!disabled"]
        for rb in acct_radios:
            rb.state(flag)

    llm_var.trace_add("write", _sync_account)
    _sync_account()

    def go(_e=None):
        if llm_var.get() in no_account:
            res["v"] = (llm_var.get(), "")
            try:
                config.save_yt_tools_prefs({pref_key: {"llm": llm_var.get(), "account": acct_var.get()}})
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 提交选择没有记下：{exc}")
            box.destroy()
            return
        acct = acct_var.get()
        if not chrome_account.profile_dir(acct):
            messagebox.showwarning("提交", chrome_account.missing_profile_message(acct), parent=box)
            return
        res["v"] = (llm_var.get(), acct)
        try:
            config.save_yt_tools_prefs({pref_key: {"llm": llm_var.get(), "account": acct}})
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 提交选择没有记下：{exc}")
        box.destroy()

    btns = ttk.Frame(frm)
    btns.pack(fill=tk.X, pady=(12, 0))
    ok_btn = ttk.Button(btns, text="提交", command=go, default="active")
    ok_btn.pack(side=tk.RIGHT)
    ttk.Button(btns, text="取消", command=box.destroy).pack(side=tk.RIGHT, padx=(0, 8))
    box.bind("<Return>", go)
    box.bind("<Escape>", lambda _e: box.destroy())
    box.update_idletasks()
    try:
        x = parent.winfo_rootx() + (parent.winfo_width() - box.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - box.winfo_height()) // 2
        box.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass
    ok_btn.focus_set()
    box.grab_set()
    parent.wait_window(box)
    return res["v"]


PICTURE_EDIT_MODES = (
    ("modify", "修改图片",
     "按画风、说明文字（说明文字 / 关键字做背景 等）和内容来源（场景描述里的 视觉 / 讲话 / 人物）修改这张图。"),
    ("cover", "从封面提取",
     "把现在的图当封面，从里面取出这一场的画面。不加字，不改画风。"),
    ("cast", "补全/修正人物",
     "按 视觉、讲话 和人物肖像图，补上缺的人物或改正对不上的人物。不加字，不改画风，不画对话泡泡。"),
    ("portrait", "提取人物肖像",
     "从当前场景图里重新提取每个人物的头部肖像，已有肖像也重新提取；满意就确定替换，不满意就忽略，保留原来的肖像。"),
    ("upscale", "提高分辨率",
     "按原图比例提高到 1920 级（长边 1920，16:9 = 1920x1080），只加清晰度和细节；构图、内容、文字、画风都不改。"),
)


def ask_picture_edit_mode(parent, anchor=None, *, initial: str = "modify", step_no: int = 0):
    """t216u / t315u / t366u: 图片修改第一步：选类型。返回 "modify" / "cover" / "cast" / "portrait" / "upscale"，取消返回 None。"""
    box = tk.Toplevel(parent)
    box.title("图片修改 · 选类型")
    box.transient(parent)
    box.resizable(False, False)
    frm = ttk.Frame(box, padding=14)
    frm.pack(fill=tk.BOTH, expand=True)
    valid = {k for k, _t, _d in PICTURE_EDIT_MODES}
    if initial not in valid or (initial == "cover" and step_no <= 0):
        initial = "modify"
    var = tk.StringVar(master=box, value=initial)
    for key, title, desc in PICTURE_EDIT_MODES:
        if key == "cover" and step_no > 0:
            title = f"{title}（第 {step_no} 步）"
        rb = ttk.Radiobutton(frm, text=title, value=key, variable=var)
        rb.pack(anchor=tk.W, pady=(6, 0))
        note = desc if not (key == "cover" and step_no <= 0) else "这一场没有步骤号（第 N 步），用不了。"
        ttk.Label(frm, text=note, foreground="#666", wraplength=520, justify=tk.LEFT).pack(anchor=tk.W, padx=(22, 0))
        if key == "cover" and step_no <= 0:
            rb.state(["disabled"])
    res = {"v": None}

    def go(_e=None):
        res["v"] = var.get()
        box.destroy()

    btns = ttk.Frame(frm)
    btns.pack(fill=tk.X, pady=(12, 0))
    ok_btn = ttk.Button(btns, text="下一步", command=go, default="active")
    ok_btn.pack(side=tk.RIGHT)
    ttk.Button(btns, text="取消", command=box.destroy).pack(side=tk.RIGHT, padx=(0, 8))
    box.bind("<Return>", go)
    box.bind("<Escape>", lambda _e: box.destroy())
    try:
        _place_popup_near(box, anchor if anchor is not None else parent, below=True)
    except Exception:  # noqa: BLE001
        pass
    ok_btn.focus_set()
    box.grab_set()
    parent.wait_window(box)
    return res["v"]


def open_picture_prompt_dialog(
    parent,
    anchor,
    *,
    get_scene,
    get_style,
    get_place=None,
    open_manual=None,
    host_narrator: str = "",
    main_character: str = "",
    saved_choice=None,
    save_choice=None,
    actor_avatar_dir: str = "",
    batch_scenes=None,
    run_batch=None,
    get_step_no=None,
    get_project_cover=None,
    get_project_covers=None,
    mode=None,
    review_portrait=None,
) -> None:
    """先选画风改变和叙事风格，再打开手动窗口，里面是当前图和提示词。

    勾了「人物」且这一场有人物时，交给 LLM 的图 = 选中的场景图 + 各人物形象图（按 Actors 顺序，最多共 5 张）。

    ``saved_choice`` 是项目里记下的上次选择；关窗或提交时 ``save_choice(dict)`` 记回去。

    t249: 「修改图片」模式下：
    - 内容来源（visual/speaking/actor）临时默认全部 False，不使用也不覆盖 saved_choice
    - 关闭时不保存 modify 模式的临时内容来源设置，原 saved_choice 保持不变

    t413u: 底下两个按钮：「提交」只做当前这一场；「全集提交」从当前场景到本集结束，每一场用同样的类型和设置
    逐场处理（失败的场跳过，最后一起报告）。「提取人物肖像」只有「提交」（肖像按人物、要人一位一位确认）。
    """
    step_no = 0
    if callable(get_step_no):
        try:
            step_no = int(get_step_no() or 0)
        except (TypeError, ValueError):
            step_no = 0
    if mode is None:  # t216u: 第一步选类型，第二步才是这个窗口
        prev = (saved_choice or {}).get("mode") if isinstance(saved_choice, dict) else None
        mode = ask_picture_edit_mode(parent, anchor, initial=prev or "modify", step_no=step_no)
        if mode is None:
            return
    if mode == "cover" and step_no <= 0:
        mode = "modify"
    dlg = tk.Toplevel(parent)
    dlg.title("图片修改 · " + dict((k, t) for k, t, _d in PICTURE_EDIT_MODES).get(mode, ""))
    dlg.transient(parent)
    dlg.resizable(False, False)
    dlg.withdraw()

    last = _clean_choice(saved_choice)

    # t249: 「修改图片」模式下内容来源临时默认全部 False，不覆盖 saved_choice
    # 保存原始 saved_choice 的内容来源设置，关闭时用于恢复（不保存 modify 模式的临时设置）
    _modify_mode_source_override = (mode == "modify")
    _original_source_flags = {
        "visual": last["visual"],
        "speaking": last["speaking"],
        "actor": last["actor"],
    }
    if _modify_mode_source_override:
        last["visual"] = False
        last["speaking"] = False
        last["actor"] = False

    main = ttk.Frame(dlg, padding=10)
    main.pack(fill=tk.BOTH, expand=True)
    hint = ttk.Label(main, wraplength=760, justify=tk.LEFT)
    hint.pack(anchor=tk.W)
    groups = ttk.Frame(main)
    groups.pack(anchor=tk.W, pady=(8, 8))
    bottom = ttk.Frame(main)
    bottom.pack(fill=tk.X)

    task_var = tk.StringVar(value=last["task"])
    text_var = tk.StringVar(value=last["text"])
    narrative_var = tk.StringVar(value=last["narrative"])
    visual_var = tk.BooleanVar(value=last["visual"])
    speaking_var = tk.BooleanVar(value=last["speaking"])
    actor_var = tk.BooleanVar(value=last["actor"])
    override_var = tk.StringVar(value=last["actor_override"])
    backend_var = tk.StringVar(value=picture_edit_backend(last.get("backend")))  # t415u
    fix_cast_var = tk.BooleanVar(value=last.get("fix_cast", False))  # t197u
    _fix_ok = [False]

    def fix_on() -> bool:
        return bool(fix_cast_var.get()) and _fix_ok[0]

    # 与全集生成相同：叙事风格 | 说明文字 | 写进提示词的内容；画风改变放到下面一行。
    _story_box, story_buttons = pack_narrative_choices(groups, narrative_var, actor_var=actor_var)
    # 叙事风格第 5 项：提取第 N 步（N = 当前场景在这一集里的序号）
    if step_no > 0:
        ttk.Radiobutton(
            _story_box, text=f"提取第 {step_no} 步（从封面/信息图取出这一步，画成单张场景图）",
            value="step", variable=narrative_var,
        ).pack(anchor=tk.W, after=story_buttons[-1])
    elif narrative_var.get() == "step":
        narrative_var.set("narration")

    text_box = ttk.LabelFrame(groups, text="说明文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    text_buttons = []
    for value, label in config_prompt.PICTURE_FLOW_TEXT_CHOICES:
        btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
        btn.pack(anchor=tk.W)
        text_buttons.append(btn)

    _fields, field_buttons = pack_scene_field_choices(
        groups, visual_var, speaking_var, actor_var, override_var, anchor=tk.N,
        title="内容来源（场景描述）",
    )

    task_box = ttk.LabelFrame(bottom, text="画风改变", padding=(8, 4))
    task_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.PICTURE_FLOW_TASK_CHOICES:
        ttk.Radiobutton(task_box, text=label, value=value, variable=task_var).pack(anchor=tk.W)

    _img_box = None
    _cover_box = None
    _cover_path = ""

    def chosen_image() -> str:
        return last.get("image", "clip_image")

    def image_to_save() -> str:
        # Cover mode has no picker; keep the last saved slot key as-is.
        return last.get("image", "clip_image")

    if mode == "cover":
        from gui.clip_image_choice import pack_project_cover_preview
        from utility.scene_image_slots import list_project_cover_images, resolve_project_cover_image

        _cover_paths = []
        if callable(get_project_covers):
            try:
                _cover_paths = list(get_project_covers() or [])
            except Exception:
                _cover_paths = []
        if callable(get_project_cover):
            try:
                _cover_path = str(get_project_cover() or "").strip()
            except Exception:
                _cover_path = ""
        if not (_cover_path and os.path.isfile(_cover_path)):
            try:
                _cover_path = resolve_project_cover_image(
                    project_config=project_manager.PROJECT_CONFIG,
                )
            except Exception:
                _cover_path = _cover_path if _cover_path and os.path.isfile(_cover_path) else ""
        if _cover_path and os.path.isfile(_cover_path):
            _cover_path = os.path.abspath(_cover_path)
        else:
            _cover_path = ""
        if not _cover_paths:
            try:
                _cover_paths = list_project_cover_images(
                    project_config=project_manager.PROJECT_CONFIG,
                )
            except Exception:
                _cover_paths = []
        if _cover_path and _cover_path not in _cover_paths:
            _cover_paths = [_cover_path] + list(_cover_paths)
        _cover_box = pack_project_cover_preview(bottom, _cover_path, paths=_cover_paths)
    else:
        from gui.clip_image_choice import pack_clip_image_choice

        def _scene_image(key: str) -> str:
            sc = get_scene() if get_scene is not None else None
            return (sc.get(key) or "") if isinstance(sc, dict) else ""

        # Which image goes to the LLM; remembered with the other choices (key "image").
        _img_box, chosen_image, image_to_save = pack_clip_image_choice(
            bottom, _scene_image, initial=last.get("image", "clip_image")
        )

    # FYI / 注意: text persisted in picture_prompt; checkbox always ON on open.
    _fyi_box, get_fyi_text, fyi_include_var, get_fyi_history = pack_fyi_note(
        main, history=last.get("fyi_history", []), pady=(8, 0)
    )
    # Keep FYI above the bottom row (fields / image / submit).
    _fyi_box.pack_forget()
    _fyi_box.pack(fill=tk.X, pady=(8, 0), before=bottom)

    # 背景：地域 · 时代 · 人物（全场内容），默认勾上；放在 FYI 下面。
    region, era = ("", "")
    if get_place is not None:
        try:
            region, era = get_place()
        except (TypeError, ValueError):
            region, era = ("", "")
    from utility import story_stage as _story_stage

    stage_info = _story_stage.capture()  # t191u: 故事舞台
    from gui.prompt_fyi import pack_background_block

    _bg_box, bg_include_var = pack_background_block(
        main, region, era, host_narrator,
        style=(get_style() or "").strip(), actor_var=actor_var,
        initial=last.get("background", True),
    )
    # 下方一行：背景（左）+ 画风改变 / 交给 LLM 的图 / 提交（右，顶端对齐），同全集生成。
    lower = ttk.Frame(main)
    lower.pack(fill=tk.X, pady=(6, 0), before=bottom)
    _bg_box.pack_forget()
    _bg_box.pack(in_=lower, side=tk.LEFT, anchor=tk.N)
    _bg_box.lift(lower)  # 先建的控件在 lower 之下，需抬到上面才看得见
    bottom.pack_forget()
    bottom.pack(in_=lower, side=tk.LEFT, anchor=tk.N, padx=(16, 0))
    bottom.lift(lower)  # 先建的控件在 lower 之下，需抬到上面才看得见

    def current_choice() -> dict:
        # t249: 「修改图片」模式下，内容来源使用原始保存值，不保存临时的 False 覆盖
        if _modify_mode_source_override:
            source_flags = dict(_original_source_flags)
        else:
            source_flags = {
                "visual": bool(visual_var.get()),
                "speaking": bool(speaking_var.get()),
                "actor": bool(actor_var.get()),
            }
        return {
            "task": task_var.get(),
            "text": text_var.get(),
            "narrative": narrative_var.get(),
            **source_flags,
            "actor_override": override_var.get(),
            "image": image_to_save(),
            "fyi_history": get_fyi_history(),
            "background": bool(bg_include_var.get()),
            "fix_cast": bool(fix_cast_var.get()),
            "backend": picture_edit_backend(backend_var.get()),  # t415u
            **{k: v for k, v in _step_saved.items()},  # t114u: 提取模式下记用户原来的勾选
            **_mode_saved,  # t216u: 封面提取 / 补全人物 强制的选项不覆盖用户原来的选择
            "mode": mode,
        }

    def remember() -> None:
        if save_choice is None:
            return
        try:
            save_choice(current_choice())
        except Exception as exc:  # noqa: BLE001
            print(f"图片修改：选择没有记下：{exc}")

    _step_saved: dict = {}

    def _set_state_tree(widget, state: str) -> None:
        for child in widget.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass
            _set_state_tree(child, state)

    def _sync_step_mode_widgets(step_mode: bool) -> None:
        """t114u: 提取第 N 步时取消并灰掉「写进提示词的内容」和「背景」;离开时还原。"""
        pairs = (("visual", visual_var), ("speaking", speaking_var), ("actor", actor_var), ("background", bg_include_var))
        if step_mode and not _step_saved:
            for key, var in pairs:
                _step_saved[key] = bool(var.get())
                var.set(False)
            _set_state_tree(_bg_box, "disabled")
        elif not step_mode and _step_saved:
            for key, var in pairs:
                var.set(_step_saved.get(key, var.get()))
            _step_saved.clear()
            _set_state_tree(_bg_box, "normal")

    def _selected_cover() -> str:
        if _cover_box is not None:
            picked = str(getattr(_cover_box, "_cover_path", "") or "").strip()
            if picked and os.path.isfile(picked):
                return os.path.abspath(picked)
        if _cover_path and os.path.isfile(_cover_path):
            return os.path.abspath(_cover_path)
        return ""

    def refresh(*_args) -> None:
        extract = task_var.get() == "extract"
        step_mode = narrative_var.get() == "step"
        _sync_step_mode_widgets(step_mode)
        for btn in story_buttons:
            btn.configure(state=("disabled" if extract else "normal"))
        for btn in text_buttons:
            btn.configure(state=("disabled" if extract else "normal"))
        for btn in field_buttons:
            btn.configure(state=("disabled" if extract or step_mode else "normal"))
        if mode == "cover":
            if _selected_cover():
                hint.config(
                    foreground="",
                    text=f"从封面提取：用项目封面取出第 {step_no} 步这一场的画面。画风不变，不加字。可以写「注意 / FYI」。",
                )
            else:
                hint.config(
                    foreground="#b00020",
                    text="从封面提取：没有可用的项目封面，无法提交。不会改用场景里选中的图或链式末帧。",
                )
            return
        if mode == "cast":
            hint.config(foreground="", text="补全/修正人物：按 视觉、讲话 和人物肖像图补上缺的人物、改正对不上的人物。画风不变，不加字，不画对话泡泡。")
            return
        if mode == "portrait":
            hint.config(
                foreground="",
                text="提取人物肖像：用 Grok Image 从这一场自己的起始图（clip_image，不用封面）为每个人物重新提取头部/肩部，"
                     "已有肖像的也重新提取。提示词带上性别、年龄、国别和括号里的形象描述；图里不明显存在就不要编造。"
                     "每一张都给你看：确认 = 换上新的（原来的改名 .bak 备份），忽略 = 原来的肖像保持。不改场景图。",
            )
            return
        if mode == "upscale":
            hint.config(
                foreground="",
                text="提高分辨率：用下面选中的场景图，按它自己的比例提高到 1920 级（长边 1920；16:9 = 1920x1080，"
                     "9:16 = 1080x1920）。只加清晰度和细节，构图、人物、文字、颜色、画风一点都不改。"
                     "可以写「注意 / FYI」（会放在提示词最前面）。回来的图再用 Lanczos 对齐到这个尺寸，写回方式同其他图片修改。",
            )
            return
        if step_mode:
            hint.config(foreground="", text=f"提取第 {step_no} 步：只用画风改变（保持画风 / 转成项目风格）和说明文字（只管这一步的字），其他选项不进提示词。")
            return
        edit_only = not extract and not (visual_var.get() or speaking_var.get() or actor_var.get() or fix_on())
        hint.config(foreground=("#1f5fbf" if edit_only else ""))
        if edit_only:
            hint.config(text="未选内容：只按「注意 / FYI」修改现有图片")
        elif extract:
            hint.config(text="人物提取只出当前图里每个人的肖像，不用叙事风格。选好后点「提交」。")
        else:
            hint.config(
                text="画风改变决定这张图怎么画；叙事风格下面的蓝字说明这次怎么讲。勾选要写进提示词的内容，选好后点「提交」。"
            )

    def close() -> None:
        remember()
        dlg.destroy()

    def on_go(backend: str = "grok", account: str = "") -> None:
        # t356u: MOSS / QN（本机 ComfyUI）用 config_prompt.build_comfy_* 单独的一套提示 + 反向提示；
        # Grok / Gemini 走下面原来的提示词，一个字不变。
        comfy = config_prompt.comfy_backend(backend)
        comfy_size = config_prompt.comfy_canvas_size(_project_video_size()) if comfy else ()

        def _comfy_step_job(step: int, base: str, sc=None) -> tuple:
            """从封面（或当前多格图）提取第 step 步：看分格布局，能裁就把这一格裁出来当底图。"""
            from utility.cover_panels import prepare_cover_step_input

            style = (get_style() or "").strip() or (project_manager.LAST_VISUAL_STYLE or "").strip()
            prep = prepare_cover_step_input(base, step)
            sc = sc if isinstance(sc, dict) else {}
            pos, neg = config_prompt.build_comfy_cover_step_prompt(
                step, backend=comfy, layout=prep["layout"], count=prep["count"], cropped=prep["cropped"],
                caption=text_var.get(), keep_style=task_var.get() != "restyle", visual_style=style,
                scene_caption=str(sc.get("caption") or ""), scene_visual=str(sc.get("visual") or ""),
                fyi=(get_fyi_text() or "").strip() if fyi_include_var.get() else "", size=comfy_size,
            )
            print(f"图片修改 · {comfy.upper()} 提取第 {step} 步：布局={prep['layout'] or '看不出'}"
                  f"（{prep['count'] or '?'} 格）" + ("，已裁出这一格当底图" if prep["cropped"] else "，用整张图"))
            return pos, [prep["image"]], {"aspect": "", "actors": [], "base": prep["image"], "comfy": True,
                                          "negative": neg, "size": comfy_size}

        if mode == "portrait":
            _run_portrait_extract(account)
            return
        if mode == "upscale":
            _go_upscale(backend, account, comfy)
            return
        if mode == "cast" and not fix_on():
            messagebox.showwarning("图片修改", "补全/修正人物用不了：" + (_tip["text"] or "没有人物肖像图。"), parent=dlg)
            return
        if mode == "cover":
            from utility.scene_image_slots import manual_cover_extract_images
            from utility.speaking_marks import scene_cover_step

            images = manual_cover_extract_images(_selected_cover())
            if not images:
                messagebox.showwarning("图片修改", "没有可用的项目封面，无法从封面提取。", parent=dlg)
                return

            def _cover_step_prompt(step: int) -> str:
                style = (get_style() or "").strip() or (project_manager.LAST_VISUAL_STYLE or "").strip()
                prompt = config_prompt.build_step_image_clipbody(
                    step,
                    visual_style=style,
                    keep_style=task_var.get() != "restyle",
                    caption=text_var.get(),
                    extract_only=True,
                    fyi=(get_fyi_text() or "").strip() if fyi_include_var.get() else "",
                )
                aspect = config_prompt.output_aspect_line(_project_video_size())
                if aspect:
                    prompt = aspect + "\n\n" + prompt
                return prompt

            # t413u: 「提交」= 只做当前这一场；「全集提交」= 从当前场景到本集结束，每一场同样处理
            got_scope = _resolve_scope("每一场都用同一张项目封面提取各自的步骤")
            if got_scope is None:
                return
            scope, batch_list, k_no, m_no = got_scope
            if scope == "episode":
                jobs, skipped = [], []
                scene = get_scene() if get_scene is not None else None
                for sc in batch_list:
                    if not isinstance(sc, dict):
                        continue
                    no = k_no + len(jobs) + len(skipped)
                    label = f"第{no}场" if k_no else str(sc.get("id") or no)
                    k = int(scene_cover_step(sc) or 0)
                    if k <= 0 and sc is scene:
                        k = step_no
                    if k <= 0:
                        skipped.append(f"{label}：没有步骤号")
                        continue
                    if comfy:
                        cp_, ci_, cm_ = _comfy_step_job(k, images[0], sc)
                        jobs.append((sc, cp_, ci_, cm_))
                        continue
                    prompt = _cover_step_prompt(k)
                    aspect = config_prompt.output_aspect_line(_project_video_size())
                    jobs.append((
                        sc, prompt, list(images),
                        {"aspect": aspect, "actors": [], "base": images[0]},
                    ))
                remember()
                dlg.destroy()
                try:
                    run_batch(jobs, backend, skipped, account)
                except TypeError:
                    run_batch(jobs, backend, skipped)
                return
            if step_no <= 0:
                messagebox.showwarning("图片修改", "当前场景没有步骤号，无法从封面提取。", parent=dlg)
                return
            if comfy:
                cp_, ci_, cm_ = _comfy_step_job(step_no, images[0], get_scene() if get_scene is not None else None)
                remember()
                dlg.destroy()
                if callable(open_manual):
                    _call_open_manual(cp_, ci_, backend, account, comfy=cm_)
                return
            prompt = _cover_step_prompt(step_no)
            remember()
            dlg.destroy()
            if callable(open_manual):
                _call_open_manual(prompt, list(images), backend, account)
            return
        if narrative_var.get() == "step" and step_no > 0:
            # 提取第 N 步：沿用 Step Image 提示词，当前选中的图当输入，结果走图片修改的正常回填
            scene = get_scene() if get_scene is not None else None
            path = scene.get(chosen_image()) if isinstance(scene, dict) else ""
            if not (isinstance(path, str) and path and os.path.isfile(path)):
                messagebox.showwarning("图片修改", "当前场景没有可用的图，提取不了第几步。", parent=dlg)
                return
            if comfy:
                cp_, ci_, cm_ = _comfy_step_job(step_no, path, scene)
                remember()
                dlg.destroy()
                if callable(open_manual):
                    _call_open_manual(cp_, ci_, backend, account, comfy=cm_)
                return
            style = (get_style() or "").strip() or (project_manager.LAST_VISUAL_STYLE or "").strip()
            # t114u: 只写「原样取出第 N 格」+ 画风改变 + 说明文字 + FYI;不带 visual/speaking/actor/讲员/背景
            prompt = config_prompt.build_step_image_clipbody(
                step_no,
                visual_style=style,
                keep_style=task_var.get() != "restyle",
                caption=text_var.get(),
                extract_only=True,
                fyi=(get_fyi_text() or "").strip() if fyi_include_var.get() else "",
            )
            aspect = config_prompt.output_aspect_line(_project_video_size())
            if aspect:
                prompt = aspect + "\n\n" + prompt
            remember()
            dlg.destroy()
            if callable(open_manual):
                _call_open_manual(prompt, [path], backend, account)
            return
        extract = task_var.get() == "extract"
        edit_only = not extract and not (visual_var.get() or speaking_var.get() or actor_var.get() or fix_on())
        fyi_now = (get_fyi_text() or "").strip() if fyi_include_var.get() else ""
        if edit_only and not fyi_now:
            if not messagebox.askokcancel(
                "图片修改",
                "没有勾选任何内容，「注意 / FYI」也是空的（或没勾选），没有要修改的地方。\n仍然继续吗？",
                parent=dlg,
            ):
                return
        if False:
            messagebox.showwarning("图片修改", "场景描述、讲话、人物至少要选一项。", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not extract and not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip()
        if not extract and not style:
            messagebox.showwarning("图片修改", "请先在上面选定画面风格。", parent=dlg)
            return
        scene = get_scene() if get_scene is not None else None
        if not isinstance(scene, dict):
            messagebox.showwarning("图片修改", "没有当前场景", parent=dlg)
            return
        def build_request(scene: dict, quiet: bool = False, session: bool = False):
            """按现在的选择给这一场组提示词和图。返回 (prompt, images, meta)；出错返回 None（quiet 时抛 ValueError）。

            ``session``：Gemini 批量同一对话。人物形象图在开场时发过了，这里只发基础图，
            提示词里不写图片序号（由批量那边按开场的序号加一段说明），比例行放在 meta["aspect"]。
            """
            path = scene.get(chosen_image()) if isinstance(scene, dict) else ""
            images = [path] if isinstance(path, str) and path and os.path.isfile(path) else []
            if fix_on() and not extract:
                # t197u: 补全/修正人物：场景图 + 每位人物的肖像图，一起发给 Grok Image 编辑
                rows, missing = _cast_rows(scene, style)
                msg = ("这一场没有当前图，补全/修正人物需要一张场景图。" if not images else
                       "这一场没有人物。" if not rows else
                       ("这些人物没有肖像图：" + "、".join(missing)) if missing else "")
                if msg:
                    if quiet:
                        raise ValueError(msg)
                    messagebox.showwarning("图片修改", msg, parent=dlg)
                    return None
                if comfy:  # t356u: 参考图按工作流槽位截断（MOSS 3 / QN 2），放不下的人只用文字描述
                    crow, cref = config_prompt.comfy_cast_rows(rows, comfy)
                    cpos, cneg = config_prompt.build_comfy_cast_fix_prompt(
                        scene, crow, backend=comfy, visual_style=style, fyi=fyi_now, text=text_var.get())
                    cimgs = images[:1] + cref
                    print(f"图片修改 · 补全/修正人物（{comfy.upper()}）：发出的图 = " + " | ".join(
                        [f"1 场景图 {os.path.basename(cimgs[0])}"]
                        + [f"{r['image_no']} {r['label']} {r['name']}" if r.get("image_no") else f"（{r['label']} {r['name']} 只用文字）"
                           for r in crow]))
                    return cpos, cimgs, {"aspect": "", "actors": crow, "base": cimgs[0], "full_images": True,
                                         "comfy": True, "negative": cneg, "size": comfy_size}
                imgs = list(images)
                for r in rows:
                    if r["image"] not in imgs:
                        imgs.append(r["image"])
                prompt = config_prompt.build_cast_fix_prompt(scene, rows, visual_style=style, fyi=fyi_now, text=text_var.get())
                prompt = config_prompt.prepend_background_condition(
                    prompt, region, era, host_narrator, include=bool(bg_include_var.get()), stage=stage_info,
                )
                aspect = config_prompt.output_aspect_line(_project_video_size())
                if aspect:
                    prompt = aspect + "\n\n" + prompt
                print("图片修改 · 补全/修正人物：发出的图 = " + " | ".join(
                    [f"1 场景图 {os.path.basename(imgs[0])}"] + [f"{r['image_no']} {r['label']} {r['name']}" for r in rows]))
                return prompt, imgs, {"aspect": aspect, "actors": rows, "base": imgs[0], "full_images": True}
            if not images and not quiet:
                messagebox.showinfo("图片修改", "这一场没有当前图。提示窗口里只放提示词。", parent=dlg)
            # 人物形象图：勾了人物、不是仅修改 / 人物提取时才加。
            actor_images = []
            override_en = dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), "")
            if actor_var.get() and not edit_only and not extract:
                from utility.content_pdf import scene_actor_reference_images

                # 「换成」覆盖时形象图从头像库按 性别_时代_族裔 查（找不到就只用文字描述）。
                actor_images = scene_actor_reference_images(
                    scene, avatar_dir=actor_avatar_dir, base_image=images[0] if images else "",
                    override_label=override_var.get() if override_en else "",
                    style=style,  # 形象图按画面风格分目录查：avatar/<风格>/ → Realistic/ → 根目录
                )
                for row in actor_images:
                    if row.get("image") and row["image"] not in images:
                        images.append(row["image"])
                sent = [f"1 基础图 {os.path.basename(images[0])}"] if path in images else []
                for r in actor_images:
                    sent.append(f"{r['image_no']} {r['label']} {r['name']}" if r.get("image_no")
                                else f"（{r['label']} {r['name']} 没有形象图）")
                print(f"图片修改：发出的图 = " + " | ".join(sent))
            if comfy:  # t356u: 一般修改 / 人物提取：ComfyUI 专用短提示
                crow, cref = config_prompt.comfy_cast_rows(actor_images, comfy)
                cimgs = images[:1] + cref
                use_bg = bool(bg_include_var.get()) and not extract
                cpos, cneg = config_prompt.build_comfy_picture_edit_prompt(
                    backend=comfy, task=task_var.get(), text=text_var.get(), visual_style=style,
                    edit_request=fyi_now if edit_only else "", scene=scene,
                    use_visual=bool(visual_var.get()) and not edit_only, use_speaking=bool(speaking_var.get()) and not edit_only,
                    use_actor=bool(actor_var.get()) and not edit_only, actor_rows=crow,
                    region=region if use_bg else "", era=era if use_bg else "",
                    actor_override=dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), ""),
                    fyi="" if edit_only else fyi_now,
                )
                size = () if extract else comfy_size
                return cpos, cimgs, {"aspect": "", "actors": crow, "base": cimgs[0] if cimgs else "", "comfy": True,
                                     "negative": cneg, "size": size}
            if session:
                images = images[:1]
            try:
                prompt = config_prompt.build_picture_flow_prompt(
                    task=task_var.get(),
                    text=text_var.get(),
                    visual_style=style,
                    region="",  # 地域/时代改由下面的背景条件统一写入
                    era="",
                    narrative=narrative_var.get(),
                    use_visual=bool(visual_var.get()),
                    use_speaking=bool(speaking_var.get()),
                    use_actor=bool(actor_var.get()),
                    scene_content=[scene],
                    host_narrator=host_narrator or "",
                    main_character=main_character or "",
                    actor_override=dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), ""),
                    edit_request=fyi_now if edit_only else "",
                    actor_images=[] if session else actor_images,
                    base_image=bool(path and isinstance(path, str) and os.path.isfile(path)),
                )
            except ValueError as exc:
                if quiet:
                    raise
                messagebox.showwarning("图片修改", str(exc), parent=dlg)
                return None
            if not extract:
                # 人数锁定：防止多画出名单外的人（小孩、路人、背景人影）。
                prompt = prompt.rstrip() + "\n\n" + config_prompt.scene_cast_lock_line(
                    [scene], bool(actor_var.get()) and not edit_only, where="picture"
                )
            if edit_only:
                # 仅修改：FYI 已作为「主要修改要求」写在最前；背景条件放在后面。
                bg = config_prompt.background_condition_block(region, era, host_narrator, stage_info) if bg_include_var.get() else ""
                if bg:
                    bg = bg.replace("(applies to everything below)", "(applies to the whole edit)")
                    prompt = prompt + "\n\n---\n\n" + bg
            else:
                prompt = config_prompt.prepend_background_condition(
                    prompt, region, era, host_narrator,
                    include=bool(bg_include_var.get()) and not extract, stage=stage_info,
                )
                prompt = prepend_fyi(
                    prompt, get_fyi_text(), include=bool(fyi_include_var.get())
                )
            # 出图比例放在最前面（人物提取出肖像，不加）。
            aspect = "" if extract else config_prompt.output_aspect_line(_project_video_size())
            if aspect and not session:
                prompt = aspect + "\n\n" + prompt
            meta = {"aspect": aspect, "actors": actor_images, "base": images[0] if images else ""}
            return prompt, images, meta

        # t413u: 所有类型（含「修改图片」）都可以全集提交（以前 t249「修改图片」只能做当前场景）
        got_scope = _resolve_scope("每一场用自己的图和内容分别发出")
        if got_scope is None:
            return
        scope, batch_list, k_no, m_no = got_scope
        if scope == "episode":
            jobs, skipped = [], []
            for sc in batch_list:
                if not isinstance(sc, dict):
                    continue
                no = k_no + len(jobs) + len(skipped)
                label = f"第{no}场" if k_no else str(sc.get("id") or no)
                img = sc.get(chosen_image())
                if not (isinstance(img, str) and img and os.path.isfile(img)):
                    skipped.append(f"{label}：没有图")
                    continue
                try:
                    req = build_request(sc, quiet=True, session=(backend == "gemini"))
                except ValueError as exc:
                    skipped.append(f"{label}：{exc}")
                    continue
                if req:
                    jobs.append((sc, req[0], req[1], req[2]))
            remember()
            dlg.destroy()
            try:
                run_batch(jobs, backend, skipped, account)
            except TypeError:
                run_batch(jobs, backend, skipped)
            return
        req = build_request(scene)
        if req is None:
            return
        prompt, images = req[0], req[1]
        remember()
        dlg.destroy()
        if callable(open_manual):
            if comfy and isinstance(req[2], dict) and req[2].get("comfy"):
                _call_open_manual(prompt, images, backend, account, comfy=req[2])
            else:
                _call_open_manual(prompt, images, backend, account)

    def _go_upscale(backend: str, account: str, comfy: str) -> None:
        """t366u: 提高分辨率：每一场用自己选中的图，按原图比例出 1920 级（utility.image_upscale）；
        Grok / Gemini 用 build_upscale_prompt，MOSS / QN 用 build_comfy_upscale_prompt + 反向提示 + 固定画布。
        meta["upscale_size"] = 目标尺寸：结果回来后对齐（Lanczos，比例变了就居中裁）再写回。"""
        from utility.image_upscale import comfy_upscale_canvas, upscale_init_denoise, upscale_target_for_image

        fyi_up = (get_fyi_text() or "").strip() if fyi_include_var.get() else ""
        # t377u: 项目画风只当画风说明写进第一条（FAITHFUL RESTORE：看上去一模一样，不改 / 不加强画风）
        style_up = (get_style() or "").strip() or (project_manager.LAST_VISUAL_STYLE or "").strip()

        def _upscale_job(sc) -> tuple:
            path = sc.get(chosen_image()) if isinstance(sc, dict) else ""
            if not (isinstance(path, str) and path and os.path.isfile(path)):
                raise ValueError("没有图")
            try:
                target = upscale_target_for_image(path)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"读不出图的尺寸（{exc}）") from exc
            if not target:
                raise ValueError("读不出图的尺寸")
            if comfy:
                canvas = comfy_upscale_canvas(target)
                pos, neg = config_prompt.build_comfy_upscale_prompt(target, backend=comfy, fyi=fyi_up, style=style_up)
                return pos, [path], {"aspect": "", "actors": [], "base": path, "comfy": True, "negative": neg,
                                     "size": canvas, "upscale_size": target,
                                     "init_denoise": upscale_init_denoise(comfy)}  # t377u
            prompt = prepend_fyi(config_prompt.build_upscale_prompt(target, style_up), fyi_up, include=bool(fyi_up))
            return prompt, [path], {"aspect": "", "actors": [], "base": path, "upscale_size": target}

        # t413u: 「提交」= 只做当前这一场；「全集提交」= 从当前场景到本集结束，每一场同样处理
        got_scope = _resolve_scope("每一场用自己的图分别提高分辨率")
        if got_scope is None:
            return
        scope, batch_list, k_no, m_no = got_scope
        if scope == "episode":
            jobs, skipped = [], []
            for sc in batch_list:
                if not isinstance(sc, dict):
                    continue
                no = k_no + len(jobs) + len(skipped)
                label = f"第{no}场" if k_no else str(sc.get("id") or no)
                try:
                    p_, i_, m_ = _upscale_job(sc)
                except ValueError as exc:
                    skipped.append(f"{label}：{exc}")
                    continue
                jobs.append((sc, p_, i_, m_))
            remember()
            dlg.destroy()
            try:
                run_batch(jobs, backend, skipped, account)
            except TypeError:
                run_batch(jobs, backend, skipped)
            return
        scene = get_scene() if get_scene is not None else None
        try:
            p_, i_, m_ = _upscale_job(scene)
        except ValueError as exc:
            messagebox.showwarning("图片修改", f"提高分辨率用不了：这一场{exc}。", parent=dlg)
            return
        tw, th = m_["upscale_size"]
        print(f"图片修改 · 提高分辨率（{(comfy or backend or 'grok').upper()}）：{os.path.basename(i_[0])} → {tw}x{th}"
              + (f"（ComfyUI 画布 {m_['size'][0]}x{m_['size'][1]}）" if comfy else ""))
        remember()
        dlg.destroy()
        if callable(open_manual):
            _call_open_manual(p_, i_, backend, account, comfy=m_ if comfy else None, upscale=m_["upscale_size"])

    def _call_open_manual(prompt, images, backend, account, comfy=None, upscale=None) -> None:
        if upscale:  # t366u: 带目标尺寸，结果回来对齐后再写回
            try:
                if comfy:
                    open_manual(prompt, images, backend, account, comfy=comfy, upscale=tuple(upscale))
                else:
                    open_manual(prompt, images, backend, account, upscale=tuple(upscale))
                return
            except TypeError:
                pass
        if comfy:  # t356u: ComfyUI 专用提示：带反向提示词 / 画布给手动窗口
            try:
                open_manual(prompt, images, backend, account, comfy=comfy)
                return
            except TypeError:
                pass
        try:
            open_manual(prompt, images, backend, account)
        except TypeError:
            try:
                open_manual(prompt, images, backend)
            except TypeError:
                open_manual(prompt, images)

    def _run_portrait_extract(account: str = "") -> None:
        """t319u / t329u / t343u: 只用这一场的 clip_image，为每一位人物（已有肖像也一样）各调一次 Grok；
        每拿到一张就在人物窗里给人看（确认 = 换上，忽略 = 原来的保持，删除肖像 = 都不要）。不用 Strata。
        在后台线程跑，界面不卡；审核窗由 ``review_portrait(actor, kind)`` 排到主线程。"""
        import threading

        from utility.actor_portrait_extract import (
            REVIEW_OK,
            actors_from_scene,
            format_actor_result_line,
            generate_portrait_with_grok,
            review_portraits_for_scene,
            scene_clip_image_source,
        )

        scene = get_scene() if get_scene is not None else None
        if not isinstance(scene, dict):
            messagebox.showwarning("图片修改", "没有当前场景", parent=dlg)
            return
        # t319u: 只用这一场自己的 clip_image（不按四图选择，不用封面或封面拷贝）
        covers = []
        if callable(get_project_covers):
            try:
                covers = list(get_project_covers() or [])
            except Exception:  # noqa: BLE001
                covers = []
        image = scene_clip_image_source(scene, covers)
        if not image:
            messagebox.showwarning(
                "图片修改",
                "这一场还没有自己的起始图（clip_image），或起始图还是封面原图的拷贝。"
                "先从封面提取 / 生成这一场的图，再提取人物肖像。",
                parent=dlg,
            )
            return
        actors = actors_from_scene(scene)
        if not actors:
            messagebox.showinfo("图片修改", "这一场没有人物，不用提取肖像。", parent=dlg)
            return
        style = (get_style() or "").strip() if callable(get_style) else ""
        try:  # 同双击人物看肖像（wf_actors._portrait_style）的风格目录
            import config as _cfg

            style = _cfg.match_visual_style(style) or style or project_manager.current_visual_style()
        except Exception:  # noqa: BLE001
            pass

        def generate(image_path, actor, prompt):
            return generate_portrait_with_grok(image_path, actor, prompt, account=account)

        def review(actor, _path, kind):
            if not callable(review_portrait):
                return REVIEW_OK
            return review_portrait(actor, kind)

        remember()
        dlg.destroy()
        avatar_dir = actor_avatar_dir or ""

        def show_summary(lines, error=""):
            if error:
                messagebox.showwarning("提取人物肖像", f"提取人物肖像失败：{error}", parent=parent)
                return
            print("提取人物肖像（" + os.path.basename(image) + "）：\n" + "\n".join(lines))
            messagebox.showinfo("提取人物肖像", "\n".join(lines) if lines else "没有可处理的人物。", parent=parent)

        def work():
            try:
                out = review_portraits_for_scene(
                    scene, avatar_dir, covers=covers, style=style, generate=generate, review=review,
                    confirmed=set(), existing="replace", stop_on_failure=False, account=account,
                )
            except Exception as exc:  # noqa: BLE001
                parent.after(0, lambda e=str(exc): show_summary([], e))
                return
            rows = out.get("results") or []
            lines = [format_actor_result_line(row) for row in rows]
            parent.after(0, lambda: show_summary(lines))

        threading.Thread(target=work, daemon=True).start()

    _submit_scope = {"v": "scene"}  # t413u: 按的是「提交」(scene) 还是「全集提交」(episode)

    def _resolve_scope(note: str):
        """t413u: 按按钮定范围。返回 (scope, 场景列表, 当前是本集第 k 场, 本集共 m 场)；不做了返回 None。"""
        if _submit_scope.get("v") != "episode":
            return "scene", [], 0, 0
        if not (callable(batch_scenes) and callable(run_batch)):
            messagebox.showwarning("图片修改", "这里不能全集提交。", parent=dlg)
            return None
        got = batch_scenes()
        if isinstance(got, tuple):
            batch_list, k_no, m_no = got
        else:
            batch_list, k_no, m_no = list(got or []), 0, 0
        n_batch = len(batch_list)
        if not n_batch:
            messagebox.showinfo("图片修改", "本集从当前场景起没有场景。", parent=dlg)
            return None
        span = f"第{k_no}–{m_no}场，共{n_batch}场；前面的场不动" if k_no else f"共{n_batch}场"
        if not messagebox.askokcancel(
            "图片修改 · 全集提交",
            f"从当前场景到本集结束（{span}），{note}。\n"
            "每一场原来的起始图先拷到结束图（Clip Last）做备份，改好的图当起始图。\n"
            "某一场失败就跳过，最后一起报告。",
            parent=dlg,
        ):
            return None
        print(f"图片修改 · 全集提交：{span}")
        return "episode", list(batch_list), k_no, m_no

    def on_submit(scope: str = "scene") -> None:
        """t129u / t229u: 「提交」先问后端（Grok / Gemini / MOSS / QN）和 Chrome 账户；MOSS/QN 本机 ComfyUI，不用账户。
        t413u: ``scope`` = "scene"（提交）/ "episode"（全集提交）。"""
        _submit_scope["v"] = "episode" if scope == "episode" and mode != "portrait" else "scene"
        if mode == "portrait":
            picked = ask_llm_and_account(dlg, title="提取人物肖像（Grok）", fixed_backend="grok")
            if picked:
                _run_portrait_extract(picked[1])
            return
        # t415u: 后端在窗口里已经选好（默认 QN）。MOSS / QN = 本机 ComfyUI，直接发；Grok / Gemini 只再问 Chrome 账户。
        backend = picture_edit_backend(backend_var.get())
        if backend in COMFY_PICTURE_BACKENDS:
            print(f"图片修改：生图后端 {backend.upper()}（ComfyUI）")
            on_go(backend, "")
            return
        picked = ask_llm_and_account(dlg, title=f"提交（{dict(PICTURE_EDIT_BACKENDS)[backend]}）", fixed_backend=backend)
        if picked:
            on_go(backend, picked[1])

    # t197u: 补全/修正人物 —— 每位人物都有肖像图才能勾
    def _cast_rows(scene, style=None):
        if not isinstance(scene, dict):
            return [], []
        from utility.content_pdf import scene_actor_reference_images

        ov = override_var.get() if (actor_var.get() and dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), "")) else ""
        base = scene.get(chosen_image()) or ""
        base = base if isinstance(base, str) and base and os.path.isfile(base) else ""
        rows = scene_actor_reference_images(
            scene, avatar_dir=actor_avatar_dir, base_image=base, override_label=ov,
            style=style if style else ((get_style() or "").strip() or None),
        )
        return rows, [r["name"] for r in rows if not r.get("image")]

    fix_box = ttk.Frame(bottom)
    fix_box.pack(side=tk.LEFT, anchor=tk.N, padx=(8, 0))
    fix_cb = ttk.Checkbutton(fix_box, text="补全/修正人物", variable=fix_cast_var)
    fix_cb.pack(anchor=tk.W)
    fix_note = ttk.Label(fix_box, text="", foreground="#888", wraplength=200, justify=tk.LEFT)
    fix_note.pack(anchor=tk.W)
    _tip = {"text": "", "win": None}

    def _tip_hide(_e=None):
        if _tip["win"] is not None:
            try:
                _tip["win"].destroy()
            except tk.TclError:
                pass
            _tip["win"] = None

    def _tip_show(_e=None):
        _tip_hide()
        if not _tip["text"]:
            return
        tw = tk.Toplevel(dlg)
        tw.wm_overrideredirect(True)
        tw.geometry(f"+{fix_cb.winfo_rootx()}+{fix_cb.winfo_rooty() + fix_cb.winfo_height() + 4}")
        tk.Label(tw, text=_tip["text"], background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                 wraplength=360, justify=tk.LEFT).pack()
        _tip["win"] = tw

    fix_cb.bind("<Enter>", _tip_show)
    fix_cb.bind("<Leave>", _tip_hide)

    def _sync_fix_cast(*_a) -> None:
        try:
            rows, missing = _cast_rows(get_scene() if get_scene is not None else None)
        except Exception as exc:  # noqa: BLE001
            rows, missing = [], []
            print(f"图片修改：查人物肖像出错：{exc}")
        if not rows:
            ok, why = False, "这一场没有人物，不能补全/修正人物。"
        elif missing:
            ok, why = False, "这些人物没有肖像图：" + "、".join(missing)
        else:
            ok, why = True, ("当前场景图 + " + "、".join(f"{r['label']} {r['name']}" for r in rows)
                             + " 的肖像图一起发给 Grok Image：按场景描述和讲话补上缺的人、改正错的人，构图背景不变。")
        _fix_ok[0] = ok
        fix_cb.state(["!disabled"] if ok else ["disabled"])
        _tip["text"] = why
        fix_note.config(text="" if ok else why)
        refresh()

    # t216u: 第二步按类型只露出相关的选项
    _mode_saved: dict = {}

    def _apply_mode() -> None:
        if mode == "modify":
            fix_box.pack_forget()
            if fix_cast_var.get():
                _mode_saved["fix_cast"] = True
                fix_cast_var.set(False)
            if narrative_var.get() == "step":
                _mode_saved["narrative"] = "step"
                narrative_var.set("narration")
            for rb in _story_box.winfo_children():
                if isinstance(rb, ttk.Radiobutton) and str(rb.cget("value")) == "step":
                    rb.pack_forget()
            ttk.Label(
                main, foreground="#666", wraplength=760, justify=tk.LEFT,
                text="FYI：这是「修改图片」：按上面的画风、说明文字和内容来源改这张图。"
                     "要从封面取出这一场，或补全/修正人物，请关掉重开，第一步选别的类型。",
            ).pack(anchor=tk.W, pady=(6, 0))
            return
        forced = {"task": (task_var, "keep"), "text": (text_var, "keep")}
        if mode == "cover":
            forced["narrative"] = (narrative_var, "step")
            forced["fix_cast"] = (fix_cast_var, False)
        elif mode == "cast":
            forced["fix_cast"] = (fix_cast_var, True)
            forced["narrative"] = (narrative_var, "narration" if narrative_var.get() == "step" else narrative_var.get())
        else:
            forced["fix_cast"] = (fix_cast_var, False)
            forced["narrative"] = (narrative_var, "narration" if narrative_var.get() == "step" else narrative_var.get())
        for key, (var, val) in forced.items():
            cur = var.get()
            if cur != val:
                _mode_saved[key] = cur
            var.set(val)
        for w in (_story_box, text_box, task_box):
            w.pack_forget()
        if mode == "cover":
            _fields.pack_forget()
            fix_box.pack_forget()
            if _img_box is not None:
                _img_box.pack_forget()
        elif mode == "portrait":
            _fields.pack_forget()
            fix_box.pack_forget()
            if _cover_box is not None:
                _cover_box.pack_forget()
        elif mode == "upscale":  # t366u: 只留「交给 LLM 的图」和 FYI；内容来源 / 背景不进提示词
            _fields.pack_forget()
            fix_box.pack_forget()
            _bg_box.pack_forget()
            if _cover_box is not None:
                _cover_box.pack_forget()
        else:
            fix_cb.pack_forget()  # 补全人物一定开着；不能用时 fix_note 里写原因
            _fields.pack_forget()
            if _cover_box is not None:
                _cover_box.pack_forget()
        refresh()

    from gui.slide_prompt_dialog import big_submit_button

    if mode != "portrait":  # t415u: 生图后端（提取人物肖像固定 Grok，不显示）
        backend_box = ttk.LabelFrame(bottom, text="生图后端", padding=(6, 2))
        backend_box.pack(side=tk.LEFT, anchor=tk.N, padx=(12, 0))
        for _v, _t in PICTURE_EDIT_BACKENDS:
            ttk.Radiobutton(backend_box, text=_t, value=_v, variable=backend_var).pack(anchor=tk.W)

    submit_btn = big_submit_button(dlg, bottom, lambda: on_submit("scene"), text="提交")
    submit_btn.pack(side=tk.LEFT, anchor=tk.S, padx=(12, 0))
    _buttons = [submit_btn]
    if mode != "portrait" and callable(batch_scenes) and callable(run_batch):
        # t413u: 从当前场景到本集结束，每一场同样处理（提取人物肖像按人物、要逐位确认，只做当前场景）
        episode_btn = big_submit_button(dlg, bottom, lambda: on_submit("episode"), text="全集提交")
        episode_btn.pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
        _buttons.append(episode_btn)
    if mode == "cover" and not (_cover_path and os.path.isfile(_cover_path)):
        for _b in _buttons:
            try:
                _b.state(["disabled"])
            except Exception:
                try:
                    _b.configure(state="disabled")
                except Exception:
                    pass
    dlg.protocol("WM_DELETE_WINDOW", close)
    task_var.trace_add("write", refresh)
    narrative_var.trace_add("write", refresh)
    actor_var.trace_add("write", refresh)
    visual_var.trace_add("write", refresh)
    speaking_var.trace_add("write", refresh)
    fix_cast_var.trace_add("write", refresh)
    override_var.trace_add("write", _sync_fix_cast)
    actor_var.trace_add("write", _sync_fix_cast)
    _sync_fix_cast()
    _apply_mode()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

"""图片提示：画风改变、说明文字，以及叙事风格。叙事风格和幻灯提示、生场视频共用同一组选项。"""

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
}


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
    if saved.get("narrative") in {k for k, _ in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES}:
        choice["narrative"] = saved["narrative"]
    for key in ("visual", "speaking", "actor"):
        if key in saved:
            choice[key] = bool(saved[key])
    if saved.get("actor_override") in {label for label, _en in config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES}:
        choice["actor_override"] = saved["actor_override"]
    if saved.get("image") in ("clip_image", "clip_image_last"):
        choice["image"] = saved["image"]
    choice["fyi_history"] = clean_fyi_history(saved)
    choice["background"] = bool(saved.get("background", True))
    return choice


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
) -> None:
    """先选画风改变和叙事风格，再打开手动窗口，里面是当前图和提示词。

    ``saved_choice`` 是项目里记下的上次选择；关窗或提交时 ``save_choice(dict)`` 记回去。
    """
    dlg = tk.Toplevel(parent)
    dlg.title("图片提示")
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

    task_var = tk.StringVar(value=last["task"])
    text_var = tk.StringVar(value=last["text"])
    narrative_var = tk.StringVar(value=last["narrative"])
    visual_var = tk.BooleanVar(value=last["visual"])
    speaking_var = tk.BooleanVar(value=last["speaking"])
    actor_var = tk.BooleanVar(value=last["actor"])
    override_var = tk.StringVar(value=last["actor_override"])

    # 与全集生成相同：叙事风格 | 说明文字 | 写进提示词的内容；画风改变放到下面一行。
    _story_box, story_buttons = pack_narrative_choices(groups, narrative_var, actor_var=actor_var)

    text_box = ttk.LabelFrame(groups, text="说明文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    text_buttons = []
    for value, label in config_prompt.PICTURE_FLOW_TEXT_CHOICES:
        btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
        btn.pack(anchor=tk.W)
        text_buttons.append(btn)

    _fields, field_buttons = pack_scene_field_choices(
        groups, visual_var, speaking_var, actor_var, override_var, anchor=tk.N
    )

    task_box = ttk.LabelFrame(bottom, text="画风改变", padding=(8, 4))
    task_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.PICTURE_FLOW_TASK_CHOICES:
        ttk.Radiobutton(task_box, text=label, value=value, variable=task_var).pack(anchor=tk.W)

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
        return {
            "task": task_var.get(),
            "text": text_var.get(),
            "narrative": narrative_var.get(),
            "visual": bool(visual_var.get()),
            "speaking": bool(speaking_var.get()),
            "actor": bool(actor_var.get()),
            "actor_override": override_var.get(),
            "image": image_to_save(),
            "fyi_history": get_fyi_history(),
            "background": bool(bg_include_var.get()),
        }

    def remember() -> None:
        if save_choice is None:
            return
        try:
            save_choice(current_choice())
        except Exception as exc:  # noqa: BLE001
            print(f"图片提示：选择没有记下：{exc}")

    def refresh(*_args) -> None:
        extract = task_var.get() == "extract"
        for btn in text_buttons + story_buttons + field_buttons:
            btn.configure(state=("disabled" if extract else "normal"))
        edit_only = not extract and not (visual_var.get() or speaking_var.get() or actor_var.get())
        hint.config(foreground=("#1f5fbf" if edit_only else ""))
        if edit_only:
            hint.config(text="未选内容：只按「注意 / FYI」修改现有图片")
        elif extract:
            hint.config(text="人物提取只出当前图里每个人的肖像，不用叙事风格。选好后点提交。")
        else:
            hint.config(
                text="画风改变决定这张图怎么画；叙事风格下面的蓝字说明这次怎么讲。勾选要写进提示词的内容，选好后点提交。"
            )

    def close() -> None:
        remember()
        dlg.destroy()

    def on_go() -> None:
        extract = task_var.get() == "extract"
        edit_only = not extract and not (visual_var.get() or speaking_var.get() or actor_var.get())
        fyi_now = (get_fyi_text() or "").strip() if fyi_include_var.get() else ""
        if edit_only and not fyi_now:
            if not messagebox.askokcancel(
                "图片提示",
                "没有勾选任何内容，「注意 / FYI」也是空的（或没勾选），没有要修改的地方。\n仍然继续吗？",
                parent=dlg,
            ):
                return
        if False:
            messagebox.showwarning("图片提示", "场景描述、讲话、人物至少要选一项。", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not extract and not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip()
        if not extract and not style:
            messagebox.showwarning("图片提示", "请先在上面选定画面风格。", parent=dlg)
            return
        scene = get_scene() if get_scene is not None else None
        if not isinstance(scene, dict):
            messagebox.showwarning("图片提示", "没有当前场景", parent=dlg)
            return
        path = scene.get(chosen_image()) if isinstance(scene, dict) else ""
        images = [path] if isinstance(path, str) and path and os.path.isfile(path) else []
        if not images:
            messagebox.showinfo("图片提示", "这一场没有当前图。提示窗口里只放提示词。", parent=dlg)
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
            )
        except ValueError as exc:
            messagebox.showwarning("图片提示", str(exc), parent=dlg)
            return
        if edit_only:
            # 仅修改：FYI 已作为「主要修改要求」写在最前；背景条件放在后面。
            bg = config_prompt.background_condition_block(region, era, host_narrator) if bg_include_var.get() else ""
            if bg:
                bg = bg.replace("(applies to everything below)", "(applies to the whole edit)")
                prompt = prompt + "\n\n---\n\n" + bg
        else:
            prompt = config_prompt.prepend_background_condition(
                prompt, region, era, host_narrator,
                include=bool(bg_include_var.get()) and not extract,
            )
            prompt = prepend_fyi(
                prompt, get_fyi_text(), include=bool(fyi_include_var.get())
            )
        remember()
        dlg.destroy()
        if callable(open_manual):
            open_manual(prompt, images)

    from gui.slide_prompt_dialog import big_submit_button

    big_submit_button(dlg, bottom, on_go).pack(side=tk.LEFT, anchor=tk.S, padx=(12, 0))
    dlg.protocol("WM_DELETE_WINDOW", close)
    task_var.trace_add("write", refresh)
    narrative_var.trace_add("write", refresh)
    actor_var.trace_add("write", refresh)
    visual_var.trace_add("write", refresh)
    speaking_var.trace_add("write", refresh)
    refresh()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

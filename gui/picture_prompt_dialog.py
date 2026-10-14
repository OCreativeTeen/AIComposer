"""图片提示：画风改变、说明文字，以及叙事风格。叙事风格和幻灯提示、生场视频共用同一组选项。"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

import config_prompt
import project_manager
from gui.slide_prompt_dialog import pack_narrative_choices, pack_scene_field_choices
from gui.video_prompt_dialog import _place_popup_near


_DEFAULT_CHOICE = {
    "task": "keep",
    "text": "keep",
    "narrative": "story",
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

    ``saved_choice`` 是项目里记下的上次选择；关窗或打开提示时 ``save_choice(dict)`` 记回去。
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

    task_box = ttk.LabelFrame(groups, text="画风改变", padding=(8, 4))
    task_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.PICTURE_FLOW_TASK_CHOICES:
        ttk.Radiobutton(task_box, text=label, value=value, variable=task_var).pack(anchor=tk.W)

    text_box = ttk.LabelFrame(groups, text="说明文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    text_buttons = []
    for value, label in config_prompt.PICTURE_FLOW_TEXT_CHOICES:
        btn = ttk.Radiobutton(text_box, text=label, value=value, variable=text_var)
        btn.pack(anchor=tk.W)
        text_buttons.append(btn)

    _story_box, story_buttons = pack_narrative_choices(groups, narrative_var, padx=(0, 0))
    _fields, field_buttons = pack_scene_field_choices(
        bottom, visual_var, speaking_var, actor_var, override_var
    )

    def current_choice() -> dict:
        return {
            "task": task_var.get(),
            "text": text_var.get(),
            "narrative": narrative_var.get(),
            "visual": bool(visual_var.get()),
            "speaking": bool(speaking_var.get()),
            "actor": bool(actor_var.get()),
            "actor_override": override_var.get(),
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
        if extract:
            hint.config(text="人物提取只出当前图里每个人的肖像，不用叙事风格。选好后打开提示窗口。")
        else:
            hint.config(
                text="画风改变决定这张图怎么画。叙事风格用当前这一场："
                "场景描述只作画面参考，讲话决定故事发展和对话，人物决定性别、国籍和年龄。"
                "三项至少选一项。选择会记下，下次还在。"
            )

    def close() -> None:
        remember()
        dlg.destroy()

    def on_go() -> None:
        extract = task_var.get() == "extract"
        if not extract and not (visual_var.get() or speaking_var.get() or actor_var.get()):
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
        path = scene.get("clip_image") if isinstance(scene, dict) else ""
        images = [path] if isinstance(path, str) and path and os.path.isfile(path) else []
        if not images:
            messagebox.showinfo("图片提示", "这一场没有当前图。提示窗口里只放提示词。", parent=dlg)
        region, era = ("", "")
        if get_place is not None:
            try:
                region, era = get_place()
            except (TypeError, ValueError):
                region, era = ("", "")
        try:
            prompt = config_prompt.build_picture_flow_prompt(
                task=task_var.get(),
                text=text_var.get(),
                visual_style=style,
                region=region or "",
                era=era or "",
                narrative=narrative_var.get(),
                use_visual=bool(visual_var.get()),
                use_speaking=bool(speaking_var.get()),
                use_actor=bool(actor_var.get()),
                scene_content=[scene],
                host_narrator=host_narrator or "",
                main_character=main_character or "",
                actor_override=dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(override_var.get(), ""),
            )
        except ValueError as exc:
            messagebox.showwarning("图片提示", str(exc), parent=dlg)
            return
        remember()
        dlg.destroy()
        if callable(open_manual):
            open_manual(prompt, images)

    ttk.Button(bottom, text="打开提示", command=on_go).pack(side=tk.RIGHT, anchor=tk.S, padx=(12, 0))
    dlg.protocol("WM_DELETE_WINDOW", close)
    task_var.trace_add("write", refresh)
    refresh()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

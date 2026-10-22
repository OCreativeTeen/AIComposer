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
) -> None:
    """先选画风改变和叙事风格，再打开手动窗口，里面是当前图和提示词。

    勾了「人物」且这一场有人物时，交给 LLM 的图 = 选中的场景图 + 各人物形象图（按 Actors 顺序，最多共 5 张）。

    ``saved_choice`` 是项目里记下的上次选择；关窗或提交时 ``save_choice(dict)`` 记回去。
    """
    dlg = tk.Toplevel(parent)
    dlg.title("图片修改")
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
            print(f"图片修改：选择没有记下：{exc}")

    def refresh(*_args) -> None:
        extract = task_var.get() == "extract"
        for btn in text_buttons + story_buttons + field_buttons:
            btn.configure(state=("disabled" if extract else "normal"))
        edit_only = not extract and not (visual_var.get() or speaking_var.get() or actor_var.get())
        hint.config(foreground=("#1f5fbf" if edit_only else ""))
        if edit_only:
            hint.config(text="未选内容：只按「注意 / FYI」修改现有图片")
        elif extract:
            hint.config(text="人物提取只出当前图里每个人的肖像，不用叙事风格。选好后点 Grok提交 或 Gemini提交。")
        else:
            hint.config(
                text="画风改变决定这张图怎么画；叙事风格下面的蓝字说明这次怎么讲。勾选要写进提示词的内容，选好后点 Grok提交 或 Gemini提交。"
            )

    def close() -> None:
        remember()
        dlg.destroy()

    def on_go(backend: str = "grok") -> None:
        extract = task_var.get() == "extract"
        edit_only = not extract and not (visual_var.get() or speaking_var.get() or actor_var.get())
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
            # 出图比例放在最前面（人物提取出肖像，不加）。
            aspect = "" if extract else config_prompt.output_aspect_line(_project_video_size())
            if aspect and not session:
                prompt = aspect + "\n\n" + prompt
            meta = {"aspect": aspect, "actors": actor_images, "base": images[0] if images else ""}
            return prompt, images, meta

        scope = "scene"
        batch_list, k_no, m_no = [], 0, 0
        if callable(batch_scenes) and callable(run_batch):
            got = batch_scenes()
            if isinstance(got, tuple):
                batch_list, k_no, m_no = got
            else:
                batch_list = list(got or [])
            n_batch = len(batch_list)
            here = f"（第{k_no}场）" if k_no else ""
            span = f"（第{k_no}–{m_no}场，共{n_batch}场；前面的场不动）" if k_no else f"（共{n_batch}场）"
            answer = messagebox.askyesnocancel(
                "图片修改",
                f"是 = 只处理当前这一场{here}\n"
                f"否 = 从当前第{k_no}场到本集结束{span}，每一场用自己的图和内容分别发出\n"
                "取消 = 不处理",
                parent=dlg,
            )
            if answer is None:
                return
            scope = "scene" if answer else "episode"
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
            run_batch(jobs, backend, skipped)
            return
        req = build_request(scene)
        if req is None:
            return
        prompt, images = req[0], req[1]
        remember()
        dlg.destroy()
        if callable(open_manual):
            try:
                open_manual(prompt, images, backend)
            except TypeError:
                open_manual(prompt, images)

    from gui.slide_prompt_dialog import big_submit_button

    big_submit_button(dlg, bottom, lambda: on_go("grok"), text="Grok提交").pack(side=tk.LEFT, anchor=tk.S, padx=(12, 0))
    big_submit_button(dlg, bottom, lambda: on_go("gemini"), text="Gemini提交").pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
    dlg.protocol("WM_DELETE_WINDOW", close)
    task_var.trace_add("write", refresh)
    narrative_var.trace_add("write", refresh)
    actor_var.trace_add("write", refresh)
    visual_var.trace_add("write", refresh)
    speaking_var.trace_add("write", refresh)
    refresh()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

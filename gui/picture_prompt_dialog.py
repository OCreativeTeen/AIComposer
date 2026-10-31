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
    if saved.get("narrative") in {k for k, _ in config_prompt.SLIDE_FLOW_NARRATIVE_CHOICES} | {"step"}:
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
    # 叙事风格第 5 项：提取第 N 步（N = 当前场景在这一集里的序号）
    step_no = 0
    if callable(get_step_no):
        try:
            step_no = int(get_step_no() or 0)
        except (TypeError, ValueError):
            step_no = 0
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
            **{k: v for k, v in _step_saved.items()},  # t114u: 提取模式下记用户原来的勾选
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
        if step_mode:
            hint.config(foreground="", text=f"提取第 {step_no} 步：只用画风改变（保持画风 / 转成项目风格）和说明文字（只管这一步的字），其他选项不进提示词。")
            return
        edit_only = not extract and not (visual_var.get() or speaking_var.get() or actor_var.get())
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
        if narrative_var.get() == "step" and step_no > 0:
            # 提取第 N 步：沿用 Step Image 提示词，当前选中的图当输入，结果走图片修改的正常回填
            scene = get_scene() if get_scene is not None else None
            path = scene.get(chosen_image()) if isinstance(scene, dict) else ""
            if not (isinstance(path, str) and path and os.path.isfile(path)):
                messagebox.showwarning("图片修改", "当前场景没有可用的图，提取不了第几步。", parent=dlg)
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
            _call_open_manual(prompt, images, backend, account)

    def _call_open_manual(prompt, images, backend, account) -> None:
        try:
            open_manual(prompt, images, backend, account)
        except TypeError:
            try:
                open_manual(prompt, images, backend)
            except TypeError:
                open_manual(prompt, images)

    def on_submit() -> None:
        """t129u: 一个「提交」键：先问 LLM（Grok / Gemini）和 Chrome 账户，记住上次的选择。"""
        picked = ask_llm_and_account(dlg)
        if picked:
            on_go(picked[0], picked[1])

    from gui.slide_prompt_dialog import big_submit_button

    big_submit_button(dlg, bottom, on_submit, text="提交").pack(side=tk.LEFT, anchor=tk.S, padx=(12, 0))
    dlg.protocol("WM_DELETE_WINDOW", close)
    task_var.trace_add("write", refresh)
    narrative_var.trace_add("write", refresh)
    actor_var.trace_add("write", refresh)
    visual_var.trace_add("write", refresh)
    speaking_var.trace_add("write", refresh)
    refresh()
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

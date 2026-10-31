"""视频提示：先选叙事风格、画面、背景、演进、运镜、动画，再打开手动窗口。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import config
import config_prompt
import project_manager
from gui.prompt_fyi import clean_fyi_history, pack_background_check, pack_fyi_note, prepend_fyi


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
    # 不锁死宽高：内容变长（提示文字换行、FYI 历史等）时窗口会自己长高，按钮不会被裁掉。
    margin = 60
    if h > sh - margin:
        h = sh - margin
        dlg.geometry(f"{w}x{h}+{x}+{y}")
    else:
        dlg.geometry(f"+{x}+{y}")
    dlg.minsize(w, h)
    dlg.deiconify()
    if not getattr(dlg, "_fit_bound", False):
        dlg._fit_bound = True
        dlg.bind("<Configure>", lambda e, d=dlg: _keep_on_screen(d) if e.widget is d else None, add="+")
    try:
        dlg.lift()
    except tk.TclError:
        pass


def _keep_on_screen(dlg: tk.Toplevel) -> None:
    """内容长高后若底部出屏，就把窗口往上挪；同时更新 minsize。"""
    try:
        w = max(int(dlg.winfo_reqwidth()), 200)
        h = int(dlg.winfo_reqheight())
        sh = int(dlg.winfo_screenheight())
        y = int(dlg.winfo_y())
        x = int(dlg.winfo_x())
    except tk.TclError:
        return
    h = min(h, sh - 60)
    dlg.minsize(w, h)
    if y + h > sh - 48:
        ny = max(8, sh - h - 48)
        if ny != y:
            dlg.geometry(f"+{x}+{ny}")


def open_video_prompt_dialog(
    parent,
    anchor,
    *,
    get_scenes,
    get_style,
    copy_text,
    language: str = "",
    host_narrator: str = "",
    get_place=None,
    get_image=None,
    copy_image=None,
    open_manual=None,
    simple_actions=None,
    saved_choice=None,
    save_choice=None,
    on_story_style=None,
    get_actor_portraits=None,
    episode=None,
) -> None:
    """生场视频：上面是简单做法（静态画面 + 声音），下面是高级做法（先选叙事风格、画面、背景、演进、运镜、动画，
    再打开手动窗口，里面放提示词和画面）。

    simple_actions: [(按钮文字, 回调), ...]，点了就关掉本窗口再调用回调。
    ``saved_choice`` 记下上次的叙事风格；关窗或提交时 ``save_choice(dict)`` 记回去。
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

    saved_text = "erase"
    saved_fyi = clean_fyi_history(saved_choice)
    if isinstance(saved_choice, dict):
        picked_text = saved_choice.get("text")
        if picked_text in {k for k, _ in config_prompt.FLOW_CAPTION_CHOICES}:
            saved_text = picked_text
    # 叙事风格 = 主窗口「全场内容 · 故事风格」（project story_style，唯一存值）；旧的 video_prompt.narrative 只在迁移时读一次。
    style_var = tk.StringVar(value=config_prompt.project_story_style())
    narrative_var = tk.StringVar(value=config_prompt.story_style_narrative(style_var.get()))
    text_var = tk.StringVar(value=saved_text)
    # 视频长度：不进提示词，作为 extra 参数交给 CLI自动（Grok Imagine 视频时长）。记在 video_prompt["duration"]。
    saved_duration = saved_choice.get("duration") if isinstance(saved_choice, dict) else None
    duration_var = tk.StringVar(value=saved_duration if saved_duration in ("6s", "10s", "15s") else "15s")
    saved_visual = True
    saved_speaking = True
    saved_actor = False
    saved_override = config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES[0][0]
    if isinstance(saved_choice, dict):
        if "visual" in saved_choice:
            saved_visual = bool(saved_choice["visual"])
        if "speaking" in saved_choice:
            saved_speaking = bool(saved_choice["speaking"])
        if "actor" in saved_choice:
            saved_actor = bool(saved_choice["actor"])
        if saved_choice.get("actor_override") in {
            label for label, _en in config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES
        }:
            saved_override = saved_choice["actor_override"]
    visual_var = tk.BooleanVar(value=saved_visual)
    speaking_var = tk.BooleanVar(value=saved_speaking)
    actor_var = tk.BooleanVar(value=saved_actor)
    override_var = tk.StringVar(value=saved_override)
    # t163u: 画面 / 背景 / 演进 / 运镜 也记在项目 video_prompt 里；对这一场不能用时退回默认，但不覆盖记下的值
    _sv = saved_choice if isinstance(saved_choice, dict) else {}

    def _pick(key, choices, default):
        val = _sv.get(key)
        return val if val in {k for k, _ in choices} else default

    saved_frame = _pick("frame", config_prompt.VIDEO_FLOW_FRAME_CHOICES, "one")
    frame_fallback = (not is_transition and saved_frame == "two"
                      and not (get_image is not None and get_image("clip_image_last")))
    frame_var = tk.StringVar(value="two" if is_transition else ("one" if frame_fallback else saved_frame))
    bg_var = tk.StringVar(value=_pick("bg", config_prompt.VIDEO_FLOW_BACKGROUND_CHOICES, "none"))
    evolve_var = tk.StringVar(value=_pick("evolve", config_prompt.VIDEO_FLOW_EVOLVE_CHOICES, "keep"))
    camera_var = tk.StringVar(value=_pick("camera", config_prompt.VIDEO_FLOW_CAMERA_CHOICES, "none"))
    motion_var = tk.StringVar(value="")

    from gui.slide_prompt_dialog import pack_narrative_choices, pack_scene_field_choices

    narrative_row = ttk.Frame(body)
    narrative_row.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
    style_box = ttk.LabelFrame(narrative_row, text="叙事风格（= 故事风格）", padding=(8, 4))
    style_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.STORY_STYLE_CHOICES:
        ttk.Radiobutton(style_box, text=label, value=value, variable=style_var).pack(anchor=tk.W)
    style_note = ttk.Label(style_box, foreground="#1f5fbf", wraplength=340, justify=tk.LEFT)
    style_note.pack(anchor=tk.W, pady=(4, 0))

    def _on_style(*_a) -> None:
        key = config_prompt.normalize_story_style(style_var.get()) or config_prompt.STORY_STYLE_CHOICES[0][0]
        narrative_var.set(config_prompt.story_style_narrative(key))
        style_note.config(text=config_prompt.story_style_mode_text(key, bool(actor_var.get())))
        if on_story_style is not None:
            try:
                on_story_style(key)  # 写回 project story_style，并同步主窗口的「故事风格」
            except Exception as exc:  # noqa: BLE001
                print(f"视频提示：故事风格没有同步：{exc}")

    def _resync_style(_e=None) -> None:
        """主窗口那边改了故事风格：窗口拿到焦点时跟上。"""
        key = config_prompt.project_story_style()
        if key != style_var.get():
            style_var.set(key)

    style_var.trace_add("write", _on_style)
    actor_var.trace_add("write", lambda *_a: style_note.config(
        text=config_prompt.story_style_mode_text(style_var.get(), bool(actor_var.get()))))
    dlg.bind("<FocusIn>", _resync_style, add="+")
    style_note.config(text=config_prompt.story_style_mode_text(style_var.get(), bool(actor_var.get())))
    if on_story_style is not None:
        try:
            on_story_style(style_var.get())  # 迁移：旧项目只有 video_prompt.narrative 时，这里写成 story_style
        except Exception as exc:  # noqa: BLE001
            print(f"视频提示：故事风格没有同步：{exc}")
    text_box = ttk.LabelFrame(narrative_row, text="说明文字", padding=(8, 4))
    text_box.pack(side=tk.LEFT, anchor=tk.N)
    for value, label in config_prompt.FLOW_CAPTION_CHOICES:
        ttk.Radiobutton(text_box, text=label, value=value, variable=text_var).pack(anchor=tk.W)
    pack_scene_field_choices(
        narrative_row, visual_var, speaking_var, actor_var, override_var, anchor=tk.N
    )

    groups = ttk.Frame(body)
    if not is_transition:
        groups.pack(anchor=tk.W)

    picture_box = ttk.LabelFrame(groups, text="画面", padding=(8, 4))
    picture_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    for value, label in config_prompt.VIDEO_FLOW_FRAME_CHOICES:
        ttk.Radiobutton(picture_box, text=label, value=value, variable=frame_var).pack(anchor=tk.W)

    background_box = ttk.LabelFrame(groups, text="背景", padding=(8, 4))
    background_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    bg_buttons = []
    for value, label in config_prompt.VIDEO_FLOW_BACKGROUND_CHOICES:
        btn = ttk.Radiobutton(background_box, text=label, value=value, variable=bg_var)
        btn.pack(anchor=tk.W)
        bg_buttons.append(btn)

    evolve_box = ttk.LabelFrame(groups, text="演进", padding=(8, 4))
    evolve_box.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
    evolve_buttons = []
    for value, label in config_prompt.VIDEO_FLOW_EVOLVE_CHOICES:
        btn = ttk.Radiobutton(evolve_box, text=label, value=value, variable=evolve_var)
        btn.pack(anchor=tk.W)
        evolve_buttons.append(btn)

    camera_box = ttk.LabelFrame(groups, text="运镜", padding=(8, 4))
    camera_box.pack(side=tk.LEFT, anchor=tk.N)
    for value, label in config_prompt.VIDEO_FLOW_CAMERA_CHOICES:
        ttk.Radiobutton(camera_box, text=label, value=value, variable=camera_var).pack(anchor=tk.W)


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
        return {
            "duration": duration_var.get(),
            "text": text_var.get(),
            "visual": bool(visual_var.get()),
            "speaking": bool(speaking_var.get()),
            "actor": bool(actor_var.get()),
            "actor_override": override_var.get(),
            "image": image_to_save(),
            "fyi_history": get_fyi_history(),
            "background": bool(bg_include_var.get()),
            # t163u: 新加的记忆项（过渡场景 / 没有结束图时退回的画面不写回）
            "frame": saved_frame if (is_transition or (frame_fallback and frame_var.get() == "one")) else frame_var.get(),
            "bg": bg_var.get(),
            "evolve": evolve_var.get(),
            "camera": camera_var.get(),
            "fyi_include": bool(fyi_include_var.get()),
            "backend": backend_var.get(),
            "audio_mode": audio_mode_var.get(),
            "strata_polish": bool(polish_var.get()),  # t166u
        }

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
        keep_words = text_var.get() == "keep"
        for btn in bg_buttons:
            btn.configure(state=("normal" if keep_words else "disabled"))
        go.config(text="提交")
        base = (
            "叙事风格下面的蓝字说明这次怎么讲。写进提示词的内容勾选场景描述、讲话、人物。说明文字决定字怎么处理。"
            + (
                "多画面用起始画面和终止画面。"
                if (is_transition or two)
                else "选「保留」时背景选项才生效。运镜选默认就不写镜头怎么动。"
            )
            + "下面选 Grok / Gemini / MiniMax 再点「提交」：Grok / Gemini 会再问 Chrome 账户，MiniMax 直接提交。"
            + "所有选择都记在项目里，换场景再打开也一样。场景音频（作为说话 / 作为唱歌）只有 MiniMax 能用。"
        )
        hint.config(text=base)

    def close() -> None:
        remember()
        dlg.destroy()

    _episode_state = {"started": False}  # t172u: 全集提交：这一场的提示词做出来了（已交给打磨 / 发送）

    def on_go(backend: str = "grok", account: str = "", deliver=None, quiet: bool = False) -> None:
        fyi_now = (get_fyi_text() or "").strip() if fyi_include_var.get() else ""
        # 什么都没勾、但写了注意 / FYI：只按 FYI 让图动起来（同图片提示「仅修改」）。
        fyi_only = not (visual_var.get() or speaking_var.get() or actor_var.get())
        if fyi_only and fyi_now:
            fyi_now = config_prompt.strip_caption_lines(fyi_now) or fyi_now  # t163u
        if fyi_only and not fyi_now:
            messagebox.showwarning("视频提示", "场景描述、讲话、人物或注意/FYI 至少要有一项。", parent=dlg)
            return
        scenes = [s for s in (get_scenes() or []) if isinstance(s, dict)]
        if not scenes:
            messagebox.showwarning("视频提示", "没有可用场景", parent=dlg)
            return
        style = (get_style() or "").strip()
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]
        frames = "two" if is_transition else frame_var.get()
        field_kw = dict(
            use_visual=bool(visual_var.get()),
            use_speaking=bool(speaking_var.get()),
            use_actor=bool(actor_var.get()),
            actor_override=dict(config_prompt.SLIDE_FLOW_ACTOR_OVERRIDES).get(
                override_var.get(), ""
            ),
        )
        try:
            if fyi_only:
                prompt = config_prompt.build_video_fyi_only_prompt(
                    frames=frames,
                    evolve=evolve_var.get(),
                    visual_style=style,
                    camera=camera_var.get(),
                    text=text_var.get(),
                    duration=duration_var.get(),
                    fyi=fyi_now,
                )
            elif is_transition:
                prompt = config_prompt.build_transition_video_prompt(
                    visual_style=style,
                    scene_content=scenes,
                    transition=transition,
                    language=language or "",
                    host_narrator=host_narrator or "",
                    narrative=narrative_var.get(),
                    story_style=style_var.get(),
                    text=text_var.get(),
                    **field_kw,
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
                    story_style=style_var.get(),
                    text=text_var.get(),
                    **field_kw,
                )
        except ValueError as exc:
            messagebox.showerror("视频提示", str(exc), parent=dlg)
            return
        if fyi_only:
            # FYI 已作为「主要动作」写在最前；背景条件放在后面。
            bg = config_prompt.background_condition_block(bg_region, bg_era, host_narrator) if bg_include_var.get() else ""
            if bg:
                bg = bg.replace("(applies to everything below)", "(applies to the whole clip)")
                prompt = prompt + "\n\n---\n\n" + bg
        else:
            prompt = config_prompt.prepend_background_condition(
                prompt, bg_region, bg_era, host_narrator, include=bool(bg_include_var.get())
            )
            prompt = prepend_fyi(  # t163u: FYI 里讲字幕 / 文字的句子不带
                prompt, config_prompt.strip_caption_lines(get_fyi_text()), include=bool(fyi_include_var.get())
            )
        # 出图比例：16:9 / 9:16（项目画面大小），提示词里没有才加在最前面。
        from gui.picture_prompt_dialog import _project_video_size

        _size = _project_video_size()
        if "OUTPUT FORMAT" not in prompt:
            _aspect = config_prompt.output_aspect_line(_size).replace("output image", "output video").replace("输出的图片", "输出的视频")
            if _aspect:
                prompt = _aspect + "\n\n" + prompt
        images = []
        missing = []
        if get_image is not None:
            # 多画面（起始 + 终止）照旧两张都给；单画面用上面选中的那张。
            start = get_image("clip_image" if frames == "two" else chosen_image()) or ""
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
        # t123u: Grok 单画面：场景图后面按说话人顺序附上有形象图的人，提示词里说明每张图是谁。
        portrait_refs = []
        if backend == "grok" and frames != "two" and images and callable(get_actor_portraits):
            try:
                portrait_refs = list(get_actor_portraits(scenes[0]) or [])[:4]  # Grok 最多 5 张输入图
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 人物形象图没取到：{exc}")
                portrait_refs = []
        if portrait_refs:
            images = images[:1] + [p for _n, _name, p in portrait_refs]
            block = config_prompt.portrait_reference_block(portrait_refs)
            if "OUTPUT FORMAT" in prompt:
                head, sep, rest = prompt.partition("\n\n")
                prompt = head + "\n\n" + block + ("\n\n" + rest if sep else "")
            else:
                prompt = block + "\n\n" + prompt
        # t163u: 三个后端同一份提示词。要点放最前（OUTPUT FORMAT 之后），结尾再强调一次画面干净和光线。
        _scene_audio = bool(get_image("clip_audio")) if get_image is not None else False  # t172u: 每一场自己判断
        _amode = audio_mode_var.get() if (backend == "minimax" and _scene_audio) else "none"
        _tr = transition if is_transition else None
        _start = images[0] if images else ""
        guard = config_prompt.video_guard_block(scenes, _tr, _start, audio_mode=_amode)
        if prompt.startswith("OUTPUT FORMAT"):
            head, sep, rest = prompt.partition("\n\n")
            prompt = head + "\n\n" + guard + ("\n\n" + rest if sep else "")
        else:
            prompt = guard + "\n\n" + prompt
        if _amode == "sing":
            prompt = prompt.replace(
                "Sound: natural sound of the place only. No music of any kind (music is added to the whole film later).",
                "Sound: the given song.")
        prompt = prompt + "\n\n" + config_prompt.video_closing_block(scenes, _tr, _start)
        if backend == "minimax":
            # t165u: 提交给 MiniMax 时把同样的场景内容换成 H3 官方格式（窗口里显示的就是实际发送的）
            _secs = float(str(duration_var.get()).rstrip("sS") or 6)
            try:
                from utility import sd_image_processor as _sdp

                if _amode in ("talk", "sing"):
                    _secs = _sdp.minimax_audio_video_seconds(_sdp.h3_audio_seconds(get_image("clip_audio") or ""))
                _secs = _sdp.minimax_h3_frames(_secs) / float(_sdp.MINIMAX_H3_FPS)
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ MiniMax 时长没算出来：{exc}")
            prompt = config_prompt.build_h3_prompt(
                scenes, frames=frames, transition=_tr, style=style,
                region=bg_region if bg_include_var.get() else "", era=bg_era if bg_include_var.get() else "",
                language=language or "", camera=camera_var.get(), audio_mode=_amode, start_image=_start,
                seconds=_secs, use_visual=bool(visual_var.get()), use_speaking=bool(speaking_var.get()),
                fyi=get_fyi_text() if fyi_include_var.get() else "",
            )
        if missing and quiet:
            print("视频提示：这一场没有" + "、".join(missing) + "，只发已有的图。")
        elif missing:
            messagebox.showinfo(
                "视频提示",
                "这一场没有" + "、".join(missing) + "。提示窗口里只放已有的图。",
                parent=dlg,
            )
        remember()
        extra = {
            "duration": duration_var.get(),
            "resolution": "720p",
            "video_backend": backend,
            "chrome_account": account or "",  # t133u: LLM 窗口的 CLI自动 / 重试 都用这个账户
            "portrait_refs": len(portrait_refs),
            "orientation": "portrait" if _size == "1080x1920" else "landscape",
            "frames": frames,  # t155u: MiniMax 用：two 时第二张图是结束图
        }
        if backend == "minimax" and get_image is not None and _amode in ("talk", "sing"):
            # t155u/t163u: 只有 MiniMax 且选了「作为说话 / 作为唱歌」才把当前场景音频送去对口型
            extra["scene_audio"] = get_image("clip_audio") or ""
            extra["audio_mode"] = _amode

        def _deliver(final_prompt: str) -> None:
            if callable(deliver):  # t172u: 全集提交：交回给批量，不关窗口
                deliver(final_prompt, images, extra)
                return
            try:
                dlg.destroy()
            except tk.TclError:
                pass
            if callable(open_manual):
                try:
                    open_manual(final_prompt, images, extra=extra)
                except TypeError:
                    open_manual(final_prompt, images)  # old callers without extra

        _episode_state["started"] = True
        if not polish_var.get():
            _deliver(prompt)
            return
        # t166u: 本机 Strata 先把提示词打磨精简（后台线程）；失败 / 超时就用原提示词。重试用窗口里已打磨的提示词，不再打磨。
        import threading

        from utility.prompt_polish import polish_video_prompt

        hint.config(text="Strata 精简提示词…（几秒钟，失败会自动用原提示词）", foreground="#1f5fbf")
        try:
            go.state(["disabled"])
        except tk.TclError:
            pass
        box = {}

        def _work() -> None:
            box["v"] = polish_video_prompt(prompt, backend)

        threading.Thread(target=_work, daemon=True).start()

        def _poll() -> None:
            if "v" not in box:
                dlg.after(250, _poll)
                return
            final, why = box["v"]
            print(f"视频提示：{why}")
            _deliver(final)

        dlg.after(250, _poll)

    # FYI / 注意: text persisted in video_prompt; checkbox always ON on open.
    _fyi_box, get_fyi_text, fyi_include_var, get_fyi_history = pack_fyi_note(
        advanced, history=saved_fyi, pady=(0, 8)
    )
    _fyi_box.pack_forget()
    _fyi_box.pack(fill=tk.X, pady=(0, 8), before=actions)
    if isinstance(saved_choice, dict) and "fyi_include" in saved_choice:  # t163u
        fyi_include_var.set(bool(saved_choice["fyi_include"]))

    # 背景：地域 · 时代 · 人物（全场内容），默认勾上；放在 FYI 下面。
    bg_region, bg_era = ("", "")
    if get_place is not None:
        try:
            bg_region, bg_era = get_place()
        except (TypeError, ValueError):
            bg_region, bg_era = ("", "")
    from gui.prompt_fyi import pack_background_block

    _bg_box, bg_include_var = pack_background_block(
        advanced, bg_region, bg_era, host_narrator,
        style=(get_style() or "").strip(), actor_var=actor_var,
        initial=bool(saved_choice.get("background", True)) if isinstance(saved_choice, dict) else True,
        pady=(0, 8),
    )
    # 下方一行：背景（左）+ 交给 LLM 的图 / 长度 / 提交（右，顶端对齐），同全集生成。
    lower = ttk.Frame(advanced)
    lower.pack(fill=tk.X, pady=(0, 8), before=actions)
    _bg_box.pack_forget()
    _bg_box.pack(in_=lower, side=tk.LEFT, anchor=tk.N)
    _bg_box.lift(lower)  # 先建的控件在 lower 之下，需抬到上面才看得见
    actions.pack_forget()
    actions.pack(in_=lower, side=tk.LEFT, anchor=tk.N, padx=(16, 0))
    actions.lift(lower)  # 先建的控件在 lower 之下，需抬到上面才看得见

    from gui.clip_image_choice import pack_clip_image_choice

    # Which image goes to the LLM (single-frame); remembered with the other choices (key "image").
    saved_image = saved_choice.get("image") if isinstance(saved_choice, dict) else ""
    _img_box, chosen_image, image_to_save = pack_clip_image_choice(
        actions,
        (lambda key: get_image(key) if get_image is not None else ""),
        initial=saved_image or "clip_image",
    )
    length_box = ttk.LabelFrame(actions, text="长度", padding=(8, 4))
    length_box.pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
    length_radios = []
    for value, label in (("6s", "6秒"), ("10s", "10秒"), ("15s", "15秒")):
        _rb = ttk.Radiobutton(length_box, text=label, value=value, variable=duration_var)
        _rb.pack(anchor=tk.W)
        length_radios.append(_rb)

    # t161u/t163u: 后端选在对话框里（Grok / Gemini / MiniMax）；场景音频：不加 / 作为说话 / 作为唱歌（只有 MiniMax）
    import config as _cfg_prefs

    try:
        _last_submit = dict(_cfg_prefs.load_yt_tools_prefs().get("video_submit_choice") or {})
    except Exception:  # noqa: BLE001
        _last_submit = {}
    _backends = ("grok", "gemini", "minimax")
    _saved_backend = _sv.get("backend") if _sv.get("backend") in _backends else _last_submit.get("llm")
    backend_var = tk.StringVar(master=dlg, value=_saved_backend if _saved_backend in _backends else "grok")
    _has_audio = bool(get_image("clip_audio")) if get_image is not None else False
    audio_mode_var = tk.StringVar(master=dlg, value=_sv.get("audio_mode") if _sv.get("audio_mode") in ("none", "talk", "sing") else "talk")
    backend_box = ttk.LabelFrame(actions, text="生成", padding=(8, 4))
    backend_box.pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
    for value, label in (("grok", "Grok"), ("gemini", "Gemini"), ("minimax", "MiniMax（ComfyUI）")):
        ttk.Radiobutton(backend_box, text=label, value=value, variable=backend_var).pack(anchor=tk.W)
    audio_box = ttk.LabelFrame(actions, text="场景音频" + ("" if _has_audio else "（这一场没有音频）"), padding=(8, 4))
    audio_box.pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
    audio_radios = []
    for value, label in (("none", "不加"), ("talk", "作为说话"), ("sing", "作为唱歌")):
        _rb = ttk.Radiobutton(audio_box, text=label, value=value, variable=audio_mode_var)
        _rb.pack(anchor=tk.W)
        audio_radios.append(_rb)

    # t166u: 提交前用本机 Strata 精简提示词（默认开，记在项目里）
    polish_var = tk.BooleanVar(master=dlg, value=bool(_sv.get("strata_polish", True)))
    ttk.Checkbutton(backend_box, text="Strata 精简提示词", variable=polish_var).pack(anchor=tk.W, pady=(4, 0))

    def _sync_backend(*_a) -> None:
        mm = backend_var.get() == "minimax"
        for rb in audio_radios:  # 只有 MiniMax 且这一场有音频才能选（选的值照样记着）
            rb.state(["!disabled"] if (mm and _has_audio) else ["disabled"])
        with_audio = mm and _has_audio and audio_mode_var.get() in ("talk", "sing")
        for rb in length_radios:  # 带音频时长度跟音频走
            rb.state(["disabled"] if with_audio else ["!disabled"])

    backend_var.trace_add("write", _sync_backend)
    audio_mode_var.trace_add("write", _sync_backend)
    _sync_backend()
    from gui.slide_prompt_dialog import big_submit_button

    def on_submit() -> None:
        """t161u: 后端在对话框里选好；Grok / Gemini 只再问 Chrome 账户，MiniMax 直接提交。"""
        from gui.picture_prompt_dialog import ask_llm_and_account

        backend = backend_var.get()
        if backend == "minimax":
            try:
                _cfg_prefs.save_yt_tools_prefs({"video_submit_choice": {"llm": "minimax",
                                                                        "account": _last_submit.get("account") or ""}})
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 提交选择没有记下：{exc}")
            on_go("minimax", "")
            return
        picked = ask_llm_and_account(
            dlg, pref_key="video_submit_choice", title=("Grok" if backend == "grok" else "Gemini") + " 提交",
            fixed_backend=backend,
        )
        if picked:
            on_go(picked[0], picked[1])

    go = big_submit_button(dlg, actions, on_submit, text="提交")
    go.pack(side=tk.LEFT, anchor=tk.S, padx=(12, 0))

    EPISODE_MAX_SCENES = 6

    def on_episode_submit() -> None:
        """t172u: 全集提交：用现在的选项，从当前场到本集结束一场一场生成视频（一场做完再提交下一场，最多 6 场）。"""
        import os

        from gui.picture_prompt_dialog import ask_llm_and_account

        try:
            todo, k_no, m_no = episode["scenes"]()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("全集提交", f"没有取到本集的场景：{exc}", parent=dlg)
            return
        todo = [s for s in (todo or []) if isinstance(s, dict)]
        if not todo:
            messagebox.showwarning("全集提交", "本集没有可处理的场景。", parent=dlg)
            return
        n = len(todo)
        if n > EPISODE_MAX_SCENES:
            messagebox.showwarning(
                "全集提交",
                f"从当前第 {k_no} 场到本集结束共 {n} 场，超过 {EPISODE_MAX_SCENES} 场。\n"
                f"请先把这一集分割（每集不超过 {EPISODE_MAX_SCENES} 场），再全集提交。",
                parent=dlg,
            )
            return
        backend = backend_var.get()
        account = ""
        if backend != "minimax":
            picked = ask_llm_and_account(
                dlg, pref_key="video_submit_choice",
                title=("Grok" if backend == "grok" else "Gemini") + " 全集提交", fixed_backend=backend,
            )
            if not picked:
                return
            account = picked[1]
        if not messagebox.askokcancel(
            "全集提交",
            f"用现在的选项生成第 {k_no}–{m_no} 场的视频，共 {n} 场。\n一场做完、下载好再提交下一场。继续吗？",
            parent=dlg,
        ):
            return
        remember()
        state = {"stop": False, "ok": 0, "files": [], "done": False}
        prog = tk.Toplevel(parent)
        prog.title(f"全集提交 · {n} 场")
        prog.transient(parent)
        pvar = tk.StringVar(master=prog, value="准备 …")
        ttk.Label(prog, textvariable=pvar, wraplength=460, justify=tk.LEFT, padding=12).pack(fill=tk.BOTH)
        ttk.Button(prog, text="停止（做完这一场后）", command=lambda: state.update(stop=True)).pack(pady=(0, 10))
        prog.protocol("WM_DELETE_WINDOW", lambda: state.update(stop=True))
        for _w in (go, ep_btn):
            try:
                _w.state(["disabled"])
            except tk.TclError:
                pass
        if callable(episode.get("begin")):
            episode["begin"]()

        def finish(msg: str, ok: bool) -> None:
            if state["done"]:
                return
            state["done"] = True
            try:
                prog.destroy()
            except tk.TclError:
                pass
            if callable(episode.get("end")):
                try:
                    episode["end"](list(state["files"]))
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 全集提交收尾失败：{exc}")
            (messagebox.showinfo if ok else messagebox.showerror)("全集提交", msg, parent=parent)
            try:
                dlg.destroy()
            except tk.TclError:
                pass

        def run(i: int) -> None:
            if state["stop"]:
                finish(f"已停止：{state['ok']}/{n} 场已生成并导入。", True)
                return
            if i >= n:
                finish(f"全集提交完成：{state['ok']} 场的视频都生成并自动导入了（原声 · Clip · 替换）。", True)
                return
            label = f"第{k_no + i}场"
            pvar.set(f"第 {i + 1}/{n} 场（本集{label}）：准备提示词…")
            try:
                episode["select"](todo[i])
            except Exception as exc:  # noqa: BLE001
                finish(f"{label}：切换场景失败（{exc}），已停止。前面完成 {state['ok']} 场。", False)
                return
            _episode_state["started"] = False

            def _one(final_prompt, images, extra) -> None:
                dlg.after(0, lambda: submit(i, label, final_prompt, images, extra))

            try:
                on_go(backend, account, deliver=_one, quiet=True)
            except Exception as exc:  # noqa: BLE001
                finish(f"{label}：提示词出错（{exc}），已停止。前面完成 {state['ok']} 场。", False)
                return
            if not _episode_state["started"]:
                finish(f"{label}：提示词没有做出来（见提示），已停止。前面完成 {state['ok']} 场。", False)

        def submit(i: int, label: str, final_prompt: str, images, extra) -> None:
            pvar.set(f"第 {i + 1}/{n} 场（本集{label}）：生成视频中…")
            try:
                res = open_manual(final_prompt, images, extra=extra)
            except Exception as exc:  # noqa: BLE001
                finish(f"{label}：生成失败（{exc}），已停止。前面完成 {state['ok']} 场。", False)
                return
            path = "" if res is None or hasattr(res, "save") else str(res)
            if not (path and os.path.isfile(path)):
                finish(f"{label}：没有拿到视频（窗口取消或生成失败），已停止。前面完成 {state['ok']} 场。", False)
                return
            state["files"].append(path)
            importer = episode.get("import")
            if not callable(importer):
                state["ok"] += 1
                dlg.after(300, lambda: run(i + 1))
                return
            # t173u: 自动导入这一场（原声、Clip、替换），导入好了再做下一场
            pvar.set(f"第 {i + 1}/{n} 场（本集{label}）：视频已下载，自动导入（原声 · Clip · 替换）…")

            def _imported(ok: bool, why: str) -> None:
                if not ok:
                    finish(f"{label}：视频生成了，但自动导入失败（{why}），已停止。前面完成 {state['ok']} 场。\n"
                           f"视频文件：{path}", False)
                    return
                state["ok"] += 1
                dlg.after(300, lambda: run(i + 1))

            try:
                importer(todo[i], path, lambda ok, why="": dlg.after(0, lambda: _imported(ok, why)))
            except Exception as exc:  # noqa: BLE001
                finish(f"{label}：自动导入出错（{exc}），已停止。前面完成 {state['ok']} 场。", False)

        run(0)

    ep_btn = ttk.Button(actions, text="全集提交", command=on_episode_submit)
    if isinstance(episode, dict) and callable(open_manual):
        ep_btn.pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
    # t155u/t161u: 说清楚声音输入只有 MiniMax 支持
    ttk.Label(
        advanced,
        text="场景音频：仅 MiniMax 能用，选「作为说话」或「作为唱歌」时把当前场景音频一起送去对口型（长度选项灰掉，音频 ≤ 10 秒视频长度跟音频、至少 4 秒，> 10 秒按 15 秒；分辨率按音频长度：≤ 6 秒最高、≤ 10 秒中档、> 10 秒最低），"
        "Grok / Gemini 不支持。" + ("" if _has_audio else "（这一场没有音频）"),
        foreground="#b05a00", wraplength=620, justify=tk.LEFT,
    ).pack(anchor=tk.W, pady=(0, 6), before=lower)
    dlg.protocol("WM_DELETE_WINDOW", close)
    frame_var.trace_add("write", refresh_choices)
    text_var.trace_add("write", refresh_choices)
    narrative_var.trace_add("write", refresh_choices)
    actor_var.trace_add("write", refresh_choices)
    refresh_choices()
    # t163u: 每个单选 / 勾选一改就记到项目 video_prompt（下次、换场景打开都保持）
    for _v in (duration_var, text_var, visual_var, speaking_var, actor_var, override_var, frame_var, bg_var,
               evolve_var, camera_var, fyi_include_var, bg_include_var, backend_var, audio_mode_var, polish_var):
        _v.trace_add("write", lambda *_a: remember())
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

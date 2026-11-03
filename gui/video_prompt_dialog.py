"""视频提示：先选叙事风格、画面、背景、演进、运镜、动画，再打开手动窗口。"""

from __future__ import annotations

import config as _cfg_mm  # t188u: is_minimax（t194u: MiniMax 5070Ti / 5060）
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
    on_scene_record=None,
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

    saved_text = "keywords"  # t203u: 默认「关键字作背景」
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
    if saved_duration == "13s":  # t255u: MiniMax 13 秒改成 12 秒，旧项目存的 13s 当 12s
        saved_duration = "12s"
    duration_var = tk.StringVar(value=saved_duration if saved_duration in ("6s", "10s", "15s", "7s", "12s", "auto") else "auto")  # t227u: 默认「自动」（存过的长度照旧恢复）
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
            "h3_workflow": h3_wf_var.get(),  # t216u: MiniMax 工作流 i2v / r2v
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
        # t225u: 长度「自动」：每一场按自己的 speaking 估算（全集 / 本集从这一场起也是一场一场算）
        _dur = duration_var.get()
        _speech_speed, _speech_normal = 1.0, 0.0  # t151u: 语速档（MiniMax 不加音频的「自动」才会 < 1）
        if _dur == "auto":
            _opts = _LEN_MM if _cfg_mm.is_minimax(backend) else _LEN_STD
            _sp = " ".join(str(s.get("speaking") or "") for s in scenes)
            _will_audio = (_cfg_mm.is_minimax(backend) and audio_mode_var.get() in ("talk", "sing")
                           and get_image is not None and bool(get_image("clip_audio")))
            if _cfg_mm.is_minimax(backend) and not _will_audio:
                # t154u: 正常语速长度：场景音频 > 配音时间轴 > 字数估算
                _norm = None
                try:
                    _ap = (get_image("clip_audio") or "") if (get_image is not None and len(scenes) == 1) else ""
                    if _ap:
                        from utility import sd_image_processor as _sdp0

                        _a = float(_sdp0.h3_audio_seconds(_ap) or 0)
                        if _a > 0:
                            _norm = (_a, "场景音频")
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 场景音频长度没读出来：{exc}")
                if _norm is None:
                    _tl0 = config_prompt.h3_speaker_timeline(scenes[0]) if len(scenes) == 1 else []
                    _norm = _tl0[-1][1] if _tl0 else None
                _dur, _speech_speed, _speech_normal, _why = config_prompt.auto_length_speed_choice(_sp, _opts, _norm)
            else:
                _dur, _why = config_prompt.auto_length_choice(_sp, _opts)
            _cap = str(scenes[0].get("caption") or scenes[0].get("title") or "").strip()
            print(f"⏱ 自动长度：{_cap[:20] or '这一场'} {_why}")
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
                    duration=_dur,
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
            bg = config_prompt.background_condition_block(bg_region, bg_era, host_narrator, bg_stage) if bg_include_var.get() else ""
            if bg:
                bg = bg.replace("(applies to everything below)", "(applies to the whole clip)")
                prompt = prompt + "\n\n---\n\n" + bg
        else:
            prompt = config_prompt.prepend_background_condition(
                prompt, bg_region, bg_era, host_narrator, include=bool(bg_include_var.get()), stage=bg_stage,
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
        # t216u: MiniMax 选了「参考图工作流」时也附肖像（最多 8 张；场景图 + 8 = R2V 的 9 张上限）
        _mm_r2v = _cfg_mm.is_minimax(backend) and h3_wf_var.get() in ("r2v", "r2v_fast8")  # t228u: FastH3 同样附肖像
        if (backend == "grok" or _mm_r2v) and frames != "two" and images and callable(get_actor_portraits):
            try:
                portrait_refs = list(get_actor_portraits(scenes[0]) or [])[: (8 if _mm_r2v else 4)]  # Grok 最多 5 张输入图
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 人物形象图没取到：{exc}")
                portrait_refs = []
        if portrait_refs and _mm_r2v:
            images = images[:1] + [p for _n, _name, p in portrait_refs]  # 提示词段落在 build_h3_prompt 之后加
        elif portrait_refs:
            images = images[:1] + [p for _n, _name, p in portrait_refs]
            block = config_prompt.portrait_reference_block(portrait_refs)
            if "OUTPUT FORMAT" in prompt:
                head, sep, rest = prompt.partition("\n\n")
                prompt = head + "\n\n" + block + ("\n\n" + rest if sep else "")
            else:
                prompt = block + "\n\n" + prompt
        _h3_build = None  # t150u: MiniMax：带人物描述重做提示词
        _h3_people = None
        _h3_visual = ""
        _timeline = []
        # t163u: 三个后端同一份提示词。要点放最前（OUTPUT FORMAT 之后），结尾再强调一次画面干净和光线。
        _scene_audio = bool(get_image("clip_audio")) if get_image is not None else False  # t172u: 每一场自己判断
        _amode = audio_mode_var.get() if (_cfg_mm.is_minimax(backend) and _scene_audio) else "none"
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
        if _cfg_mm.is_minimax(backend):
            # t165u: 提交给 MiniMax 时把同样的场景内容换成 H3 官方格式（窗口里显示的就是实际发送的）
            _secs = 10.0
            try:
                from utility import sd_image_processor as _sdp

                _secs = float(_sdp.minimax_snap_seconds(_dur))  # t200u: 7 / 10 / 12

                if _amode in ("talk", "sing"):
                    _secs = _sdp.minimax_audio_video_seconds(_sdp.h3_audio_seconds(get_image("clip_audio") or ""))
                _secs = _sdp.minimax_h3_frames(_secs) / float(_sdp.MINIMAX_H3_FPS)
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ MiniMax 时长没算出来：{exc}")
            # t150u: <Picture k> = 第 n 个说话人的肖像（参考图工作流才有）；notes = Strata 看图写的人物括号描述
            _pics = {n: k for k, (n, _nm, _p) in enumerate(portrait_refs, 2)} if (portrait_refs and _mm_r2v) else None
            _h3_args = dict(
                frames=frames, transition=_tr, style=style,
                region=bg_region if bg_include_var.get() else "", era=bg_era if bg_include_var.get() else "",
                language=language or "", camera=camera_var.get(), audio_mode=_amode, start_image=_start,
                seconds=_secs, use_visual=bool(visual_var.get()), use_speaking=bool(speaking_var.get()),
                fyi=get_fyi_text() if fyi_include_var.get() else "",
                stage=bg_stage if bg_include_var.get() else None,
                speech_speed=_speech_speed if _amode == "none" else 1.0,
            )
            _h3_refs = list(portrait_refs) if (portrait_refs and _mm_r2v) else []

            def _h3_build(notes=None, _scenes=scenes, _args=_h3_args, _pics=_pics, _refs=_h3_refs):
                p = config_prompt.build_h3_prompt(_scenes, speaker_notes=notes, portrait_pictures=_pics, **_args)
                if _refs:  # t216u: <Picture k> = 谁的肖像
                    p = config_prompt.h3_portrait_reference_block(_refs) + "\n\n" + p
                return p

            prompt = _h3_build(None)
            if _amode == "talk":  # t150u: 每句台词的起止秒（分段时每段只留这段里的台词和说话人）
                _timeline = config_prompt.h3_speaker_timeline(scenes[0]) if scenes else []
            if polish_var.get() and scenes:
                # t150u: Strata 精简前先看场景图 + 每个有肖像的人（原工作流也找肖像，只给 Strata 看，不送 ComfyUI）
                try:
                    _rows = config_prompt.h3_speaker_map(scenes[0])[0]
                    _all = {}
                    if callable(get_actor_portraits):
                        _all = {n: p for n, _nm, p in (get_actor_portraits(scenes[0]) or [])}
                    _h3_people = []
                    for _k, _row in enumerate(_rows, 1):
                        _nm, _ident, _tone = config_prompt._speaker_identity(_row)
                        _h3_people.append((_k, _nm, ", ".join(x for x in (_ident, _tone) if x), _all.get(_k, "")))
                    _h3_visual = " ".join(str(s.get("visual") or "") for s in scenes if isinstance(s, dict)).strip() \
                        if visual_var.get() else ""
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ Strata 人物描述准备失败：{exc}")
                    _h3_people = None
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
            "duration": _dur,
            "resolution": "720p",
            "video_backend": backend,
            "chrome_account": account or "",  # t133u: LLM 窗口的 CLI自动 / 重试 都用这个账户
            "portrait_refs": len(portrait_refs),
            "h3_workflow": h3_wf_var.get() if _cfg_mm.is_minimax(backend) else "i2v",  # t216u
            "orientation": "portrait" if _size == "1080x1920" else "landscape",
            "frames": frames,  # t155u: MiniMax 用：two 时第二张图是结束图
        }
        # t151u: 记下这一场的语速档，导入视频时自动按它放慢（1.0 = 不变速，也记，盖掉旧的）
        _eff_speed = _speech_speed if (_cfg_mm.is_minimax(backend) and _amode == "none") else 1.0
        extra["speech_speed"] = _eff_speed
        try:
            import time as _time

            scenes[0]["video_speech_speed"] = {
                "speed": _eff_speed, "length": _dur, "normal_seconds": _speech_normal,
                "backend": backend, "at": round(_time.time(), 1),
            }
            if callable(on_scene_record):
                on_scene_record()
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ 语速档没记下：{exc}")
        if _cfg_mm.is_minimax(backend) and get_image is not None and _amode in ("talk", "sing"):
            # t155u/t163u: 只有 MiniMax 且选了「作为说话 / 作为唱歌」才把当前场景音频送去对口型
            extra["scene_audio"] = get_image("clip_audio") or ""
            extra["audio_mode"] = _amode
            if _timeline:
                extra["speaker_timeline"] = [list(x) for x in _timeline]  # t150u

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

        def _log_prompt(pre: str, post: str, why: str = "") -> None:
            try:  # t156u: 记下 Strata 前 / 后的提示词（单场）
                if len(scenes) == 1:
                    config_prompt.record_video_prompt_log(scenes[0], pre, post, backend, why)
                    if callable(on_scene_record):
                        on_scene_record()
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 提示词记录没写成：{exc}")

        _episode_state["started"] = True
        if not polish_var.get():
            _log_prompt(prompt, prompt, "没用 Strata")
            _deliver(prompt)
            return
        # t166u: 本机 Strata 先把提示词打磨精简（后台线程）；失败 / 超时就用原提示词。重试用窗口里已打磨的提示词，不再打磨。
        import threading

        from utility.prompt_polish import polish_h3_with_people, polish_video_prompt

        hint.config(text="Strata 精简提示词…（几秒钟，失败会自动用原提示词）", foreground="#1f5fbf")
        try:
            go.state(["disabled"])
        except tk.TclError:
            pass
        box = {}

        def _work() -> None:
            if _h3_build is not None and _h3_people:  # t150u: 先看图写人物描述，再打磨
                def _rb(notes):
                    box["pre"] = _h3_build(notes)  # t156u: 打磨前的那版（带人物描述）
                    return box["pre"]

                box["v"] = polish_h3_with_people(_rb, _h3_people, _start, _h3_visual, backend)
            else:
                box["v"] = polish_video_prompt(prompt, backend)

        threading.Thread(target=_work, daemon=True).start()

        def _poll() -> None:
            if "v" not in box:
                dlg.after(250, _poll)
                return
            final, why = box["v"]
            print(f"视频提示：{why}")
            _log_prompt(box.get("pre") or prompt, final, why)
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
    from utility import story_stage as _story_stage

    bg_stage = _story_stage.capture()  # t191u: 故事舞台（get_place 来自哪里就用哪里的）
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
    # t200u: Grok / Gemini 6/10/15 秒；MiniMax 7/10/12 秒（换后端时就地改字和值，6↔7、10↔10、15↔12）
    _LEN_STD = ("6s", "10s", "15s")
    _LEN_MM = ("7s", "10s", "12s")
    for value, label in (("6s", "6秒"), ("10s", "10秒"), ("15s", "15秒")):
        _rb = ttk.Radiobutton(length_box, text=label, value=value, variable=duration_var)
        _rb.pack(anchor=tk.W)
        length_radios.append(_rb)
    # t225u: 自动 = 每一场按讲话长度挑（不加音频时）；加了音频整组灰掉
    _rb = ttk.Radiobutton(length_box, text="自动", value="auto", variable=duration_var)
    _rb.pack(anchor=tk.W)
    length_radios.append(_rb)

    # t161u/t163u: 后端选在对话框里（Grok / Gemini / MiniMax）；场景音频：不加 / 作为说话 / 作为唱歌（只有 MiniMax）
    import config as _cfg_prefs

    try:
        _last_submit = dict(_cfg_prefs.load_yt_tools_prefs().get("video_submit_choice") or {})
    except Exception:  # noqa: BLE001
        _last_submit = {}
    _backends = ("grok", "gemini") + tuple(k for k, _l in _cfg_prefs.minimax_backend_options())

    def _norm_backend(b):  # t188u: 旧的「minimax」→ MiniMax 5070
        b = str(b or "").strip().lower()
        return _cfg_prefs.minimax_variant_key(b) or b

    _saved_backend = _norm_backend(_sv.get("backend"))
    if _saved_backend not in _backends:
        _saved_backend = _norm_backend(_last_submit.get("llm"))
    backend_var = tk.StringVar(master=dlg, value=_saved_backend if _saved_backend in _backends else "grok")
    _has_audio = bool(get_image("clip_audio")) if get_image is not None else False
    audio_mode_var = tk.StringVar(master=dlg, value=_sv.get("audio_mode") if _sv.get("audio_mode") in ("none", "talk", "sing") else "none")  # t202u: 默认不加；选了记在项目 video_prompt
    backend_box = ttk.LabelFrame(actions, text="生成", padding=(8, 4))
    backend_box.pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
    for value, label in (("grok", "Grok"), ("gemini", "Gemini")) + _cfg_prefs.minimax_backend_options():
        ttk.Radiobutton(backend_box, text=label, value=value, variable=backend_var).pack(anchor=tk.W)
    # t216u: MiniMax 工作流：原工作流（无参考图，FL2VA）/ 参考图工作流（人物肖像，Ref2VA），记在项目 video_prompt
    h3_wf_var = tk.StringVar(master=dlg, value=_sv.get("h3_workflow") if _sv.get("h3_workflow") in ("i2v", "r2v", "r2v_fast8") else "i2v")
    h3_wf_box = ttk.LabelFrame(actions, text="MiniMax 工作流", padding=(8, 4))
    h3_wf_box.pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
    h3_wf_radios = []
    for value, label in (("i2v", "原工作流（无参考图）"), ("r2v", "参考图工作流（人物肖像）"),
                         ("r2v_fast8", "参考图·8步快速（FastH3）")):  # t228u
        _rb = ttk.Radiobutton(h3_wf_box, text=label, value=value, variable=h3_wf_var)
        _rb.pack(anchor=tk.W)
        h3_wf_radios.append(_rb)
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
        mm = _cfg_prefs.is_minimax(backend_var.get())
        _vals = _LEN_MM if mm else _LEN_STD
        for rb, v in zip(length_radios, _vals):
            rb.configure(value=v, text=v[:-1] + "秒")
        _cur = duration_var.get()
        if _cur not in _vals and _cur != "auto":
            _other = _LEN_STD if mm else _LEN_MM
            duration_var.set(_vals[_other.index(_cur)] if _cur in _other else "auto")
        for rb in h3_wf_radios:  # t216u: 只有 MiniMax 能选工作流
            rb.state(["!disabled"] if mm else ["disabled"])
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
        if _cfg_prefs.is_minimax(backend):
            try:
                _cfg_prefs.save_yt_tools_prefs({"video_submit_choice": {"llm": backend,
                                                                        "account": _last_submit.get("account") or ""}})
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 提交选择没有记下：{exc}")
            on_go(backend, "")
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
        if not _cfg_prefs.is_minimax(backend):
            picked = ask_llm_and_account(
                dlg, pref_key="video_submit_choice",
                title=("Grok" if backend == "grok" else "Gemini") + " 全集提交", fixed_backend=backend,
            )
            if not picked:
                return
            account = picked[1]
        _dual = backend == _cfg_prefs.MINIMAX_DUAL_KEY and callable(episode.get("generate"))
        if not messagebox.askokcancel(
            "全集提交",
            f"用现在的选项生成第 {k_no}–{m_no} 场的视频，共 {n} 场。\n"
            + ("MiniMax 双机：两台同时跑，先做完的接下一场，每场做完自动导入。继续吗？" if _dual
               else "一场做完、下载好再提交下一场。继续吗？"),
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

        def run_dual() -> None:
            """t190u: MiniMax 双机全集：主线程一场一场准备提示词（切场景、精简），放进队列；
            每台能连上的机器一个工人取场景生成，导入回主线程一场一场做。中途不弹窗，最后自动关闭的汇总。"""
            import queue as _queue
            import threading as _th

            from utility import minimax_dual as _mmd

            box = _queue.Queue()
            post = box.put
            lines = []

            def log(msg: str) -> None:
                print("🎬 双机全集：" + str(msg))
                lines.append(str(msg))
                del lines[:-10]
                try:
                    pvar.set("\n".join(lines))
                except tk.TclError:
                    pass

            def pump() -> None:
                while True:
                    try:
                        fn = box.get_nowait()
                    except _queue.Empty:
                        break
                    try:
                        fn()
                    except Exception as exc:  # noqa: BLE001
                        print(f"⚠️ 双机全集：{exc}")
                if not state["done"]:
                    dlg.after(150, pump)

            def gen(job, key, status):
                return episode["generate"](job["prompt"], job["images"], job["extra"], key, status)

            def imp(scene, path, cb):
                state["files"].append(path)
                episode["import"](scene, path, cb)

            def done(results) -> None:
                if state["done"]:
                    return
                state["done"] = True
                ok_n = sum(1 for r in results if r.get("ok"))
                rows = [f"{r['label']} · {r.get('server') or '—'} · " + ("✅ " if r.get("ok") else "❌ ") + str(r.get("msg") or "")
                        for r in results]
                msg = f"MiniMax 双机全集：{ok_n}/{n} 场生成并导入。\n" + "\n".join(rows)
                print("🎬 " + msg)
                try:
                    prog.destroy()
                except tk.TclError:
                    pass
                if callable(episode.get("end")):
                    try:
                        episode["end"](list(state["files"]))
                    except Exception as exc:  # noqa: BLE001
                        print(f"⚠️ 全集提交收尾失败：{exc}")
                try:
                    from utility.file_util import show_auto_close_popup

                    show_auto_close_popup(parent, "全集提交", msg, kind="info" if ok_n == n else "warning",
                                          duration_ms=12000)
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 汇总没有显示：{exc}")
                try:
                    dlg.destroy()
                except tk.TclError:
                    pass

            def start(loads) -> None:
                up = [k for k, v in loads.items() if v is not None]
                down = [k for k, v in loads.items() if v is None]
                if not up:
                    finish("MiniMax 双机：两台 ComfyUI 都连不上，没有提交。", False)
                    return
                if down:
                    log("⚠️ " + "、".join(_mmd.server_label(k) for k in down) + " 连不上，只用 "
                        + "、".join(_mmd.server_label(k) for k in up) + " 跑")
                else:
                    log("两台都在线：" + "，".join(f"{_mmd.server_label(k)} {v} 个任务" for k, v in loads.items()))
                runner = _mmd.DualRunner(up, gen, post, imp, log, done, should_stop=lambda: state["stop"])
                runner.start()
                prep(0, runner)

            def prep(i: int, runner) -> None:
                if i >= n or state["stop"]:
                    runner.close()
                    return
                label = f"第{k_no + i}场"
                job = {"i": i, "label": label, "scene": todo[i]}
                log(f"{label}：准备提示词…")

                def nxt():
                    dlg.after(50, lambda: prep(i + 1, runner))

                try:
                    episode["select"](todo[i])
                except Exception as exc:  # noqa: BLE001
                    runner.fail(job, f"切换场景失败：{exc}")
                    nxt()
                    return
                _episode_state["started"] = False

                def _one(final_prompt, images, extra) -> None:
                    def _q():
                        job.update(prompt=final_prompt, images=list(images or []), extra=dict(extra or {}))
                        runner.add(job)
                        log(f"{label}：提示词好了，排队等空闲的机器")
                        nxt()
                    post(_q)

                try:
                    on_go(backend, "", deliver=_one, quiet=True)
                except Exception as exc:  # noqa: BLE001
                    runner.fail(job, f"提示词出错：{exc}")
                    nxt()
                    return
                if not _episode_state["started"]:
                    runner.fail(job, "提示词没有做出来")
                    nxt()

            pvar.set("MiniMax 双机：检查两台 ComfyUI …")
            _th.Thread(target=lambda: post(lambda l=_mmd.probe_servers(): start(l)), daemon=True).start()
            pump()

        if _dual:
            run_dual()
            return
        run(0)

    ep_btn = ttk.Button(actions, text="全集提交", command=on_episode_submit)
    if isinstance(episode, dict) and callable(open_manual):
        ep_btn.pack(side=tk.LEFT, anchor=tk.S, padx=(8, 0))
    # t155u/t161u: 说清楚声音输入只有 MiniMax 支持
    ttk.Label(
        advanced,
        text="场景音频：仅 MiniMax 能用，选「作为说话」或「作为唱歌」时把当前场景音频一起送去对口型（长度选项灰掉，视频长度跟音频、至少 4 秒；音频 > 12 秒自动分成几段（每段 ≤ 12 秒、切在停顿处），同一台机器依次生成，后一段接前一段最后一帧，再接起来换原声导入）。选「不加」时不送音频，也从不分段：一场只生成一段，长度 7 / 10 / 12 秒（「自动」按台词估算；"
        "12 秒放不下就用 12 秒加语速档让人物说快，导入时按同一档放慢）。分辨率固定 1120×640（竖屏 640×1120）。"
        "Grok / Gemini 不支持。"
        "「MiniMax 双机」：单场提交轮流用 5070Ti / 5060（忙或连不上就换另一台）；全集提交两台同时跑，先做完的接下一场。"
        + ("" if _has_audio else "（这一场没有音频）"),
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
    # t203u: 交给 LLM 的图、注意 / FYI 文字也是一改就记（原来只在关窗 / 提交时记）
    _img_var = getattr(_img_box, "_choice_var", None)
    if _img_var is not None:
        _img_var.trace_add("write", lambda *_a: remember())
    dlg.bind("<KeyRelease>", lambda _e: dlg.after_idle(remember), add="+")
    near = anchor if anchor is not None else parent
    _place_popup_near(dlg, near, below=True)

# -*- coding: utf-8 -*-
"""t235u: video submit confirm dialog + preview→project clone look pass-through."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"D:\AIComposer")

CONFIRM_FN = r'''
def ask_video_submit_confirm(
    parent,
    *,
    title: str = "提交前确认",
    initial: dict | None = None,
    note: str = "",
):
    """t235u: 提交 / 全集提交前再确认一次全场背景选项（可改）。

    initial 键：visual_style / scene_style / story_style / narrator / region / era / background。
    确定 → 返回改后的 dict；取消 / Esc → None。
    """
    import tkinter as tk
    from tkinter import ttk

    import config
    import config_prompt

    init = dict(initial or {})
    box = tk.Toplevel(parent)
    box.title(title)
    box.transient(parent)
    box.resizable(False, False)
    try:
        box.grab_set()
    except tk.TclError:
        pass

    frm = ttk.Frame(box, padding=14)
    frm.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        frm,
        text="请再核对一次下面的选项（生成时间较长，确认后再提交）：",
        wraplength=520,
        justify=tk.LEFT,
    ).pack(anchor=tk.W, pady=(0, 10))

    grid = ttk.Frame(frm)
    grid.pack(fill=tk.X)
    for c in (0, 1):
        grid.columnconfigure(c, weight=1 if c == 1 else 0)

    def _row(r: int, label: str, widget):
        ttk.Label(grid, text=label).grid(row=r, column=0, sticky=tk.W, pady=3, padx=(0, 8))
        widget.grid(row=r, column=1, sticky=tk.EW, pady=3)

    vs_opts = list(config.VISUAL_STYLE_OPTIONS or [])
    vs0 = config.match_visual_style(init.get("visual_style") or "") or (
        vs_opts[0] if vs_opts else ""
    )
    vs_var = tk.StringVar(master=box, value=vs0)
    vs_cb = ttk.Combobox(grid, textvariable=vs_var, values=vs_opts, state="readonly", width=42)
    _row(0, "画面风格", vs_cb)

    ss_labels = list(config_prompt.SCENE_STYLE_LABELS or [])
    ss_key = config_prompt.normalize_scene_style(init.get("scene_style"))
    ss_label = next(
        (lab for key, lab, *_rest in [
            (k, (k.split(" (")[0] if k else "(空)"),) for k, _en, _d in config_prompt.SCENE_STYLE_CHOICES
        ] if False),
        None,
    )
    # map stored key → combobox label (SCENE_STYLE_LABELS aligns with CHOICES)
    ss_by_key = {}
    for i, (key, _en, _desc) in enumerate(config_prompt.SCENE_STYLE_CHOICES):
        lab = config_prompt.SCENE_STYLE_LABELS[i] if i < len(config_prompt.SCENE_STYLE_LABELS) else (key or "(空)")
        ss_by_key[key] = lab
    ss0 = ss_by_key.get(ss_key, ss_labels[0] if ss_labels else "(空)")
    ss_var = tk.StringVar(master=box, value=ss0)
    ss_cb = ttk.Combobox(grid, textvariable=ss_var, values=ss_labels, state="readonly", width=42)
    _row(1, "场景风格", ss_cb)

    story_pairs = list(config_prompt.STORY_STYLE_CHOICES or [])
    story_vals = [k for k, _ in story_pairs]
    story_labs = {k: lab for k, lab in story_pairs}
    st0 = config_prompt.normalize_story_style(init.get("story_style")) or (story_vals[0] if story_vals else "")
    story_var = tk.StringVar(master=box, value=st0)
    story_cb = ttk.Combobox(
        grid,
        textvariable=tk.StringVar(master=box, value=story_labs.get(st0, st0)),
        values=[lab for _k, lab in story_pairs],
        state="readonly",
        width=42,
    )
    # keep key in story_var; combobox shows label
    _story_label_var = story_cb.cget("textvariable")
    # Combobox above used anonymous StringVar — redo cleanly:
    story_label_var = tk.StringVar(master=box, value=story_labs.get(st0, st0))
    story_cb.destroy()
    story_cb = ttk.Combobox(
        grid, textvariable=story_label_var,
        values=[lab for _k, lab in story_pairs], state="readonly", width=42,
    )
    _row(2, "叙事风格", story_cb)

    narr_opts = [""] + [x for x in config.narrator_person_options() if (x or "").strip()]
    nar0 = (init.get("narrator") or "").strip()
    if nar0 and nar0 not in narr_opts:
        narr_opts = narr_opts + [nar0]
    nar_var = tk.StringVar(master=box, value=nar0)
    nar_cb = ttk.Combobox(grid, textvariable=nar_var, values=narr_opts, width=42)
    _row(3, "默认讲员", nar_cb)

    regions = [""] + list(config_prompt.SETTING_PLACES.keys())
    reg0 = (init.get("region") or "").strip()
    if reg0 and reg0 not in regions:
        regions = regions + [reg0]
    reg_var = tk.StringVar(master=box, value=reg0 if reg0 in regions else "")
    reg_cb = ttk.Combobox(grid, textvariable=reg_var, values=regions, state="readonly", width=42)
    _row(4, "地域", reg_cb)

    era_var = tk.StringVar(master=box, value=(init.get("era") or "").strip())
    era_cb = ttk.Combobox(grid, textvariable=era_var, values=(), state="readonly", width=42)
    _row(5, "时代", era_cb)

    def _sync_eras(*_a):
        region = (reg_var.get() or "").strip()
        eras = list(config_prompt.setting_era_labels(region) or [])
        era_cb.configure(values=eras)
        cur = (era_var.get() or "").strip()
        if cur not in eras:
            era_var.set(eras[0] if eras else "")

    reg_var.trace_add("write", _sync_eras)
    _sync_eras()

    bg_var = tk.BooleanVar(master=box, value=bool(init.get("background", True)))
    ttk.Checkbutton(
        frm, text="背景（地域 · 时代 · 讲员）写入提示词", variable=bg_var
    ).pack(anchor=tk.W, pady=(10, 0))

    if (note or "").strip():
        ttk.Label(frm, text=note.strip(), foreground="#333", wraplength=520, justify=tk.LEFT).pack(
            anchor=tk.W, pady=(10, 0)
        )

    res = {"v": None}
    btns = ttk.Frame(frm)
    btns.pack(fill=tk.X, pady=(14, 0))

    def _cancel(_e=None):
        res["v"] = None
        try:
            box.destroy()
        except tk.TclError:
            pass

    def _ok(_e=None):
        # map story label → key
        lab = (story_label_var.get() or "").strip()
        st_key = next((k for k, l in story_pairs if l == lab), "") or config_prompt.normalize_story_style(lab)
        ss_lab = (ss_var.get() or "").strip()
        ss_key = ""
        for i, (key, _en, _desc) in enumerate(config_prompt.SCENE_STYLE_CHOICES):
            lab_i = config_prompt.SCENE_STYLE_LABELS[i] if i < len(config_prompt.SCENE_STYLE_LABELS) else (key or "(空)")
            if lab_i == ss_lab:
                ss_key = key
                break
        res["v"] = {
            "visual_style": config.match_visual_style(vs_var.get() or "") or (vs_var.get() or "").strip(),
            "scene_style": ss_key,
            "story_style": st_key,
            "narrator": (nar_var.get() or "").strip(),
            "region": (reg_var.get() or "").strip(),
            "era": (era_var.get() or "").strip(),
            "background": bool(bg_var.get()),
        }
        try:
            box.destroy()
        except tk.TclError:
            pass

    ttk.Button(btns, text="确定提交", command=_ok).pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(btns, text="取消", command=_cancel).pack(side=tk.RIGHT)
    box.bind("<Escape>", _cancel)
    box.bind("<Return>", _ok)
    box.update_idletasks()
    try:
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - box.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - box.winfo_height()) // 3)
        box.geometry(f"+{px}+{py}")
    except tk.TclError:
        pass
    box.focus_set()
    box.wait_window()
    return res["v"]


'''

# Fix the messy story_style label mapping in CONFIRM_FN — rewrite cleaner version
CONFIRM_FN = r'''
def ask_video_submit_confirm(
    parent,
    *,
    title: str = "提交前确认",
    initial: dict | None = None,
    note: str = "",
):
    """t235u: 提交 / 全集提交前再确认一次全场背景选项（可改）。

    initial 键：visual_style / scene_style / story_style / narrator / region / era / background。
    确定 → 返回改后的 dict；取消 / Esc → None。
    """
    import tkinter as tk
    from tkinter import ttk

    import config
    import config_prompt

    init = dict(initial or {})
    box = tk.Toplevel(parent)
    box.title(title)
    box.transient(parent)
    box.resizable(False, False)
    try:
        box.grab_set()
    except tk.TclError:
        pass

    frm = ttk.Frame(box, padding=14)
    frm.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        frm,
        text="请再核对一次下面的选项（生成时间较长，确认后再提交）：",
        wraplength=520,
        justify=tk.LEFT,
    ).pack(anchor=tk.W, pady=(0, 10))

    grid = ttk.Frame(frm)
    grid.pack(fill=tk.X)
    grid.columnconfigure(1, weight=1)

    def _row(r: int, label: str, widget):
        ttk.Label(grid, text=label).grid(row=r, column=0, sticky=tk.W, pady=3, padx=(0, 8))
        widget.grid(row=r, column=1, sticky=tk.EW, pady=3)

    vs_opts = list(config.VISUAL_STYLE_OPTIONS or [])
    vs0 = config.match_visual_style(init.get("visual_style") or "") or (vs_opts[0] if vs_opts else "")
    vs_var = tk.StringVar(master=box, value=vs0)
    _row(0, "画面风格", ttk.Combobox(grid, textvariable=vs_var, values=vs_opts, state="readonly", width=42))

    # SCENE_STYLE_LABELS[i] ↔ SCENE_STYLE_CHOICES[i][0]
    ss_labels = list(config_prompt.SCENE_STYLE_LABELS or [])
    ss_key_to_lab = {}
    ss_lab_to_key = {}
    for i, (key, _en, _desc) in enumerate(config_prompt.SCENE_STYLE_CHOICES):
        lab = ss_labels[i] if i < len(ss_labels) else (key.split(" (")[0] if key else "(空)")
        ss_key_to_lab[key] = lab
        ss_lab_to_key[lab] = key
    ss_key = config_prompt.normalize_scene_style(init.get("scene_style"))
    ss_var = tk.StringVar(master=box, value=ss_key_to_lab.get(ss_key, ss_labels[0] if ss_labels else "(空)"))
    _row(1, "场景风格", ttk.Combobox(grid, textvariable=ss_var, values=ss_labels, state="readonly", width=42))

    story_pairs = list(config_prompt.STORY_STYLE_CHOICES or [])
    story_lab_to_key = {lab: key for key, lab in story_pairs}
    story_key_to_lab = {key: lab for key, lab in story_pairs}
    st0 = config_prompt.normalize_story_style(init.get("story_style")) or (story_pairs[0][0] if story_pairs else "")
    story_label_var = tk.StringVar(master=box, value=story_key_to_lab.get(st0, st0))
    _row(
        2,
        "叙事风格",
        ttk.Combobox(
            grid,
            textvariable=story_label_var,
            values=[lab for _k, lab in story_pairs],
            state="readonly",
            width=42,
        ),
    )

    narr_opts = [""] + [x for x in config.narrator_person_options() if (x or "").strip()]
    nar0 = (init.get("narrator") or "").strip()
    if nar0 and nar0 not in narr_opts:
        narr_opts = narr_opts + [nar0]
    nar_var = tk.StringVar(master=box, value=nar0)
    _row(3, "默认讲员", ttk.Combobox(grid, textvariable=nar_var, values=narr_opts, width=42))

    regions = [""] + list(config_prompt.SETTING_PLACES.keys())
    reg0 = (init.get("region") or "").strip()
    if reg0 and reg0 not in regions:
        regions = regions + [reg0]
    reg_var = tk.StringVar(master=box, value=reg0 if reg0 in regions else "")
    _row(4, "地域", ttk.Combobox(grid, textvariable=reg_var, values=regions, state="readonly", width=42))

    era_var = tk.StringVar(master=box, value=(init.get("era") or "").strip())
    era_cb = ttk.Combobox(grid, textvariable=era_var, values=(), state="readonly", width=42)
    _row(5, "时代", era_cb)

    def _sync_eras(*_a):
        region = (reg_var.get() or "").strip()
        eras = list(config_prompt.setting_era_labels(region) or [])
        era_cb.configure(values=eras)
        if (era_var.get() or "").strip() not in eras:
            era_var.set(eras[0] if eras else "")

    reg_var.trace_add("write", _sync_eras)
    _sync_eras()

    bg_var = tk.BooleanVar(master=box, value=bool(init.get("background", True)))
    ttk.Checkbutton(frm, text="背景（地域 · 时代 · 讲员）写入提示词", variable=bg_var).pack(
        anchor=tk.W, pady=(10, 0)
    )

    if (note or "").strip():
        ttk.Label(frm, text=note.strip(), foreground="#333", wraplength=520, justify=tk.LEFT).pack(
            anchor=tk.W, pady=(10, 0)
        )

    res = {"v": None}
    btns = ttk.Frame(frm)
    btns.pack(fill=tk.X, pady=(14, 0))

    def _cancel(_e=None):
        res["v"] = None
        try:
            box.destroy()
        except tk.TclError:
            pass

    def _ok(_e=None):
        lab = (story_label_var.get() or "").strip()
        st_key = story_lab_to_key.get(lab) or config_prompt.normalize_story_style(lab)
        ss_lab = (ss_var.get() or "").strip()
        res["v"] = {
            "visual_style": config.match_visual_style(vs_var.get() or "") or (vs_var.get() or "").strip(),
            "scene_style": ss_lab_to_key.get(ss_lab, ""),
            "story_style": st_key,
            "narrator": (nar_var.get() or "").strip(),
            "region": (reg_var.get() or "").strip(),
            "era": (era_var.get() or "").strip(),
            "background": bool(bg_var.get()),
        }
        try:
            box.destroy()
        except tk.TclError:
            pass

    ttk.Button(btns, text="确定提交", command=_ok).pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(btns, text="取消", command=_cancel).pack(side=tk.RIGHT)
    box.bind("<Escape>", _cancel)
    box.bind("<Return>", _ok)
    box.update_idletasks()
    try:
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - box.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - box.winfo_height()) // 3)
        box.geometry(f"+{px}+{py}")
    except tk.TclError:
        pass
    box.focus_set()
    box.wait_window()
    return res["v"]


'''

def main():
    vpd = ROOT / "gui" / "video_prompt_dialog.py"
    text = vpd.read_text(encoding="utf-8")
    if "def ask_video_submit_confirm" in text:
        print("confirm fn already present")
    else:
        # Insert before open_video_prompt_dialog
        anchor = "def open_video_prompt_dialog("
        if anchor not in text:
            raise SystemExit("open_video_prompt_dialog not found")
        text = text.replace(anchor, CONFIRM_FN + anchor, 1)
        print("inserted ask_video_submit_confirm")

    # Add apply_look param
    old_sig = """def open_video_prompt_dialog(
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
) -> None:"""
    new_sig = """def open_video_prompt_dialog(
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
    apply_look=None,
) -> None:"""
    if "apply_look=None" not in text:
        if old_sig not in text:
            raise SystemExit("signature block not found")
        text = text.replace(old_sig, new_sig, 1)
        print("added apply_look param")
    else:
        print("apply_look already in signature")

    # After pack_background_block / bg_include_var setup, init _look and helper.
    # Find the block that sets bg and insert _look + _confirm helper nearby.
    marker = """    _bg_box, bg_include_var = pack_background_block(
        advanced, bg_region, bg_era, host_narrator,
        style=(get_style() or "").strip(), actor_var=actor_var,
        initial=bool(saved_choice.get("background", True)) if isinstance(saved_choice, dict) else True,
        pady=(0, 8),
    )"""
    if "_look = {" in text and "t235u" in text:
        print("_look already wired")
    else:
        if marker not in text:
            raise SystemExit("pack_background_block call not found")
        inject = marker + """
    # t235u: 提交前可改的背景 / 风格快照（on_go 读这里，避免只改主窗口却用到开窗时的旧值）
    import config as _cfg_look

    _look = {
        "visual_style": (get_style() or "").strip(),
        "scene_style": config_prompt.project_scene_style(),
        "story_style": style_var.get(),
        "narrator": (host_narrator or "").strip(),
        "region": (bg_region or "").strip(),
        "era": (bg_era or "").strip(),
        "background": bool(bg_include_var.get()),
    }

    def _confirm_before_submit(*, episode_note: str = "") -> bool:
        \"\"\"t235u: 弹出可编辑确认；写入 _look / 勾选框 / 叙事风格，并回写主窗口全场内容。\"\"\"
        _look["visual_style"] = (get_style() or "").strip() or _look.get("visual_style") or ""
        _look["scene_style"] = config_prompt.project_scene_style()
        _look["story_style"] = style_var.get()
        _look["background"] = bool(bg_include_var.get())
        edited = ask_video_submit_confirm(
            dlg,
            title=("全集提交前确认" if episode_note else "提交前确认"),
            initial=_look,
            note=episode_note,
        )
        if not edited:
            return False
        _look.update(edited)
        bg_include_var.set(bool(edited.get("background", True)))
        st = config_prompt.normalize_story_style(edited.get("story_style"))
        if st:
            style_var.set(st)
            if on_story_style is not None:
                try:
                    on_story_style(st)
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠️ 叙事风格没有同步：{exc}")
        if callable(apply_look):
            try:
                apply_look(dict(_look))
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 全场内容没有写回主窗口：{exc}")
        return True
"""
        text = text.replace(marker, inject, 1)
        print("injected _look + _confirm_before_submit")

    # Patch on_go to use _look for style / region / era / narrator
    # Replace first style = (get_style()...
    old_style = """        style = (get_style() or "").strip()
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]"""
    new_style = """        style = (_look.get("visual_style") or get_style() or "").strip()  # t235u
        if not style:
            style = (project_manager.LAST_VISUAL_STYLE or "").strip() or config.VISUAL_STYLE_OPTIONS[0]
        _host = (_look.get("narrator") or host_narrator or "").strip()
        _reg = (_look.get("region") or "").strip()
        _era = (_look.get("era") or "").strip()"""
    if "_host = (_look.get" in text:
        print("on_go look reads already present")
    else:
        if old_style not in text:
            raise SystemExit("style block in on_go not found")
        text = text.replace(old_style, new_style, 1)
        # Replace host_narrator=host_narrator or "" in build calls inside on_go — careful, only the prompt builds
        text = text.replace(
            """                    host_narrator=host_narrator or "",
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
                )""",
            """                    host_narrator=_host,
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
                    host_narrator=_host,
                    camera=camera_var.get(),
                    motion=motion_var.get(),
                    narrative=narrative_var.get(),
                    story_style=style_var.get(),
                    text=text_var.get(),
                    **field_kw,
                )""",
            1,
        )
        text = text.replace(
            """            bg = config_prompt.background_condition_block(bg_region, bg_era, host_narrator, bg_stage) if bg_include_var.get() else ""
            if bg:
                bg = bg.replace("(applies to everything below)", "(applies to the whole clip)")
                prompt = prompt + "\\n\\n---\\n\\n" + bg
        else:
            prompt = config_prompt.prepend_background_condition(
                prompt, bg_region, bg_era, host_narrator, include=bool(bg_include_var.get()), stage=bg_stage,
            )""",
            """            bg = config_prompt.background_condition_block(_reg, _era, _host, bg_stage) if bg_include_var.get() else ""
            if bg:
                bg = bg.replace("(applies to everything below)", "(applies to the whole clip)")
                prompt = prompt + "\\n\\n---\\n\\n" + bg
        else:
            prompt = config_prompt.prepend_background_condition(
                prompt, _reg, _era, _host, include=bool(bg_include_var.get()), stage=bg_stage,
            )""",
            1,
        )
        print("on_go uses _look for style/place/narrator")

    # Wire on_submit
    old_on_submit = '''    def on_submit() -> None:
        """t161u: 后端在对话框里选好；Grok / Gemini 只再问 Chrome 账户，MiniMax 直接提交。"""
        from gui.picture_prompt_dialog import ask_llm_and_account

        backend = backend_var.get()
        if _cfg_prefs.is_minimax(backend):
'''
    new_on_submit = '''    def on_submit() -> None:
        """t161u: 后端在对话框里选好；Grok / Gemini 只再问 Chrome 账户，MiniMax 直接提交。
        t235u: 提交前先确认画面风格 / 场景风格 / 讲员 / 地域 · 时代。"""
        from gui.picture_prompt_dialog import ask_llm_and_account

        if not _confirm_before_submit():
            return
        backend = backend_var.get()
        if _cfg_prefs.is_minimax(backend):
'''
    if "t235u: 提交前先确认" in text:
        print("on_submit already patched")
    else:
        if old_on_submit not in text:
            raise SystemExit("on_submit not found")
        text = text.replace(old_on_submit, new_on_submit, 1)
        print("patched on_submit")

    # Wire on_episode_submit: confirm after validation, replace askokcancel
    old_ep_acct = '''        backend = backend_var.get()
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
            f"用现在的选项生成第 {k_no}–{m_no} 场的视频，共 {n} 场。\\n"
            + ("MiniMax 双机：两台同时跑，先做完的接下一场，每场做完自动导入。继续吗？" if _dual
               else "一场做完、下载好再提交下一场。继续吗？"),
            parent=dlg,
        ):
            return
        remember()
'''
    new_ep_acct = '''        backend = backend_var.get()
        account = ""
        _dual = backend == _cfg_prefs.MINIMAX_DUAL_KEY and callable(episode.get("generate"))
        _ep_note = (
            f"将用以上选项生成第 {k_no}–{m_no} 场的视频，共 {n} 场。"
            + (" MiniMax 双机：两台同时跑，先做完的接下一场。" if _dual
               else " 一场做完、下载好再提交下一场。")
        )
        if not _confirm_before_submit(episode_note=_ep_note):
            return
        if not _cfg_prefs.is_minimax(backend):
            picked = ask_llm_and_account(
                dlg, pref_key="video_submit_choice",
                title=("Grok" if backend == "grok" else "Gemini") + " 全集提交", fixed_backend=backend,
            )
            if not picked:
                return
            account = picked[1]
        remember()
'''
    if "全集提交前确认" in text and "_ep_note" in text:
        print("on_episode_submit already patched")
    else:
        if old_ep_acct not in text:
            # show nearby for debug
            idx = text.find("backend = backend_var.get()\n        account = \"\"")
            print("NEAR", repr(text[idx:idx+500]) if idx>=0 else "not found")
            raise SystemExit("on_episode_submit account/askokcancel block not found")
        text = text.replace(old_ep_acct, new_ep_acct, 1)
        print("patched on_episode_submit")

    # Docstring mention apply_look
    if "apply_look" in text and "t235u" in text:
        pass

    vpd.write_text(text, encoding="utf-8")
    # strip BOM if any
    raw = vpd.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        vpd.write_bytes(raw[3:])
        print("stripped BOM from video_prompt_dialog")
    print("video_prompt_dialog written")


if __name__ == "__main__":
    main()

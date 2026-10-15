# -*- coding: utf-8 -*-
"""Patch fade in/out for 导入视频 dialog."""
from pathlib import Path

dialog = Path("gui/mp4_pick_preview_dialog.py")
text = dialog.read_text(encoding="utf-8")

old_ui = '''    video_fade_in_on = tk.BooleanVar(value=False)
    video_fade_out_on = tk.BooleanVar(value=False)
    video_fade_in_sec = tk.DoubleVar(value=1.0)
    video_fade_out_sec = tk.DoubleVar(value=1.0)
    if audio_edit:
        def _pack_video_fade(parent, label: str, flag, seconds) -> None:
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=(0, 4))
            ttk.Checkbutton(row, text=label, variable=flag).pack(side=tk.LEFT)
            ttk.Spinbox(
                row, from_=0.5, to=3.0, increment=0.5, width=6, textvariable=seconds,
            ).pack(side=tk.LEFT, padx=(8, 4))
            ttk.Label(row, text="秒，最长 3 秒").pack(side=tk.LEFT)

        _pack_video_fade(trim_box, "淡入", video_fade_in_on, video_fade_in_sec)
        _pack_video_fade(trim_box, "淡出", video_fade_out_on, video_fade_out_sec)
'''

new_ui = '''    video_fade_in_on = tk.BooleanVar(value=False)
    video_fade_out_on = tk.BooleanVar(value=False)
    video_fade_in_sec = tk.DoubleVar(value=1.0)
    video_fade_out_sec = tk.DoubleVar(value=1.0)
    # 成片画面淡入/淡出（默认关=0 秒）。另有“同时淡变声音”：原声/混音可用，配声禁用。
    audio_fade_var = tk.BooleanVar(value=True)
    audio_fade_chk_holder: list = [None]

    def _pack_video_fade(parent, label: str, flag, seconds) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=(0, 4))
        ttk.Checkbutton(row, text=label, variable=flag).pack(side=tk.LEFT)
        ttk.Spinbox(
            row, from_=0.0, to=3.0, increment=0.5, width=6, textvariable=seconds,
        ).pack(side=tk.LEFT, padx=(8, 4))
        ttk.Label(row, text="秒，最长 3 秒").pack(side=tk.LEFT)

    _pack_video_fade(trim_box, "淡入", video_fade_in_on, video_fade_in_sec)
    _pack_video_fade(trim_box, "淡出", video_fade_out_on, video_fade_out_sec)
    audio_fade_row = ttk.Frame(trim_box)
    audio_fade_row.pack(fill=tk.X, pady=(0, 4))
    audio_fade_chk = ttk.Checkbutton(
        audio_fade_row,
        text="同时淡变声音（原声/混音；配声不可用）",
        variable=audio_fade_var,
    )
    audio_fade_chk.pack(side=tk.LEFT)
    audio_fade_chk_holder[0] = audio_fade_chk
'''

if old_ui not in text:
    raise SystemExit("UI block not found")
text = text.replace(old_ui, new_ui, 1)

# Insert _sync_audio_fade_gate after _target_ok / near _apply_ui helpers.
# Find a good anchor after radio_var is defined — insert after dest_var.trace_add
anchor = '''    dest_var.trace_add("write", lambda *_a: _apply_ui())
    source_var = tk.StringVar(value=(current["key"] if sources else ""))
'''
gate_fn = '''    dest_var.trace_add("write", lambda *_a: _apply_ui())

    def _audio_fade_allowed() -> bool:
        # 配声 = 整条换成旁白/场景声，不给导入声做淡变；原声/混音才允许。
        if audio_edit:
            return audio_use_var.get() != "replace"
        if radio_holder[0]:
            return radio_var.get() != "replace_speed"
        return True

    def _sync_audio_fade_gate(*_a) -> None:
        allowed = _audio_fade_allowed()
        chk = audio_fade_chk_holder[0]
        if chk is not None:
            try:
                chk.state(["!disabled"] if allowed else ["disabled"])
            except tk.TclError:
                pass
        if not allowed:
            audio_fade_var.set(False)
        elif not audio_fade_var.get() and _a:
            # 从配声切回原声/混音时恢复默认勾选
            audio_fade_var.set(True)

    source_var = tk.StringVar(value=(current["key"] if sources else ""))
'''
if anchor not in text:
    raise SystemExit("dest_var anchor not found")
text = text.replace(anchor, gate_fn, 1)

# Hook radio_var traces after _fill_actions builds radios — extend _show_mix_level block
# and also call _sync_audio_fade_gate at end of _fill_actions.
old_fill_tail = '''                radio_var.trace_add("write", _show_mix_level)
                _show_mix_level()
        ttk.Button(btn_host, text="取消", command=_close).pack(side=tk.RIGHT, padx=(6, 0))
'''
new_fill_tail = '''                radio_var.trace_add("write", _show_mix_level)
                _show_mix_level()
            radio_var.trace_add("write", _sync_audio_fade_gate)
        _sync_audio_fade_gate()
        ttk.Button(btn_host, text="取消", command=_close).pack(side=tk.RIGHT, padx=(6, 0))
'''
if old_fill_tail not in text:
    raise SystemExit("fill_actions tail not found")
text = text.replace(old_fill_tail, new_fill_tail, 1)

# Also sync when audio_edit use mode changes — find _sync_audio_edit and add call
# Look for def _sync_audio_edit
marker = "    def _sync_audio_edit() -> None:\n"
idx = text.find(marker)
if idx < 0:
    raise SystemExit("_sync_audio_edit not found")
# Find end of function roughly by inserting call near start
# Read a bit after marker
snippet_start = idx + len(marker)
# Insert right after the def line a call at the end is better — search for first return or end pattern
# Simpler: append to audio_use_var command if any, or add trace after audio_use_var creation
old_use = 'audio_use_var = tk.StringVar(value="replace")\n'
new_use = '''audio_use_var = tk.StringVar(value="replace")
    # 编辑本场时：配声(=replace)禁用成片声音淡变；混音才允许。
'''
if old_use not in text:
    raise SystemExit("audio_use_var not found")
# Don't duplicate comment badly — just leave and hook in _sync_audio_edit body
# Find "_sync_audio_edit" body first line with mixing =
sync_idx = text.find(marker)
# Insert call at beginning of function body
insert_at = sync_idx + len(marker)
hook = "        _sync_audio_fade_gate()\n"
if hook not in text[insert_at:insert_at+200]:
    text = text[:insert_at] + hook + text[insert_at:]

# Update result payload for video_fade
old_payload = '''                "video_fade_in": min(3.0, _fade_seconds(video_fade_in_on, video_fade_in_sec)) if audio_edit else 0.0,
                "video_fade_out": min(3.0, _fade_seconds(video_fade_out_on, video_fade_out_sec)) if audio_edit else 0.0,
            }
'''
new_payload = '''                "video_fade_in": _video_fade_amounts()[0],
                "video_fade_out": _video_fade_amounts()[1],
                "audio_fade": bool(audio_fade_var.get()) and _audio_fade_allowed()
                    and (_video_fade_amounts()[0] > 0.01 or _video_fade_amounts()[1] > 0.01),
            }
'''
if old_payload not in text:
    raise SystemExit("payload not found")
text = text.replace(old_payload, new_payload, 1)

# Add helper _video_fade_amounts near _fade_seconds
old_fade_sec = '''        def _fade_seconds(flag, var) -> float:
            if not flag.get():
                return 0.0
            try:
                return max(0.0, float(var.get()))
            except (tk.TclError, ValueError, TypeError):
                return 0.0
'''
new_fade_sec = '''        def _fade_seconds(flag, var) -> float:
            if not flag.get():
                return 0.0
            try:
                return max(0.0, float(var.get()))
            except (tk.TclError, ValueError, TypeError):
                return 0.0

        def _video_fade_amounts() -> tuple[float, float]:
            fi = min(3.0, _fade_seconds(video_fade_in_on, video_fade_in_sec))
            fo = min(3.0, _fade_seconds(video_fade_out_on, video_fade_out_sec))
            # 不超过选中输出时长的一半，避免淡入淡出重叠过头
            if c is not None:
                out_len = max(0.0, (c.end - c.start) / max(float(c.speed or 1.0), 0.1))
                if out_len > 0.05:
                    half = out_len / 2.0
                    fi = min(fi, half)
                    fo = min(fo, half)
            return fi, fo
'''
if old_fade_sec not in text:
    raise SystemExit("_fade_seconds not found")
text = text.replace(old_fade_sec, new_fade_sec, 1)

dialog.write_text(text, encoding="utf-8")
print("dialog patched OK")

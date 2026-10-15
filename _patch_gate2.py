# -*- coding: utf-8 -*-
from pathlib import Path

path = Path("gui/mp4_pick_preview_dialog.py")
text = path.read_text(encoding="utf-8")

old = '''    def _sync_audio_fade_gate(*_a) -> None:
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
'''

new = '''    _audio_fade_was_allowed = [True]

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
        elif not _audio_fade_was_allowed[0]:
            # 刚从配声切回原声/混音：恢复默认勾选
            audio_fade_var.set(True)
        _audio_fade_was_allowed[0] = allowed
'''

if old not in text:
    raise SystemExit("gate fn not found")
text = text.replace(old, new, 1)

# Cleaner payload: compute once
old_p = '''                "video_fade_in": _video_fade_amounts()[0],
                "video_fade_out": _video_fade_amounts()[1],
                "audio_fade": bool(audio_fade_var.get()) and _audio_fade_allowed()
                    and (_video_fade_amounts()[0] > 0.01 or _video_fade_amounts()[1] > 0.01),
            }
'''
new_p = '''                "video_fade_in": (_vf := _video_fade_amounts())[0],
                "video_fade_out": _vf[1],
                "audio_fade": (
                    bool(audio_fade_var.get())
                    and _audio_fade_allowed()
                    and (_vf[0] > 0.01 or _vf[1] > 0.01)
                ),
            }
'''
# Walrus in dict might be ok in 3.11 - but clearer without
new_p = '''            }
'''
# Actually replace differently - insert before result[0]=
# Find the result[0] = { block and add fi/fo before it

anchor = '''            result[0] = {
                "filename": picked[0],
                "mp4": picked[1],
                "wav": picked[2],
                "action": action,
                "radio": radio_var.get() if radio_holder[0] else "",
                "mix_volume": max(10, min(100, int(mix_level_var.get()))) / 100.0,
                "source": source_var.get() if sources else "",
                "dest": dest_var.get() if dest_options else "",
                "audio": audio_payload,
                "video_fade_in": _video_fade_amounts()[0],
                "video_fade_out": _video_fade_amounts()[1],
                "audio_fade": bool(audio_fade_var.get()) and _audio_fade_allowed()
                    and (_video_fade_amounts()[0] > 0.01 or _video_fade_amounts()[1] > 0.01),
            }
'''
replacement = '''            _vf_in, _vf_out = _video_fade_amounts()
            result[0] = {
                "filename": picked[0],
                "mp4": picked[1],
                "wav": picked[2],
                "action": action,
                "radio": radio_var.get() if radio_holder[0] else "",
                "mix_volume": max(10, min(100, int(mix_level_var.get()))) / 100.0,
                "source": source_var.get() if sources else "",
                "dest": dest_var.get() if dest_options else "",
                "audio": audio_payload,
                "video_fade_in": _vf_in,
                "video_fade_out": _vf_out,
                "audio_fade": (
                    bool(audio_fade_var.get())
                    and _audio_fade_allowed()
                    and (_vf_in > 0.01 or _vf_out > 0.01)
                ),
            }
'''
if anchor not in text:
    # show what's there
    i = text.find('"video_fade_in"')
    print(repr(text[i-200:i+350]))
    raise SystemExit("payload anchor not found")
text = text.replace(anchor, replacement, 1)

path.write_text(text, encoding="utf-8")
print("gate + payload cleaned")

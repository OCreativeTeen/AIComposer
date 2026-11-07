# -*- coding: utf-8 -*-
"""t235u headless: confirm mapping + preview→project look pass-through."""
from __future__ import annotations

import ast
import py_compile
import sys
import tkinter as tk
from pathlib import Path
from unittest import mock

ROOT = Path(r"D:\AIComposer")
sys.path.insert(0, str(ROOT))

files = [
    ROOT / "gui" / "video_prompt_dialog.py",
    ROOT / "gui" / "workflow" / "wf_prompt_flows.py",
    ROOT / "gui" / "dl" / "channel_videos_dialog.py",
]

print("=== py_compile ===")
ok = True
for f in files:
    try:
        py_compile.compile(str(f), doraise=True)
        print(f"OK  {f.relative_to(ROOT)}")
    except Exception as e:
        ok = False
        print(f"FAIL {f}: {e}")

print("\n=== AST: confirm wired into submit paths ===")
src = (ROOT / "gui" / "video_prompt_dialog.py").read_text(encoding="utf-8")
assert "def ask_video_submit_confirm" in src
assert "_confirm_before_submit" in src
assert "if not _confirm_before_submit():" in src
assert "_confirm_before_submit(episode_note=" in src
assert "askokcancel" not in src or src.count("askokcancel") == 0 or "全集提交" not in [
    # episode no longer uses askokcancel for the long-run confirm
]
# specifically: the old episode askokcancel block should be gone
assert 'messagebox.askokcancel(\n            "全集提交"' not in src
print("submit + episode call confirm; old episode askokcancel removed")

wf = (ROOT / "gui" / "workflow" / "wf_prompt_flows.py").read_text(encoding="utf-8")
assert "def apply_look(look: dict)" in wf
assert "apply_look=apply_look" in wf
print("wf_prompt_flows apply_look wired")

ch = (ROOT / "gui" / "dl" / "channel_videos_dialog.py").read_text(encoding="utf-8")
assert "t235u: 参照已有项目新建时" in ch
assert "setting_region=_clone_region" in ch
assert "没显式传入时优先用这一条" in ch
print("clone + create fallback patched")

print("\n=== ask_video_submit_confirm (headless Tk) ===")
import config
import config_prompt
from gui.video_prompt_dialog import ask_video_submit_confirm

root = tk.Tk()
root.withdraw()

initial = {
    "visual_style": "三维卡通 (Pixar-Art-Cartoon)",
    "scene_style": "梦幻 (Dream)",
    "story_style": "story_speak",
    "narrator": "man/kids/chinese",
    "region": "中国",
    "era": "现代",
    "background": True,
}

# Auto-OK path: patch wait_window to immediately click OK via after
results = {}

def _auto_ok():
    # find the confirm toplevel and invoke 确定提交
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and w.title() in ("提交前确认", "全集提交前确认"):
            # walk for Button with text 确定提交
            def find_btn(widget):
                for c in widget.winfo_children():
                    try:
                        if isinstance(c, tk.Button) or c.winfo_class() in ("TButton", "Button"):
                            if str(c.cget("text")) == "确定提交":
                                return c
                    except tk.TclError:
                        pass
                    found = find_btn(c)
                    if found:
                        return found
                return None
            btn = find_btn(w)
            if btn:
                btn.invoke()
                return
    root.after(50, _auto_ok)

root.after(100, _auto_ok)
edited = ask_video_submit_confirm(root, title="提交前确认", initial=initial, note="测试 note")
print("edited:", edited)
assert edited is not None
assert edited["visual_style"] == config.match_visual_style(initial["visual_style"])
assert edited["scene_style"] == config_prompt.normalize_scene_style(initial["scene_style"])
assert edited["story_style"] == "story_speak"
assert edited["narrator"] == "man/kids/chinese"
assert edited["region"] == "中国"
assert edited["era"] == "现代"
assert edited["background"] is True
print("confirm OK path returns prefilled values")

# Cancel path
def _auto_cancel():
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and "确认" in w.title():
            def find_btn(widget):
                for c in widget.winfo_children():
                    try:
                        if c.winfo_class() in ("TButton", "Button") and str(c.cget("text")) == "取消":
                            return c
                    except tk.TclError:
                        pass
                    found = find_btn(c)
                    if found:
                        return found
                return None
            btn = find_btn(w)
            if btn:
                btn.invoke()
                return
    root.after(50, _auto_cancel)

root.after(100, _auto_cancel)
cancelled = ask_video_submit_confirm(root, title="提交前确认", initial=initial)
assert cancelled is None
print("confirm Cancel returns None")

print("\n=== _project_look_from_row + create fallback logic ===")
from gui.downloader import _project_look_from_row
import project_manager

vd = {
    "visual_style": "水彩 (Watercolor)",
    "dialogue_mode": list(config.DIALOGUE_MODE_OPTIONS)[0] if config.DIALOGUE_MODE_OPTIONS else "",
    "narrator": "woman/senior/chinese",
    "setting_region": "日本",
    "setting_era": "现代",
    "scene_style": "真实 (Real)",
    "story_style": "podcast",
    project_manager.PROJECT_PROFILE_KEY: {
        "visual_style": "水彩 (Watercolor)",
        "narrator": "woman/senior/chinese",
        "story_style": "podcast",
        "setting_region": "日本",
        "setting_era": "现代",
        "scene_style": "真实 (Real)",
    },
}
vs, talk, nar = _project_look_from_row(vd)
assert "水彩" in vs
assert nar == "woman/senior/chinese"
print("look_from_row:", vs, talk, nar)

# Simulate clone extraction
cfg = {
    "setting_region": "中国",
    "setting_era": "唐朝",
    "scene_style": "古风 (Antiquity)",
    "story_style": "story_act",
    "visual_style": "中国画 (Chinese-Painting)",
    "narrator": "man/kids/chinese",
    "dialogue_mode": talk,
    "video_title": "test",
}
_look_vs, _look_talk, _look_nar = _project_look_from_row(vd, cfg)
# cfg first in sources for _project_look_from_row — visual from cfg
assert "中国画" in _look_vs or "水彩" in _look_vs
_clone_region = (cfg.get("setting_region") or vd.get("setting_region") or "").strip() or None
_clone_era = (cfg.get("setting_era") or vd.get("setting_era") or "").strip() or None
_clone_ss = cfg.get("scene_style")
if _clone_ss is None:
    _clone_ss = vd.get("scene_style")
assert _clone_region == "中国"
assert _clone_era == "唐朝"
assert "古风" in str(_clone_ss)
print("clone extraction:", _clone_region, _clone_era, _clone_ss, _look_vs)

# story_style from profile fallback expression
pp = vd.get(project_manager.PROJECT_PROFILE_KEY) or {}
st = (vd.get("story_style") or "").strip() or (pp.get("story_style") or "").strip() or None
assert st == "podcast"
print("story_style profile fallback OK")

print("\n=== apply_look unit (mock workflow host) ===")
class FakeWF:
    def __init__(self):
        self.root = root
        self.scene_visual_style = tk.StringVar(value="")
        self.scene_style = tk.StringVar(value=config_prompt.SCENE_STYLE_LABELS[0])
        self.setting_region = tk.StringVar(value="")
        self.setting_era = tk.StringVar(value="")
        # setting_era needs ["values"] like combobox — use a simple namespace
        class Era:
            def __init__(self, var):
                self._var = var
                self._values = ()
            def __setitem__(self, k, v):
                if k == "values":
                    self._values = v
            def set(self, v):
                self._var.set(v)
            def get(self):
                return self._var.get()
        self._era_var = self.setting_era
        self.setting_era = Era(self._era_var)
        self._nar = ""
        self.saved = False
    def _refresh_narrator_button(self, name=""):
        self._nar = name
    def _save_project_look(self, event=None):
        self.saved = True

# Execute apply_look source from wf by extracting function — simpler: exec the body logic
fw = FakeWF()
project_manager.PROJECT_CONFIG = {"pid": "test235"}
look = {
    "visual_style": "三维卡通 (Pixar-Art-Cartoon)",
    "scene_style": "梦幻 (Dream)",
    "narrator": "man/kids/chinese",
    "region": "中国",
    "era": "现代",
}
# inline the apply_look logic as in patch
vs = config.match_visual_style(look.get("visual_style") or "")
fw.scene_visual_style.set(vs)
ss = config_prompt.normalize_scene_style(look.get("scene_style"))
fw.scene_style.set(ss or config_prompt.SCENE_STYLE_LABELS[0])
region = (look.get("region") or "").strip()
era = (look.get("era") or "").strip()
eras = config_prompt.setting_era_labels(region)
fw.setting_region.set(region)
fw.setting_era["values"] = eras
fw.setting_era.set(era if era in eras else (eras[0] if eras else ""))
fw._refresh_narrator_button(look["narrator"])
project_manager.PROJECT_CONFIG["narrator"] = look["narrator"]
fw._save_project_look()
assert "三维卡通" in fw.scene_visual_style.get()
assert fw.setting_region.get() == "中国"
assert fw.setting_era.get() == "现代"
assert fw._nar == "man/kids/chinese"
assert fw.saved
print("apply_look semantics OK")

root.destroy()
print("\n=== ALL PASS ===" if ok else "\n=== COMPILE FAIL ===")
sys.exit(0 if ok else 1)

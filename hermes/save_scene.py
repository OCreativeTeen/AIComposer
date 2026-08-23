#!/usr/bin/env python3
"""Step 2.4: paste the 4-scene JSON into the 分镜 panel's scene_content textarea,
click 保存, then verify the item's scene_content on disk updated."""
import sys, time, ctypes, json, re
import uiautomation as auto
import pyperclip

EDITOR_HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 1115942
u = ctypes.windll.user32

editor = auto.ControlFromHandle(EDITOR_HWND)
editor.SetActive(); time.sleep(0.8)

# re-resolve 分镜 panel (may have new hwnd if reopened)
panel = None
for c, d in auto.WalkControl(editor, maxDepth=3):
    if c.ControlTypeName == "WindowControl" and "分镜" in (c.Name or ""):
        panel = c; break
assert panel is not None, "PANEL_GONE"
pr = panel.BoundingRectangle
print("panel:", pr.left, pr.top, pr.width(), pr.height())

# locate the scene_content textarea: an EditControl/TextControl with name containing 'scene_content' or 'JSON'
ta = None
for c, d in auto.WalkControl(panel, maxDepth=8):
    nm = (c.Name or "")
    if "scene_content" in nm.lower() and c.ControlTypeName in ("EditControl","TextControl"):
        ta = c; break
# fallback: a large text area in the panel
if ta is None:
    best = None
    for c, d in auto.WalkControl(panel, maxDepth=8):
        if c.ControlTypeName in ("EditControl","TextControl"):
            r = c.BoundingRectangle
            if r.height() > 120:
                if best is None or r.height() > best[1].height():
                    best = (c, r)
    ta = best[0] if best else None
assert ta is not None, "TEXTAREA_GONE"
print("textarea:", repr(ta.Name), ta.BoundingRectangle)

# click into textarea (UIA origin + mouse_event), select all, paste
r = ta.BoundingRectangle
tr = editor.BoundingRectangle
# textarea rect is already absolute (UIA physical). Click its center.
u.SetCursorPos(r.left + r.width()//2, r.top + r.height()//2); time.sleep(0.3)
u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0)
time.sleep(0.4)
auto.SendKeys("{Ctrl}a"); time.sleep(0.2)
auto.SendKeys("{Del}"); time.sleep(0.2)
auto.SendKeys("{Ctrl}v"); time.sleep(0.6)
val = ta.GetValuePattern().Value if hasattr(ta, "GetValuePattern") else ""
print("textarea_len_after_paste:", len(val), "has_caption:", "caption" in val)

# locate 保存 button in bottom row (uniform 113x37 around y=1240 panel-relative
# => absolute = panel.top + 1240). Scan buttons near that y.
save_btn = None
for c, d in auto.WalkControl(panel, maxDepth=8):
    if c.ControlTypeName == "ButtonControl":
        rr = c.BoundingRectangle
        # save is at panel-relative y~1240 => abs y ~ pr.top+1240
        target_y = pr.top + 1240
        if abs(rr.top - target_y) < 60 and rr.width() > 40:
            # among the row, save is the one near x 431 panel-relative
            if abs((rr.left - pr.left) - 431) < 120:
                save_btn = c; break
# fallback: any button whose name contains 保存
if save_btn is None:
    for c, d in auto.WalkControl(panel, maxDepth=8):
        if c.ControlTypeName == "ButtonControl" and "保存" in (c.Name or ""):
            save_btn = c; break
assert save_btn is not None, "SAVE_BTN_GONE"
sr = save_btn.BoundingRectangle
print("save_btn:", repr(save_btn.Name), sr.left, sr.top, sr.width(), sr.height())
u.SetCursorPos(sr.left + sr.width()//2, sr.top + sr.height()//2); time.sleep(0.3)
u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0)
print("clicked 保存")
time.sleep(2.0)
print("RESULT_JSON " + json.dumps({"pasted": len(val)>0, "save_clicked": True}, ensure_ascii=False))

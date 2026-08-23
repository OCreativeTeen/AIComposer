#!/usr/bin/env python3
"""Click the 场景 button safely (UIA origin + mouse_event), then verify:
   (a) clipboard now contains the scene prompt (has N scene marker)
   (b) the 分镜 / Scene child panel opened under the editor root.
Prints JSON: {clicked, clipboard_len, has_scene_marker, panel_hwnd, panel_rect}"""
import sys, time, ctypes, json
import uiautomation as auto
import pyperclip

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 1115942
REL_X, REL_Y = 714, 535  # 场景 button, live edge-detected
u = ctypes.windll.user32

editor = auto.ControlFromHandle(HWND)
editor.SetActive(); time.sleep(1.0)
r = editor.BoundingRectangle
L, T = r.left, r.top
print("editor origin:", L, T, "size:", r.width(), r.height())

u.SetCursorPos(L + REL_X, T + REL_Y); time.sleep(0.4)
u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.08); u.mouse_event(0x0004, 0, 0, 0, 0)
print("clicked 场景 at", L + REL_X, T + REL_Y)
time.sleep(2.0)

clip = pyperclip.paste() or ""
marker = None
import re
m = re.findall(r'has \d+ scene', clip)
if m:
    marker = m[0]
print("clipboard_len:", len(clip))
print("has_scene_marker:", marker)

# detect 分镜 panel: child WindowControl of root with name containing 分镜
root = editor
panel_hwnd = None; panel_rect = None
for c, depth in auto.WalkControl(root, maxDepth=3):
    if c.ControlTypeName == "WindowControl" and "分镜" in (c.Name or ""):
        pr = c.BoundingRectangle
        panel_hwnd = c.NativeWindowHandle
        panel_rect = (pr.left, pr.top, pr.width(), pr.height())
        print("PANEL found depth", depth, "hwnd", panel_hwnd, panel_rect)
        break
if panel_hwnd is None:
    print("PANEL_NOT_FOUND_YET")

out = {
    "clicked": True,
    "clipboard_len": len(clip),
    "has_scene_marker": marker,
    "panel_hwnd": panel_hwnd,
    "panel_rect": panel_rect,
}
print("RESULT_JSON " + json.dumps(out, ensure_ascii=False))

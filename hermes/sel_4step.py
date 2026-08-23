#!/usr/bin/env python3
"""In the 分镜 panel, select '4 Step Story' in the 选LM提示 combobox by
keyboard nav, then verify the clipboard prompt marker flips to 'has 4 scene'.

Combobox physical point = panel_origin + (239, 167).
panel hwnd passed as argv[1], panel origin rect argv optional.
"""
import sys, time, ctypes, re, json
import uiautomation as auto
import pyperclip

PANEL_HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 657646
REL_X, REL_Y = 239, 167  # combobox center, panel-relative
u = ctypes.windll.user32

panel = auto.ControlFromHandle(PANEL_HWND)
if not panel.Exists(3, 1):
    print("PANEL_GONE"); sys.exit(0)
pr = panel.BoundingRectangle
L, T = pr.left, pr.top
print("panel origin:", L, T, "size:", pr.width(), pr.height())
click_x, click_y = L + REL_X, T + REL_Y
print("combobox click at:", click_x, click_y)

# ensure editor/panel active
root = auto.WindowControl(searchDepth=1, Name="AIComposer — YT 工具")
root.SetActive(); time.sleep(0.5)
panel.SetActive(); time.sleep(0.5)

# click combobox ONCE
u.SetCursorPos(click_x, click_y); time.sleep(0.4)
u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.08); u.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(0.8)

# keyboard nav: Down x5 then Enter
for _ in range(5):
    auto.SendKey(auto.Keys.VK_DOWN); time.sleep(0.25)
auto.SendKey(auto.Keys.VK_RETURN); time.sleep(1.0)

clip = pyperclip.paste() or ""
m = re.findall(r'has \d+ scene', clip)
marker = m[0] if m else None
print("clipboard_len:", len(clip))
print("marker:", marker)
print("RESULT_JSON " + json.dumps({"clicked_combo": True, "marker": marker}, ensure_ascii=False))

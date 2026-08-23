#!/usr/bin/env python3
"""Step 2.2: New chat -> paste scene prompt -> Enter. Verifies paste by
reading back the input control's value (must be >3000 chars)."""
import sys, time, ctypes, json, re
import uiautomation as auto
import pyperclip

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 2032376
u = ctypes.windll.user32

w = auto.ControlFromHandle(HWND)
w.SetActive(); time.sleep(0.8)

def find_input():
    for c, d in auto.WalkControl(w, maxDepth=42):
        if c.ControlTypeName == "EditControl" and "prompt for Gemini" in (c.Name or ""):
            return c
    return None

def find_newchat():
    for c, d in auto.WalkControl(w, maxDepth=42):
        nm = (c.Name or "").strip().lower()
        if (c.ControlTypeName in ("ButtonControl","HyperlinkControl")) and nm == "new chat":
            return c
    return None

# 1) New chat
nc = find_newchat()
if nc:
    r = nc.BoundingRectangle
    u.SetCursorPos(r.left + r.width()//2, r.top + r.height()//2); time.sleep(0.3)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0)
    print("clicked New chat at", r.left + r.width()//2, r.top + r.height()//2)
    time.sleep(2.0)
else:
    print("NEW_CHAT_NOT_FOUND")

# 2) focus input, sentinel check
ta = find_input()
assert ta is not None, "INPUT_GONE"
ta.SetFocus(); time.sleep(0.6)
auto.SendKeys("{Ctrl}a"); time.sleep(0.2)
auto.SendKeys("ZZSENTINELZZ"); time.sleep(0.3)
val = ta.GetValuePattern().Value
print("sentinel_readback:", repr(val), "focus_ok:", auto.GetFocusedControl().Name)
assert val == "ZZSENTINELZZ", "SENTINEL_FAILED"

# 3) clear + paste real prompt
auto.SendKeys("{Ctrl}a"); time.sleep(0.2)
auto.SendKeys("{Del}"); time.sleep(0.2)
auto.SendKeys("{Ctrl}v"); time.sleep(0.8)
val = ta.GetValuePattern().Value
print("pasted_len:", len(val))
assert len(val) > 3000, "PASTE_TOO_SHORT"

# 4) send
auto.SendKeys("{Enter}")
print("SENT")
print("RESULT_JSON " + json.dumps({"newchat_clicked": nc is not None, "pasted_len": len(val)}, ensure_ascii=False))

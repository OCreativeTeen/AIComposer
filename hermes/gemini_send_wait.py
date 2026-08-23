#!/usr/bin/env python3
"""Re-send the 4-step scene prompt to a FRESH Gemini chat, then wait PASSIVELY
(no Esc / no clicks / no focus theft) while Gemini generates. Periodically
screenshots so the orchestrator can check progress. Does NOT touch the page
during generation (Esc/click would abort streaming)."""
import sys, time, ctypes, json
import uiautomation as auto
import pyperclip
from PIL import ImageGrab

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 2032376
WAIT = int(sys.argv[2]) if len(sys.argv) > 2 else 120
SHOT_EVERY = int(sys.argv[3]) if len(sys.argv) > 3 else 30
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

# fresh chat
nc = find_newchat()
if nc:
    r = nc.BoundingRectangle
    u.SetCursorPos(r.left + r.width()//2, r.top + r.height()//2); time.sleep(0.3)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0)
    time.sleep(2.0)

ta = find_input()
assert ta is not None
ta.SetFocus(); time.sleep(0.5)
auto.SendKeys("{Ctrl}a"); time.sleep(0.15); auto.SendKeys("{Del}"); time.sleep(0.15)
auto.SendKeys("{Ctrl}v"); time.sleep(0.6)
val = ta.GetValuePattern().Value
print("pasted_len:", len(val))
assert len(val) > 3000
auto.SendKeys("{Enter}")
print("SENT at t=0, waiting passively", WAIT, "s ...")

# PASSIVE wait: no UI interaction
t = 0
while t < WAIT:
    time.sleep(SHOT_EVERY)
    t += SHOT_EVERY
    rb = w.BoundingRectangle
    ImageGrab.grab((rb.left, rb.top, rb.right, rb.bottom)).save("hermes/gemini_gen.png")
    print(f"  t={t}s screenshot saved")
print("WAIT_DONE")
print("RESULT_JSON " + json.dumps({"sent": True, "pasted_len": len(val)}, ensure_ascii=False))

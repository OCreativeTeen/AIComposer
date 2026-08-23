#!/usr/bin/env python3
"""Generate ONE NotebookLM infographic cover in the Story Builder notebook (H=199052).
Opens Customize Infographic chevron, pastes prompt, sets 中文（繁體）/Portrait/Concise,
clicks Generate, and polls for a 'Generating Infographic...' row to confirm it started.
Checks the daily-quota banner FIRST and aborts if present.
Usage: nb_gen.py <prompt_file> [H]
"""
import sys, time, ctypes, json
sys.path.insert(0, 'hermes')
from wf_lib import bring_front
import uiautomation as auto, pyperclip

H = int(sys.argv[2]) if len(sys.argv) > 2 else 199052
prompt_file = sys.argv[1] if len(sys.argv) > 1 else "hermes/cover_prompt.txt"
u = ctypes.windll.user32

def activate(hwnd):
    bring_front(hwnd)
    time.sleep(0.5)

def find(hwnd, pred, depth=48):
    for t, d in auto.WalkControl(auto.ControlFromHandle(hwnd), maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            return t, n, r
    return None, None, None

def mclick(r):
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    auto.ControlFromHandle(H).SetActive(); time.sleep(0.3)
    u.SetCursorPos(cx, cy); time.sleep(0.3)
    u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.09)
    u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.5)

def quota_banner():
    w = auto.ControlFromHandle(H)
    for t, d in auto.WalkControl(w, maxDepth=30):
        n = (t.Name or '').strip().lower()
        if 'daily' in n and 'limit' in n:
            return True
    return False

def open_dialog():
    activate(H)
    time.sleep(1.0)
    t, nm, r = find(H, lambda t, n, rr: t.ControlTypeName == 'ButtonControl' and n == 'Infographic')
    if not t:
        print("NO Infographic button"); return False
    # click the Infographic tile BODY to open Customize Infographic dialog
    cx, cy = r.left + r.width() // 2, r.top + r.height() // 2
    u.SetCursorPos(cx, cy); time.sleep(1.5)
    u.mouse_event(0x0002, 0, 0, 0, 0); u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(4)
    ta, _, _ = find(H, lambda t, n, rr: t.ControlTypeName == 'EditControl' and 'Describe the infographic' in n)
    return ta is not None

def set_radio(name):
    t, nm, r = find(H, lambda t, n, rr: t.ControlTypeName == 'RadioButtonControl' and n == name)
    if not t:
        print("  radio not found:", name); return None
    try:
        if t.GetSelectionItemPattern().IsSelected:
            return True
    except Exception:
        pass
    mclick(r); time.sleep(0.8)
    t, _, _ = find(H, lambda x, n, rr: x.ControlTypeName == 'RadioButtonControl' and n == name)
    return t.GetSelectionItemPattern().IsSelected

def set_language(want='中文（繁體）'):
    t, nm, r = find(H, lambda t, n, rr: t.ControlTypeName == 'ComboBoxControl' and n == 'Choose language')
    if not t:
        print("  no language combo"); return False
    cur = ''
    try: cur = t.GetValuePattern().Value
    except Exception: pass
    print("  language:", repr(cur))
    if want in (cur or ''):
        return True
    mclick(r); time.sleep(1.5)
    it, n2, r2 = find(H, lambda x, n, rr: x.ControlTypeName == 'ListItemControl' and want in n)
    if it:
        mclick(r2); time.sleep(1.0); return True
    auto.SendKey(auto.Keys.VK_ESCAPE); return False

def submit(prompt):
    ta, _, _ = find(H, lambda t, n, rr: t.ControlTypeName == 'EditControl' and 'Describe the infographic' in n)
    if not ta:
        print("  no Describe field"); return False
    pyperclip.copy(prompt); time.sleep(0.4)
    ta.SetFocus(); time.sleep(0.9)
    auto.SendKeys('{Ctrl}a'); time.sleep(0.2); auto.SendKeys('{Ctrl}v'); time.sleep(2.0)
    v = ta.GetValuePattern().Value
    print("  prompt chars in field:", len(v))
    if len(v) < 500:
        return False
    g, _, gr = find(H, lambda t, n, rr: t.ControlTypeName == 'ButtonControl' and n == 'Generate')
    if not g:
        print("  no Generate button"); return False
    mclick(gr); time.sleep(3)
    return True

def generating_row():
    for t, d in auto.WalkControl(auto.ControlFromHandle(H), maxDepth=42):
        n = (t.Name or '').strip()
        if 'Generating Infographic' in n:
            return n
    return None

if __name__ == '__main__':
    prompt = open(prompt_file, encoding='utf-8').read()
    print("prompt len:", len(prompt))
    if quota_banner():
        print("QUOTA_BANNER_PRESENT -> abort"); sys.exit(2)
    if not open_dialog():
        print("OPEN_DIALOG_FAILED"); sys.exit(1)
    set_language('中文（繁體）')
    set_radio('Portrait')
    set_radio('Concise')
    if not submit(prompt):
        print("SUBMIT_FAILED"); sys.exit(1)
    # poll for generating row (up to ~60s)
    for _ in range(12):
        row = generating_row()
        if row:
            print("GENERATING_STARTED:", row); break
        time.sleep(5)
    else:
        print("NO_GENERATING_ROW")
    print("DONE_ONE")

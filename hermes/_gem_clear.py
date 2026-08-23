import sys, time, re, ctypes
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W
import uiautomation as auto, win32gui, win32con

USER32 = ctypes.windll.user32
gem_hw = 0x60802

def find_control(hwnd, pred, depth=42):
    for t, d in auto.WalkControl(auto.ControlFromHandle(hwnd), maxDepth=depth):
        n = (t.Name or '').strip(); r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            return t, n, r
    return None, None, None

if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.8)

ta, tan, tar = find_control(gem_hw, lambda t,n,r: 'prompt for Gemini' in n)
assert ta, "input not found"
ta.SetFocus(); time.sleep(0.8)

# detect current content
val0 = ta.GetValuePattern().Value
print("current input value:", repr(val0[:80]))

# try clear methods
for method in ["backspace", "delete", "esc_then_backspace"]:
    if method == "esc_then_backspace":
        auto.SendKeys('{Esc}'); time.sleep(0.3)
    auto.SendKeys('{Ctrl}a'); time.sleep(0.2)
    if method in ("backspace","esc_then_backspace"):
        auto.SendKeys('{Backspace}')
    else:
        auto.SendKeys('{Delete}')
    time.sleep(0.4)
    v = ta.GetValuePattern().Value
    print(f"  after {method}: len={len(v)} val={v[:50]!r}")
    if v == '':
        print("  CLEARED with", method); break

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

if win32gui.IsIconic(gem_hw): gem_hw = gem_hw
if win32gui.IsIconic(0x60802): win32gui.ShowWindow(0x60802, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(0x60802); time.sleep(0.8)

ta, tan, tar = find_control(0x60802, lambda t,n,r: 'prompt for Gemini' in n)
assert ta, "input not found"
ta.SetFocus(); time.sleep(0.8)

# clear any content via Ctrl+A + BACKSPACE token
auto.SendKeys('{Ctrl}a'); time.sleep(0.2)
auto.SendKeys('{BACKSPACE}'); time.sleep(0.4)
v = ta.GetValuePattern().Value
print("after clear, len:", len(v), repr(v[:40]))

# paste the 4-step prompt (in clipboard from earlier)
auto.SendKeys('{Ctrl}v'); time.sleep(1.2)
v = ta.GetValuePattern().Value
print("after paste, len:", len(v), "head:", v[:50].replace(chr(10),' '))
assert len(v) > 3000, "paste too short -> paste failed"

auto.SendKeys('{Enter}')
print("SUBMITTED. Waiting for Gemini generation (60s)...")
time.sleep(60)
print("waited 60s. input now len:", len(ta.GetValuePattern().Value))

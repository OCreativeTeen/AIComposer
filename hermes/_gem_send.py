import sys, time, re, ctypes, pyperclip
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

# 1) focus window
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(1.0)

# 2) click "New chat" (sidebar button, larger rect)
nc, ncn, ncr = find_control(gem_hw, lambda t,n,r: 'New chat' in n and t.ControlTypeName=='HyperlinkControl' and r.width()>300)
assert nc, "New chat not found"
print("clicking New chat at", (ncr.left, ncr.top, ncr.right, ncr.bottom))
cx = (ncr.left + ncr.right)//2; cy = (ncr.top + ncr.bottom)//2
ctl = auto.ControlFromHandle(gem_hw); ctl.SetActive(); time.sleep(0.5)
USER32.SetCursorPos(cx, cy); time.sleep(0.3)
USER32.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); USER32.mouse_event(0x0004,0,0,0,0)
time.sleep(2.5)

# 3) re-locate input
ta, tan, tar = find_control(gem_hw, lambda t,n,r: 'prompt for Gemini' in n)
assert ta, "input not found after New chat"
print("input found:", tan, (tar.left,tar.top,tar.right,tar.bottom))

# 4) focus + sentinel verify
ta.SetFocus(); time.sleep(0.8)
auto.SendKeys('ZZSENTINELZZ')
time.sleep(0.5)
try:
    val = ta.GetValuePattern().Value
except Exception as e:
    val = f"<err {e}>"
print("after sentinel, value:", repr(val))
assert val == 'ZZSENTINELZZ', f"sentinel mismatch: {val!r}"

# clear sentinel
auto.SendKeys('{Ctrl}a'); time.sleep(0.2)
auto.SendKeys('{Delete}'); time.sleep(0.3)
assert ta.GetValuePattern().Value == '', "clear failed"
print("cleared sentinel OK")

# 5) paste the 4-step prompt (already in clipboard from Step 2a/2b)
time.sleep(0.3)
auto.SendKeys('{Ctrl}v')
time.sleep(1.0)
v = ta.GetValuePattern().Value
print("after paste, length:", len(v), "head:", v[:60].replace(chr(10),' '))
assert len(v) > 3000, "paste too short"

# 6) submit
auto.SendKeys('{Enter}')
print("submitted prompt to Gemini. Waiting for generation...")
time.sleep(5)
print("DONE submit; clipboard still has prompt (len %d)" % len(W.clip_text()))

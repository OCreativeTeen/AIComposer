import sys, time, re, ctypes
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W
import uiautomation as auto, win32gui, win32con

USER32 = ctypes.windll.user32
VK_CONTROL=0x11; VK_A=0x41; VK_BACK=0x08; VK_RETURN=0x0D; VK_C=0x43; VK_V=0x56

def key_down(code): USER32.keybd_event(code,0,0,0)
def key_up(code): USER32.keybd_event(code,0,0x0002,0)
def tap(code): key_down(code); time.sleep(0.05); key_up(code); time.sleep(0.05)
def ctrl_key(code):
    key_down(VK_CONTROL); time.sleep(0.05); tap(code); key_up(VK_CONTROL); time.sleep(0.08)

gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.8)

def find_control(pred, depth=42):
    for t, d in auto.WalkControl(auto.ControlFromHandle(gem_hw), maxDepth=depth):
        n = (t.Name or '').strip(); r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            return t, n, r
    return None, None, None

ta, tan, tar = find_control(lambda t,n,r: 'prompt for Gemini' in n)
assert ta, "input not found"
ta.SetFocus(); time.sleep(0.8)
# clear
ctrl_key(VK_A); time.sleep(0.2); tap(VK_BACK); time.sleep(0.4)
v = ta.GetValuePattern().Value
print("after clear len:", len(v), repr(v[:40]))

# paste clipboard (4-step prompt)
ctrl_key(VK_V); time.sleep(1.2)
v = ta.GetValuePattern().Value
print("after paste len:", len(v), "head:", v[:50].replace(chr(10),' '))
assert len(v) > 3000, "paste failed"

tap(VK_RETURN)
print("SUBMITTED. waiting 60s...")
time.sleep(60)
print("done wait. input len now:", len(ta.GetValuePattern().Value))

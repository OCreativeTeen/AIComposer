import sys, time, re, ctypes, json
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W
import uiautomation as auto, win32gui, win32con

USER32=ctypes.windll.user32
VK_CONTROL=0x11; VK_A=0x41; VK_C=0x43; VK_ESCAPE=0x1B
def key_down(c): USER32.keybd_event(c,0,0,0)
def key_up(c): USER32.keybd_event(c,0,0x0002,0)
def tap(c): key_down(c); time.sleep(0.05); key_up(c); time.sleep(0.05)
def ctrl(c):
    key_down(VK_CONTROL); time.sleep(0.05); tap(c); key_up(VK_CONTROL); time.sleep(0.15)

gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.8)

# Drop focus to page body: click top margin of the window (y small)
ctl=auto.ControlFromHandle(gem_hw); ctl.SetActive(); 
USER32.SetCursorPos(400, 20); time.sleep(0.2)
USER32.mouse_event(0x0002,0,0,0,0); time.sleep(0.05); USER32.mouse_event(0x0004,0,0,0,0)
time.sleep(0.5)
# Esc to ensure no input focused
tap(VK_ESCAPE); time.sleep(0.3)

# Ctrl+A then Ctrl+C on the page
ctrl(VK_A); time.sleep(0.5)
ctrl(VK_C); time.sleep(0.8)

clip = W.clip_text()
print("clip len:", len(clip))
print("caption count:", len(re.findall(r'"caption"', clip)))
print("scene markers:", re.findall(r'"caption"\s*:\s*"([^"]{0,20})', clip)[:6])
print("head 200:", clip[:200].replace(chr(10),' '))

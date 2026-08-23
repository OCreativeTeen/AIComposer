import sys, time, re, ctypes
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W
import uiautomation as auto, win32gui, win32con

USER32 = ctypes.windll.user32

# locate 分镜 panel
panel = auto.WindowControl(searchDepth=1, Name="分镜 / Scene")
phw = panel.NativeWindowHandle
print("panel hwnd", hex(phw))
r = panel.BoundingRectangle
print("panel rect", (r.left, r.top, r.right, r.bottom))
if win32gui.IsIconic(phw): win32gui.ShowWindow(phw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(phw); time.sleep(0.6)

# combobox center: absolute (1268, 271) per ground-truth geometry
cx, cy = 1268, 271
print(f"clicking 选LM提示 combobox at abs ({cx},{cy})...")
ctl = auto.ControlFromHandle(phw); ctl.SetActive(); time.sleep(1.0)
USER32.SetCursorPos(cx, cy); time.sleep(0.35)
USER32.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); USER32.mouse_event(0x0004,0,0,0,0)
time.sleep(1.2)

# navigate: Down x5 then Enter
for i in range(5):
    USER32.keybd_event(0x28,0,0,0)  # VK_DOWN
    time.sleep(0.12)
    USER32.keybd_event(0x28,0,0x0002,0)
    time.sleep(0.12)
time.sleep(0.3)
USER32.keybd_event(0x0D,0,0,0)  # VK_RETURN
USER32.keybd_event(0x0D,0,0x0002,0)
time.sleep(1.5)

clip = W.clip_text()
print("clip len:", len(clip))
m = re.findall(r'has \d+ scene', clip)
print("scene marker:", m)
print("first 120:", clip[:120].replace("\n"," "))

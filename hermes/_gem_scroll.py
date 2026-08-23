import uiautomation as auto, win32gui, win32con, time, ctypes
from PIL import ImageGrab
USER32=ctypes.windll.user32
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
W=right-left
# scroll up within the chat: move mouse to center of right pane, wheel up several notches
import ctypes
# mouse wheel: negative = up
USER32.SetCursorPos(left+int(W*0.75), top+int((bottom-top)*0.5))
time.sleep(0.3)
for _ in range(8):
    USER32.mouse_event(0x0800, 0, 0, ctypes.c_int(-480), 0)  # WHEEL_DELTA negative=up
    time.sleep(0.15)
time.sleep(0.5)
img=ImageGrab.grab(bbox=(left+W//2, top, right, bottom))
img.save(r"D:\AIComposer\hermes\gem_right.png")
print("saved after scroll-up")

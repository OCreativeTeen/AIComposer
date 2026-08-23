import sys, time, cv2, numpy as np
import uiautomation as auto
from PIL import ImageGrab
HWND = int(sys.argv[1]) if len(sys.argv)>1 else 460876
# find window by enumeration of detail title containing 摘要
import win32gui, win32con
target=None
def cb(h,res):
    if win32gui.IsWindowVisible(h):
        t=win32gui.GetWindowText(h)
        if '摘要' in t or '拖入' in t:
            res.append(h)
res=[]
win32gui.EnumWindows(cb,res)
if HWND==460876 and res:
    HWND=res[-1]
print("USING_HWND",HWND)
w = auto.ControlFromHandle(HWND)
try:
    r = w.BoundingRectangle
    left,top,right,bottom = r.left,r.top,r.right,r.bottom
except Exception as e:
    print("rect fail", e); sys.exit(1)
print("RECT", left,top,right,bottom, "W", right-left, "H", bottom-top)
# bring to foreground + topmost then grab
win32gui.ShowWindow(HWND, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(HWND)
time.sleep(0.6)
ImageGrab.grab(bbox=(left,top,right,bottom)).save("hermes/probe_full.png")
print("saved hermes/probe_full.png")

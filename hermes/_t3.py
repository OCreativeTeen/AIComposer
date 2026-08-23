import uiautomation as auto
import ctypes, win32gui
u = ctypes.windll.user32
found=[]
def cb(h,_):
    t=win32gui.GetWindowText(h)
    if "分镜" in t: found.append(h)
    return 1
win32gui.EnumWindows(cb,None)
print("RESULT", hex(found[0]) if found else None)

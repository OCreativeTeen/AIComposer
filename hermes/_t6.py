import uiautomation as auto
import ctypes, time, subprocess, json, re, win32gui
u = ctypes.windll.user32
found=[]
def cb(h,_):
    t=win32gui.GetWindowText(h)
    if "分镜" in t: found.append(h)
    return 1
def go():
    win32gui.EnumWindows(cb,None)
    return found[0] if found else None
print("RESULT", hex(go()) if go() else None)

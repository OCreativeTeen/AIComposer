import uiautomation as auto
import ctypes, time, subprocess, json, re, win32gui
u = ctypes.windll.user32
def find_by_title(sub, exclude=""):
    found = []
    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if sub in t and exclude not in t:
            found.append(h)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None
hw = find_by_title("分镜")
print("RESULT", hex(hw) if hw else None)

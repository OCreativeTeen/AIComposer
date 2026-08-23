import uiautomation as auto
import ctypes, time, subprocess, json, re, win32gui
u = ctypes.windll.user32
_found = []
def _enum_cb(h, _):
    t = win32gui.GetWindowText(h)
    if _enum_cb._sub in t and _enum_cb._exclude not in t:
        _found.append(h)
    return 1
def find_by_title(sub, exclude=""):
    _found.clear()
    _enum_cb._sub = sub
    _enum_cb._exclude = exclude
    win32gui.EnumWindows(_enum_cb, None)
    return _found[0] if _found else None
print("RESULT", hex(find_by_title("分镜")) if find_by_title("分镜") else None)

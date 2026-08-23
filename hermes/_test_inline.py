import uiautomation as auto
import ctypes, time, subprocess, json, re, win32gui
u = ctypes.windll.user32
_TITLE_HITS = []
_TITLE_SUB = ""
def _enum_titles_cb(h, _):
    t = win32gui.GetWindowText(h)
    if _TITLE_SUB in t:
        _TITLE_HITS.append(h)
    return 1
def find_by_title(sub):
    global _TITLE_HITS, _TITLE_SUB
    _TITLE_HITS = []
    _TITLE_SUB = sub
    win32gui.EnumWindows(_enum_titles_cb, None)
    return _TITLE_HITS[0] if _TITLE_HITS else None
print("INLINE call:", hex(find_by_title("分镜")) if find_by_title("分镜") else None)

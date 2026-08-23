"""Screenshot the 分镜 panel to a file for visual inspection of the
scene_content textarea location. Module-level enum callback (proven reliable).
"""
import uiautomation as auto
import ctypes, win32gui
from PIL import ImageGrab

u = ctypes.windll.user32
OUT = "hermes/panel_shot.png"
_TITLE_HITS = []
_TITLE_SUB = ""
def _enum_cb(h, _):
    t = win32gui.GetWindowText(h)
    if _TITLE_SUB in t:
        _TITLE_HITS.append(h)
    return 1
def find_by_title(sub):
    global _TITLE_HITS, _TITLE_SUB
    _TITLE_HITS = []; _TITLE_SUB = sub
    win32gui.EnumWindows(_enum_cb, None)
    return _TITLE_HITS[0] if _TITLE_HITS else None

def main():
    panel = find_by_title("分镜")
    rect = win32gui.GetWindowRect(panel)
    img = ImageGrab.grab(bbox=rect)
    img.save(OUT)
    print("saved", OUT, img.size)

if __name__=="__main__":
    main()

"""Deep-probe the 分镜 panel: enumerate ALL descendants (recursive) to find the
real edit/textarea widget for scene_content. Tk text widgets are TkChild too but
may sit one level deeper than the big container rect.
"""
import uiautomation as auto
import ctypes, win32gui

u = ctypes.windll.user32
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
    print("panel:", hex(panel) if panel else None)
    rect = win32gui.GetWindowRect(panel)
    print("rect:", list(rect))
    # recursively enumerate children
    def enum(h, _):
        kids.append((h, win32gui.GetClassName(h), win32gui.GetWindowRect(h)))
    global kids
    kids = []
    win32gui.EnumChildWindows(panel, enum, None)
    # find the deepest large widget (the text area) - largest TkChild
    big = []
    for h, cls, r in kids:
        w=r[2]-r[0]; ht=r[3]-r[1]
        if cls=='TkChild' and ht>200 and w>300:
            big.append((r[0]+w//2, r[1]+ht//2, w, ht, r))
    big.sort(key=lambda b:-b[3])
    print("=== large TkChild widgets (cx,cy,w,h) ===")
    for cx,cy,w,ht,r in big[:8]:
        print(f"  cx={cx} cy={cy} w={w} h={ht} rect={list(r)}")

if __name__=="__main__":
    main()

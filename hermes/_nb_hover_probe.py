"""Fresh full NotebookLM screenshot, then probe UIA for the per-row export
button by hovering over each row's right edge first. Reports revealed controls.
"""
import uiautomation as auto
import ctypes, win32gui, time
from PIL import ImageGrab

u = ctypes.windll.user32
NB_HWND = 0x3098c

def walk(root, pred, depth=46):
    for t, d in auto.WalkControl(root, maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            yield t, n, r

def main():
    root = auto.ControlFromHandle(NB_HWND)
    root.SetActive(); time.sleep(1.5)
    rect = win32gui.GetWindowRect(NB_HWND)
    # hover over the studio area right side at a few y positions to reveal rows' export btns
    for y in (540, 720, 900):
        u.SetCursorPos(2215, y); time.sleep(1.5)
    img = ImageGrab.grab(bbox=rect)
    img.save("hermes/nb_full2.png")
    print("saved nb_full2.png", img.size)
    # now probe for export-ish controls
    hits=[]
    for t,n,r in walk(root, lambda t,n,r: 'Export' in n or 'JPG' in n or 'Download' in n or '信息图' in n):
        hits.append((n,(r.left,r.top,r.right,r.bottom)))
    print("export-ish controls after hover:", len(hits))
    for h in hits[:15]:
        print("  ", h)

if __name__=="__main__":
    main()

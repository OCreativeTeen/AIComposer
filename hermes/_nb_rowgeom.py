"""Find the 3 infographic row title TextControls via UIA and report their rects.
The per-row export button sits to the RIGHT of each row's text. This gives
exact geometry instead of guessing pixels.
"""
import uiautomation as auto
import ctypes, win32gui, time

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
    titles = ['碎裂後的自我和解旅程','情緒崩潰的四個階段','剩餘的自我修復旅程']
    for title in titles:
        found=None
        for t,n,r in walk(root, lambda t,n,r: title in n):
            found=(n,(r.left,r.top,r.right,r.bottom)); break
        if found:
            n,rect=found
            # export button likely ~ right edge of row + some offset
            print(f"{title}: rect={rect}  right_edge_x={rect[2]}  row_cy={(rect[1]+rect[3])//2}")
        else:
            print(f"{title}: NOT FOUND")

if __name__=="__main__":
    main()

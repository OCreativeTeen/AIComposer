"""Step 3 poll: confirm a NotebookLM generation started (look for
'Generating Infographic' row) and check for a daily-quota banner.
Report state without mutating.
"""
import uiautomation as auto
import ctypes, win32gui, json, time

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
    generating = [n for t, n, r in walk(root, lambda t, n, r: 'Generating' in n or 'infographic' in n.lower())]
    quota = [n for t, n, r in walk(root, lambda t, n, r: 'daily' in n.lower() and 'limit' in n.lower())]
    # also count Studio source rows
    rows = [n for t, n, r in walk(root, lambda t, n, r: 'source' in n.lower())]
    print("generating markers:", generating[:5])
    print("quota banner:", quota[:3])
    print("source rows:", len(rows))
    print(json.dumps({"generating_now": len(generating) > 0,
                      "quota_hit": len(quota) > 0}, ensure_ascii=False))

if __name__=="__main__":
    main()

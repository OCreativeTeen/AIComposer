"""Step 3 detailed status: count ready vs generating infographics, list their
titles, and detect any error/empty/failed state. No mutation.
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
    ready = [n for t, n, r in walk(root, lambda t, n, r: 'is ready' in n.lower())]
    generating = [n for t, n, r in walk(root, lambda t, n, r: 'generating' in n.lower())]
    failed = [n for t, n, r in walk(root, lambda t, n, r: 'failed' in n.lower() or 'error' in n.lower())]
    # studio rows often show '<title> 1 source · Nm ago'
    rows = [n for t, n, r in walk(root, lambda t, n, r: 'source ·' in n.lower())]
    print("READY (%d):" % len(ready))
    for r in ready: print("   ", r)
    print("GENERATING (%d):" % len(generating))
    for g in generating: print("   ", g)
    print("FAILED/ERR (%d):" % len(failed), failed[:5])
    print("ROWS w/ source · (%d):" % len(rows))
    for x in rows[:8]: print("   ", x)
    print(json.dumps({"ready":len(ready),"generating":len(generating),"failed":len(failed)},
                     ensure_ascii=False))

if __name__=="__main__":
    main()

"""Step 3: (re)open the NotebookLM Customize Infographic dialog via the
infographic tile's far-right chevron (hover-revealed). Returns whether the
dialog is now open. Module-level enum. Does NOT generate.
"""
import uiautomation as auto
import ctypes, time, win32gui, json

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
    # is dialog already open?
    dlg = None
    for t, n, r in walk(root, lambda t, n, r: t.ControlTypeName=='WindowControl' and 'Customize Infographic' in n):
        dlg = (n, r); break
    if dlg:
        print("dialog already open:", dlg[0])
        print(json.dumps({"open": True})); return
    # need to open: find the Infographic tile and its chevron. Hover then click.
    # find a button/control named like 'Infographic' tile or the chevron '>' 
    tile = None
    for t, n, r in walk(root, lambda t, n, r: 'Infographic' in n and t.ControlTypeName in ('ButtonControl','HyperlinkControl')):
        tile = (n, r); break
    if not tile:
        print("no infographic tile/button found")
        print(json.dumps({"open": False, "tile": None})); return
    # hover over tile to reveal chevron, then click far-right of tile
    r = tile[1]
    hx = r.right - 22; hy = (r.top + r.bottom)//2
    u.SetCursorPos(hx, hy); time.sleep(1.5)  # hover to reveal
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0)
    time.sleep(1.0)
    # re-check
    for t, n, r in walk(root, lambda t, n, r: t.ControlTypeName=='WindowControl' and 'Customize Infographic' in n):
        print("dialog opened:", n); print(json.dumps({"open": True})); return
    print("dialog did not open after chevron click")
    print(json.dumps({"open": False}))

if __name__=="__main__":
    main()

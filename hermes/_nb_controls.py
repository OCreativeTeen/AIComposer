"""Step 3.2 probe: find the NotebookLM Customize Infographic controls.
- the Infographic tile + its far-right chevron (hover-revealed)
- 'Describe the infographic you want to create' EditControl
- Language/Portrait/Concise radios
Module-level enum (reliable). Print clickable control names+rects.
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
    print("=== controls of interest ===")
    for t, n, r in walk(root, lambda t, n, r:
            any(k in n for k in ['Infographic','Customize','Describe','Language',
                                  'Portrait','Concise','Generate','Landscape',
                                  'Standard','Detailed','Studio','Export'])):
        print(f"  [{t.ControlTypeName}] {n!r} rect=({r.left},{r.top},{r.right},{r.bottom})")

if __name__=="__main__":
    main()

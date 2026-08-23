"""Probe current NotebookLM window for export-related controls and their rects.
Reports: per-row 'Export信息图' buttons, any open export dialog, JPG/Export Image
buttons, and Download folder jpgs. No mutation.
"""
import uiautomation as auto
import ctypes, win32gui, json, os, time

u = ctypes.windll.user32
NB_HWND = 0x3098c
DL = os.path.expanduser("~/Downloads")

def walk(root, pred, depth=46):
    for t, d in auto.WalkControl(root, maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            yield t, n, r

def main():
    root = auto.ControlFromHandle(NB_HWND)
    root.SetActive(); time.sleep(1.5)
    print("=== export-ish controls ===")
    for t, n, r in walk(root, lambda t, n, r: 'Export' in n or 'JPG' in n or 'PNG' in n or 'WEBP' in n or 'Download' in n):
        print(f"  [{t.ControlTypeName}] {n!r} rect=({r.left},{r.top},{r.right},{r.bottom})")
    print("=== recent Downloads jpgs ===")
    files = [os.path.join(DL,f) for f in os.listdir(DL) if f.lower().endswith('.jpg')]
    files.sort(key=os.path.getmtime, reverse=True)
    for f in files[:5]:
        print("   ", os.path.basename(f), int(os.path.getmtime(f)))

if __name__=="__main__":
    main()

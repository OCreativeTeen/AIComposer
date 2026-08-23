"""NotebookLM Studio helper: locate window, find the target notebook, probe
controls, check quota banner. Drives the live signed-in Profile 3 window via UIA.
"""
import uiautomation as auto
import win32gui, win32process, time, sys, ctypes, re

USER32 = ctypes.windll.user32

def nb_windows():
    """Top-level Chrome windows that are on notebooklm.google.com."""
    out=[]
    def cb(h,_):
        if not win32gui.IsWindowVisible(h): return 1
        t=win32gui.GetWindowText(h)
        if 'Google Chrome' in t and ('NotebookLM' in t or 'notebook' in t.lower()):
            out.append((h,t))
        return 1
    win32gui.EnumWindows(cb,None)
    return out

def find_target():
    """Return (hwnd, title) of a window showing the Story Builder notebook."""
    for h,t in nb_windows():
        if 'Story Builder' in t:
            return h,t
    # fallback: any notebooklm window
    w=nb_windows()
    return (w[0] if w else (None,None))

def walk_buttons(hwnd, depth=40):
    w=auto.ControlFromHandle(hwnd)
    out=[]
    for t,d in auto.WalkControl(w, maxDepth=depth):
        n=(t.Name or '').strip()
        if t.ControlTypeName in ('ButtonControl','HyperlinkControl','EditControl','ComboBoxControl','RadioButtonControl') and n:
            r=t.BoundingRectangle
            out.append((t.ControlTypeName, n, r.left, r.top, r.width(), r.height()))
    return out

def quota_banner(hwnd, depth=40):
    w=auto.ControlFromHandle(hwnd)
    for t,d in auto.WalkControl(w, maxDepth=depth):
        n=(t.Name or '').strip().lower()
        if 'daily' in n and 'limit' in n:
            return t.Name
    return None

def main():
    h,t=find_target()
    print("NB window:", hex(h) if h else None, t)
    if not h:
        print("NO notebooklm window"); return
    print("\n--- controls (name + rect) ---")
    for ctype,n,x,y,bw,bh in walk_buttons(h):
        print(f"  [{ctype}] {n!r} @({x},{y}) {bw}x{bh}")
    print("\nquota banner:", quota_banner(h))

if __name__=='__main__':
    main()

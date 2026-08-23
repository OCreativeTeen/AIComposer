"""Switch to a Chrome tab by title within a Chrome window, then read its URL.
Uses ground-truth tab-strip coordinates (reliable) rather than UIA TabItem.Click
(which silently no-ops on Chrome)."""
import uiautomation as auto
import win32gui, win32process, time, sys, ctypes

USER32 = ctypes.windll.user32

def chrome_windows():
    out=[]
    def cb(h,_):
        if win32gui.IsWindowVisible(h):
            try:
                pid=win32process.GetWindowThreadProcessId(h)[1]
                import psutil; name=psutil.Process(pid).name()
            except Exception:
                return 1
            if name.lower()=='chrome.exe':
                out.append((h, win32gui.GetWindowText(h)))
        return 1
    win32gui.EnumWindows(cb,None)
    return out

def tab_strip_items(hwnd, depth=14):
    """Enumerate UIA TabItemControl with rects (for ground-truth click)."""
    w=auto.ControlFromHandle(hwnd)
    items=[]
    for t,d in auto.WalkControl(w, maxDepth=depth):
        if t.ControlTypeName=='TabItemControl':
            n=(t.Name or '').strip()
            r=t.BoundingRectangle
            if r.width() and n:
                items.append((n, r.left+r.width()//2, r.top+r.height()//2))
    return items

def switch_and_url(hwnd, sub):
    items=tab_strip_items(hwnd)
    print("tabs found:")
    for n,x,y in items:
        print(f"  {n!r} center=({x},{y})")
    target=[(n,x,y) for n,x,y in items if sub in n]
    if not target:
        print("tab not found"); return None
    n,x,y=target[0]
    w=auto.ControlFromHandle(hwnd); w.SetActive(); time.sleep(0.8)
    USER32.SetCursorPos(x,y); time.sleep(0.3)
    USER32.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); USER32.mouse_event(0x0004,0,0,0,0)
    time.sleep(1.2)
    # read address bar
    for t,d in auto.WalkControl(w, maxDepth=14):
        if t.ControlTypeName=='EditControl' and (t.Name or '').strip()=='Address and search bar':
            try: return t.GetValuePattern().Value
            except Exception: return "(read fail)"
    return "(no addr)"

if __name__=='__main__':
    sub=sys.argv[1] if len(sys.argv)>1 else "Google Gemini"
    wins=chrome_windows()
    for hwnd,title in wins:
        if "notebook" in title.lower() or "Gemini" in title or "Grok" in title:
            print(f"\n=== window {hex(hwnd)} {title!r}")
            url=switch_and_url(hwnd, sub)
            print("URL now:", url)
            if url and 'gemini.google.com/app' in url:
                print("GEMINI APP TAB ACTIVE"); break

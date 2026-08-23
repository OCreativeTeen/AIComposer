"""Safe Tk click + window finders for AIComposer (physical coords, mouse_event)."""
import uiautomation as auto  # MUST be first -> process DPI-aware
import win32gui, win32process, time, ctypes

USER32 = ctypes.windll.user32

def find_root():
    for w in auto.GetRootControl().GetChildren():
        nm = w.Name.strip()
        if "AIComposer" in nm and "YT 工具" in nm:
            return w.NativeWindowHandle
    return None

def find_by_sub(sub, exclude=""):
    rhwnd = find_root()
    if rhwnd:
        root = auto.ControlFromHandle(rhwnd)
        for c, depth in auto.WalkControl(root, maxDepth=4):
            hw = c.NativeWindowHandle
            nm = c.Name.strip()
            if hw and sub in nm and exclude not in nm:
                return hw
    for w in auto.GetRootControl().GetChildren():
        if sub in w.Name and exclude not in w.Name:
            return w.NativeWindowHandle
    return None

def safe_click(hwnd, x, y, hold=0.09, pre_sleep=1.0, post_sleep=0.6):
    """Click at (x,y) PHYSICAL-relative to hwnd's UIA BoundingRectangle origin."""
    ctl = auto.ControlFromHandle(hwnd)
    ctl.SetActive()
    time.sleep(pre_sleep)
    r = ctl.BoundingRectangle
    ax, ay = r.left + x, r.top + y
    USER32.SetCursorPos(ax, ay)
    time.sleep(0.35)
    USER32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(hold)
    USER32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(post_sleep)
    return ax, ay

def tk_button_centers(hwnd):
    """Return list of (cx, cy, w, h) for TkChild button-ish children."""
    kids = []
    def enum(h, _):
        kids.append((h, win32gui.GetClassName(h), win32gui.GetWindowRect(h)))
        return 1
    win32gui.EnumChildWindows(hwnd, enum, None)
    out = []
    for h, cls, rect in kids:
        if cls != 'TkChild':
            continue
        w, hh = rect[2]-rect[0], rect[3]-rect[1]
        if 15 < hh < 140 and 15 < w < 600:
            out.append((rect[0] + w//2, rect[1] + hh//2, w, hh))
    return out

import ctypes, uiautomation as auto, win32gui, win32con, time
USER32=ctypes.windll.user32

def find_root():
    for w in auto.GetRootControl().GetChildren():
        nm=w.Name.strip()
        if "AIComposer" in nm and "YT 工具" in nm: return w.NativeWindowHandle,nm
    return None,None
def find_detail():
    rhwnd,_=find_root()
    root=auto.ControlFromHandle(rhwnd)
    for c,depth in auto.WalkControl(root,maxDepth=3):
        hw=c.NativeWindowHandle; nm=c.Name.strip()
        if hw and ("摘要" in nm or "拖入" in nm): return hw,nm
    return None,None

rhwnd,_=find_root(); dhwnd,_=find_detail()
print("root hwnd", hex(rhwnd), "detail hwnd", hex(dhwnd))

# What window owns screen point (130,715)?
class POINT(ctypes.Structure):
    _fields_=[("x",ctypes.c_long),("y",ctypes.c_long)]
pt=POINT(130,715)
hw_under=USER32.WindowFromPoint(pt)
print("WindowFromPoint(130,715) ->", hex(hw_under if hw_under else 0))
# get its class + title
try:
    title=win32gui.GetWindowText(hw_under)
    cls=win32gui.GetClassName(hw_under)
    print("   title:", repr(title), "class:", cls)
except Exception as e:
    print("   err", e)

# Is detail window visible & on-screen? Use IsWindowVisible + GetWindowRect (win32, logical)
print("IsWindowVisible(detail):", win32gui.IsWindowVisible(dhwnd))
print("win32 GetWindowRect(detail):", win32gui.GetWindowRect(dhwnd))
print("win32 GetWindowRect(root):", win32gui.GetWindowRect(rhwnd))

# Enumerate all AIComposer-owned windows with their win32 rects
def enum(hwnd, _):
    if win32gui.IsWindowVisible(hwnd):
        t=win32gui.GetWindowText(hwnd)
        if "摘要" in t or "AIComposer" in t or "拖入" in t or "YT" in t:
            print("  vis hwnd", hex(hwnd), "rect", win32gui.GetWindowRect(hwnd), repr(t[:40]))
auto.EnumWindows(lambda h,p: (enum(h,p), False)[1], None)

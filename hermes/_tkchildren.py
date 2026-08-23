import win32gui, win32con, ctypes, uiautomation as auto
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
dhwnd,_=find_detail()
print("detail hwnd", hex(dhwnd))

children=[]
def enum(hwnd, _):
    if hwnd==dhwnd: return
    rect=win32gui.GetWindowRect(hwnd)
    cls=win32gui.GetClassName(hwnd)
    t=win32gui.GetWindowText(hwnd)
    children.append((hwnd,cls,t,rect))
win32gui.EnumChildWindows(dhwnd, enum, None)
print("total children:", len(children))
# filter to smallish rects (buttons/inputs), sort by y then x
def h(r): return r[3]-r[1]
def w(r): return r[2]-r[0]
rects=[c for c in children if c[1]=='TkChild' and 20< h(c[3]) <120 and 20<w(c[3])<400]
print("button-ish TkChild count:", len(rects))
for hw,cls,t,rect in sorted(rects, key=lambda c:(c[3][1],c[3][0])):
    print(f"  hw={hex(hw)} rect={rect} size=({w(rect)}x{h(rect)}) title={t!r}")

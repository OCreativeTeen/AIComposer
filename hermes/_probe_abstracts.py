import uiautomation as auto  # MUST be first import -> DPI-aware
import win32gui

def find_root():
    for w in auto.GetRootControl().GetChildren():
        nm = w.Name.strip()
        if "AIComposer" in nm and "YT 工具" in nm:
            return w.NativeWindowHandle, nm
    return None, None

def find_by_sub(sub):
    rhwnd, _ = find_root()
    if rhwnd:
        root = auto.ControlFromHandle(rhwnd)
        for c, depth in auto.WalkControl(root, maxDepth=4):
            hw = c.NativeWindowHandle
            nm = c.Name.strip()
            if hw and sub in nm:
                return hw, nm
    for w in auto.GetRootControl().GetChildren():
        if sub in w.Name:
            return w.NativeWindowHandle, w.Name
    return None, None

hwnd, nm = find_by_sub("摘要")
print("hwnd", hex(hwnd), repr(nm))
r = auto.ControlFromHandle(hwnd).BoundingRectangle
print("UIA BoundingRectangle:", (r.left, r.top, r.right, r.bottom), "size", r.width(), r.height())
wr = win32gui.GetWindowRect(hwnd)
print("win32 GetWindowRect:", wr, "size", wr[2]-wr[0], wr[3]-wr[1])

kids = []
def enum(h, _):
    kids.append((h, win32gui.GetClassName(h), win32gui.GetWindowRect(h), win32gui.GetWindowText(h)))
    return 1
win32gui.EnumChildWindows(hwnd, enum, None)

def h_(r): return r[3]-r[1]
def w_(r): return r[2]-r[0]

print("\n=== TkChild buttons (with label text) ===")
rows = [(hw, cls, rect, txt) for hw, cls, rect, txt in kids
        if cls == 'TkChild' and 15 < h_(rect) < 140 and 15 < w_(rect) < 600]
for hw, cls, rect, txt in sorted(rows, key=lambda k: (k[2][1], k[2][0])):
    cx = rect[0] + w_(rect)//2
    cy = rect[1] + h_(rect)//2
    print(f"  label={txt!r:20} rect={rect} size=({w_(rect)}x{h_(rect)}) center=({cx},{cy})")

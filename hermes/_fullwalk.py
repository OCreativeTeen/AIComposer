import uiautomation as auto, win32gui, win32con, time, ctypes
USER32=ctypes.windll.user32
def find_root():
    for w in auto.GetRootControl().GetChildren():
        nm=w.Name.strip()
        if "AIComposer" in nm and "YT 工具" in nm: return w.NativeWindowHandle,nm
    return None,None
rhwnd,_=find_root()
root=auto.ControlFromHandle(rhwnd)
print("=== FULL WALK from root (depth up to 8) ===")
seen=set()
for c,depth in auto.WalkControl(root, maxDepth=8):
    hw=c.NativeWindowHandle; nm=c.Name.strip()
    if hw and nm and hw not in seen:
        seen.add(hw)
        r=c.BoundingRectangle
        tag=""
        if any(k in nm for k in ("分镜","Scene","编辑","Editor","提示","LM","脚本","诗歌")): tag="<<<"
        print(f"  d{depth} hw={hex(hw)} {c.ControlTypeName} {nm!r} rect=({r.left},{r.top},{r.right},{r.bottom}) {tag}")
# also list ALL top-level windows with AIComposer in title or any MessageBox
print("\n=== top-level windows ===")
for w in auto.GetRootControl().GetChildren():
    nm=w.Name.strip()
    if nm: print("  ", hex(w.NativeWindowHandle), w.ControlTypeName, repr(nm))

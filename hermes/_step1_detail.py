import uiautomation as auto, ctypes

USER32 = ctypes.windll.user32
def hwnd_pid(hwnd):
    pid = ctypes.c_int(0)
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

def is_iconic(hwnd):
    return bool(USER32.IsIconic(hwnd))

root_hwnd = 0x20452
root = auto.ControlFromHandle(root_hwnd)
print("root exists:", root.Exists(1,1))
print("root IsIconic:", is_iconic(root_hwnd))
print("root rect:", root.BoundingRectangle)

print("\n=== walk children (maxDepth=3) ===")
for c, depth in auto.WalkControl(root, maxDepth=3):
    hwnd = c.NativeWindowHandle
    nm = c.Name.strip()
    r = c.BoundingRectangle
    if hwnd and (nm or c.ControlTypeName in ("WindowControl",)):
        tag = "DETAIL" if ("摘要" in nm or "拖入" in nm) else ""
        print(f"  d{depth} hwnd={hwnd:#x} pid={hwnd_pid(hwnd)} {c.ControlTypeName} {nm!r} rect=({r.left},{r.top},{r.right},{r.bottom}) {tag}")
        if "摘要" in nm or "拖入" in nm:
            print("      IsIconic:", is_iconic(hwnd))

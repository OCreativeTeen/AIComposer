import ctypes, uiautomation as auto

USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32

def hwnd_pid(hwnd):
    pid = ctypes.c_int(0)
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

target_pid = 10104
print(f"=== Windows owned by PID {target_pid} ===")
found = False
for w in auto.GetRootControl().GetChildren():
    hwnd = w.NativeWindowHandle
    if hwnd and hwnd_pid(hwnd) == target_pid:
        found = True
        r = w.BoundingRectangle
        print(f"  ROOT hwnd={hwnd:#x} {w.ControlTypeName} {w.Name!r} rect=({r.left},{r.top},{r.right},{r.bottom})")
# also walk deeper for child toplevels
for w in auto.GetRootControl().GetChildren():
    hwnd = w.NativeWindowHandle
    if not hwnd:
        continue
    # walk this window's descendants for any owned by target_pid
    for c, depth in auto.WalkControl(w, maxDepth=3):
        ch = c.NativeWindowHandle
        if ch and hwnd_pid(ch) == target_pid and ch != hwnd:
            r = c.BoundingRectangle
            print(f"  CHILD hwnd={ch:#x} depth={depth} {c.ControlTypeName} {c.Name!r} rect=({r.left},{r.top},{r.right},{r.bottom})")
print("DONE found=", found)

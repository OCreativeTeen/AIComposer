#!/usr/bin/env python3
"""Wait (bounded) for the AIComposer detail editor window, then report its hwnd + rect."""
import sys, time, ctypes
import uiautomation as auto

targets = ("AIComposer — YT 工具", "摘要", "分镜", "YT 工具")
deadline = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 40)
found = []
while time.time() < deadline:
    for w in auto.GetRootControl().GetChildren():
        nm = (w.Name or "").strip()
        if nm and any(t in nm for t in targets):
            r = w.BoundingRectangle
            found.append((w.NativeWindowHandle, nm, r.left, r.top, r.width(), r.height()))
    if found:
        break
    time.sleep(1.5)

if not found:
    print("NO_WINDOW_YET")
else:
    for hwnd, nm, l, t, w, h in found:
        print(f"HWND={hwnd} | {nm!r} | {l},{t},{w}x{h}")

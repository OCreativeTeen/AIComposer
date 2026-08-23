#!/usr/bin/env python3
"""Find the AIComposer 摘要 detail editor (child Toplevel) under the root window."""
import sys, time, json, ctypes
import uiautomation as auto

ROOT_HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 919976
root = auto.ControlFromHandle(ROOT_HWND)
if not root.Exists(3, 1):
    print("ROOT_NOT_FOUND", ROOT_HWND)
    sys.exit(0)

print("root:", repr(root.Name), root.BoundingRectangle)
print("--- child Toplevels (depth<=3) ---")
for c, depth in auto.WalkControl(root, maxDepth=3):
    if c.ControlTypeName == "WindowControl":
        r = c.BoundingRectangle
        print(f"  d{depth} hwnd={c.NativeWindowHandle} {r.width()}x{r.height()} | {c.Name!r}")

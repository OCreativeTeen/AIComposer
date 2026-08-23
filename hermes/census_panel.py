#!/usr/bin/env python3
"""Census of the 分镜 panel controls to locate the scene_content textarea."""
import sys
import uiautomation as auto

EDITOR_HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 1115942
editor = auto.ControlFromHandle(EDITOR_HWND)
panel = None
for c, d in auto.WalkControl(editor, maxDepth=3):
    if c.ControlTypeName == "WindowControl" and "分镜" in (c.Name or ""):
        panel = c; break
if panel is None:
    print("PANEL_GONE"); sys.exit(0)
pr = panel.BoundingRectangle
print("panel rect:", pr.left, pr.top, pr.width(), pr.height())
print("--- controls (name | type | rect) depth<=6 ---")
n = 0
for c, d in auto.WalkControl(panel, maxDepth=6):
    nm = (c.Name or "").strip()
    r = c.BoundingRectangle
    if r.width() and (nm or c.ControlTypeName in ("EditControl","TextControl","ButtonControl")):
        print(f"  d{d} {c.ControlTypeName:13} | {nm[:30]!r} | {r.left},{r.top},{r.width()}x{r.height()}")
        n += 1
    if n > 80:
        break

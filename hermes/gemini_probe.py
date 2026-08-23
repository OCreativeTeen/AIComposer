#!/usr/bin/env python3
"""Enumerate tabs + address-bar URL of a Chrome window, to pick the real
gemini.google.com/app chat tab (NOT a Notebook tab)."""
import sys, time
import uiautomation as auto

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 2032376
w = auto.ControlFromHandle(HWND)
if not w.Exists(3, 1):
    print("WINDOW_GONE"); sys.exit(0)
print("window:", repr(w.Name), w.BoundingRectangle)

# address bar
addr = None
for c, d in auto.WalkControl(w, maxDepth=40):
    if c.ControlTypeName == "EditControl" and (c.Name or "").strip() == "Address and search bar":
        addr = c; break
if addr:
    print("ADDRESS:", addr.GetValuePattern().Value)
else:
    print("NO_ADDRESS_BAR")

# tab items
print("--- tabs ---")
n = 0
for c, d in auto.WalkControl(w, maxDepth=40):
    if c.ControlTypeName == "TabItemControl":
        print("  TAB:", repr(c.Name))
        n += 1
    if n > 40:
        break

#!/usr/bin/env python3
"""Locate Gemini's response 'Copy' action. Walks UIA for buttons whose name
suggests copy (copy/复制/duplicate), and reports rects. Also dumps all
ButtonControls with small names for inspection."""
import sys
import uiautomation as auto

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 2032376
w = auto.ControlFromHandle(HWND)
print("window:", repr(w.Name))
print("--- candidate copy buttons ---")
seen = []
for c, d in auto.WalkControl(w, maxDepth=42):
    nm = (c.Name or "").strip().lower()
    ct = c.ControlTypeName
    if ct == "ButtonControl" and ("copy" in nm or "复制" in nm or "duplicate" in nm):
        r = c.BoundingRectangle
        print(f"  d{d} hwnd={c.NativeWindowHandle} {ct} {r.left},{r.top},{r.width()}x{r.height()} | {nm!r}")
        seen.append((r.left, r.top, r.width(), r.height()))
print("--- all ButtonControls with non-empty short names (first 60) ---")
n = 0
for c, d in auto.WalkControl(w, maxDepth=42):
    nm = (c.Name or "").strip()
    if c.ControlTypeName == "ButtonControl" and 0 < len(nm) <= 30:
        r = c.BoundingRectangle
        print(f"  d{d} {r.left},{r.top},{r.width()}x{r.height()} | {nm!r}")
        n += 1
        if n > 60:
            break
print("COPY_CANDIDATES:", len(seen))

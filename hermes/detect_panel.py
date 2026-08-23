#!/usr/bin/env python3
"""Screenshot the 分镜 panel region and edge-detect (a) the large scene_content
textarea and (b) the uniform bottom button row."""
import sys, time, ctypes
import cv2, numpy as np
from PIL import ImageGrab
import uiautomation as auto

EDITOR_HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 1115942
editor = auto.ControlFromHandle(EDITOR_HWND)
panel = None
for c, d in auto.WalkControl(editor, maxDepth=3):
    if c.ControlTypeName == "WindowControl" and "分镜" in (c.Name or ""):
        panel = c; break
pr = panel.BoundingRectangle
L, T, R, B = pr.left, pr.top, pr.right, pr.bottom
print("panel bbox", L, T, R, B)
img = ImageGrab.grab((L, T, R, B))
img.save("hermes/panel_shot.png")
print("saved hermes/panel_shot.png", img.size)

im = cv2.imread("hermes/panel_shot.png")
gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
# find large light (textarea) rectangles via threshold + contours
_, binv = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
cnts, _ = cv2.findContours(binv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print("=== large light regions (text areas) ===")
for c in cnts:
    x, y, w, h = cv2.boundingRect(c)
    if w > 300 and h > 80:
        print(f"  x={x} y={y} w={w} h={h}")

# button row detection: uniform ~113x37 rects near bottom
edges = cv2.dilate(cv2.Canny(gray, 30, 120), np.ones((2,2), np.uint8))
cnts2, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print("=== candidate buttons (30<w<220, 18<h<50) grouped by y ===")
from collections import defaultdict
rows = defaultdict(list)
for c in cnts2:
    x, y, w, h = cv2.boundingRect(c)
    if 30 < w < 220 and 18 < h < 50:
        rows[round(y/5)*5].append((x+w//2, y+h//2, w, h))
for ry in sorted(rows):
    if ry > im.shape[0] - 250:  # near bottom
        print(f"  y={ry}: " + ", ".join(f"({cx},{cy}){w}x{h}" for cx,cy,w,h in sorted(rows[ry])))

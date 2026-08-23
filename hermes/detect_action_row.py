#!/usr/bin/env python3
"""Resolve the 摘要 editor rect, screenshot it, edge-detect the action-row
buttons (uniform 114x38 rects around y=520-630), and print click centers."""
import sys, time, ctypes
import cv2, numpy as np
from PIL import ImageGrab
import uiautomation as auto

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 1115942
EDITOR = auto.ControlFromHandle(HWND)
EDITOR.SetActive(); time.sleep(1.0)
r = EDITOR.BoundingRectangle
L, T, W, H = r.left, r.top, r.width(), r.height()
print(f"EDITOR rect: left={L} top={T} w={W} h={H}")
if W < 200 or H < 200:
    print("EDITOR_NOT_VISIBLE", W, H); sys.exit(0)

img = ImageGrab.grab(bbox=(L, T, L + W, T + H))
img.save("hermes/editor_now.png")
print("screenshot saved hermes/editor_now.png", img.size)

im = cv2.imread("hermes/editor_now.png")
if im is None:
    print("SCREENSHOT_READ_FAIL"); sys.exit(0)
gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
# action-row band: y 490..640 (window-relative)
band = gray[490:640, :]
edges = cv2.dilate(cv2.Canny(band, 30, 120), np.ones((2, 2), np.uint8))
cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
found = []
for c in cnts:
    x, y, w, h = cv2.boundingRect(c)
    if 30 < w < 220 and 18 < h < 50:
        found.append((x + w // 2, 490 + y + h // 2, w, h))
# group by y (row)
from collections import defaultdict
rows = defaultdict(list)
for cx, cy, w, h in found:
    rows[round(cy / 5) * 5].append((cx, cy, w, h))
print("=== candidate button centers ===")
for ry in sorted(rows):
    for cx, cy, w, h in sorted(rows[ry]):
        print(f"  y={cy:4d} x={cx:4d}  {w}x{h}")

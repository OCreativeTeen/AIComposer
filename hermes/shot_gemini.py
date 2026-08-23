#!/usr/bin/env python3
"""Screenshot the Gemini chat window region and save for visual inspection."""
import sys, time, ctypes
from PIL import ImageGrab
import uiautomation as auto

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 2032376
w = auto.ControlFromHandle(HWND)
w.SetActive(); time.sleep(1.0)
r = w.BoundingRectangle
bbox = (r.left, r.top, r.right, r.bottom)
print("bbox", bbox)
img = ImageGrab.grab(bbox)
img.save("hermes/gemini_view.png")
print("saved hermes/gemini_view.png", img.size)

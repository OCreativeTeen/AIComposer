#!/usr/bin/env python3
"""Crop the action row band and the 场景 region for vision label verification."""
import cv2, numpy as np
from PIL import Image

im = Image.open("hermes/editor_now.png")
# Crop the whole action row band (y 505..575 window-relative) into a contact strip
band = im.crop((0, 505, 1614, 575))
band.save("hermes/action_row_strip.png")
# Also crop each candidate button tightly for label reading
img = cv2.imread("hermes/editor_now.png")
centers = [(284,535),(456,535),(585,535),(714,535),(843,535),(1023,535)]
labels = []
for i,(cx,cy) in enumerate(centers):
    crop = img[cy-22:cy+18, cx-60:cx+60]
    cv2.imwrite(f"hermes/btn_{i}.png", crop)
    labels.append(f"btn_{i}")
print("saved: action_row_strip.png +", labels)

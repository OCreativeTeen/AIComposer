import numpy as np, cv2, os
from collections import defaultdict

# The band image is im[520:640,:]  -> 1614x120, already Canny (white edges on black)
band = cv2.imread(r"D:\AIComposer\hermes\_dbg_canny.png", cv2.IMREAD_GRAYSCALE)
H, W = band.shape
print("band", W, H, "nonzero px:", int((band>0).sum()))

# find contours (white = edges). Use RETR_EXTERNAL; hollow rect -> one contour per button outline
cnts, _ = cv2.findContours(band, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print("contours total:", len(cnts))
cands = []
for c in cnts:
    x,y,w,h = cv2.boundingRect(c)
    area = cv2.contourArea(c)
    if 60 < w < 200 and 18 < h < 50 and area > 200:
        cands.append((x+w//2, y+h//2, w, h, area))
cands.sort(key=lambda t:(t[1], t[0]))
print("\n=== band button candidates (center relative to band, +520 for full image y) ===")
for cx, cy, w, h, a in cands:
    print(f"  center=({cx:4d},{cy+520:4d})  size=({w}x{h}) area={int(a)}")

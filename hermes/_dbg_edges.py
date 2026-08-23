import numpy as np, cv2, os
from PIL import Image

png = r"D:\AIComposer\hermes\detail_now.png"
im = cv2.imread(png)
H, W = im.shape[:2]
print("image size", W, H)

gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
print("gray stats min/max/mean", int(gray.min()), int(gray.max()), round(float(gray.mean()),1))
# histogram of gray to see if mostly uniform (flat UI)
hist = cv2.calcHist([gray],[0],None,[16],[0,256]).flatten()
for i,v in enumerate(hist):
    print(f"  bin {i*16:3d}-{i*16+15:3d}: {int(v)}")

def edge_buttons(png_path, ymin, ymax, canny=(20,120), wmin=40, wmax=260, hmin=14, hmax=60):
    im = cv2.imread(png_path)
    H, W = im.shape[:2]
    ymin = max(0, ymin); ymax = min(H, ymax)
    roi = im[ymin:ymax, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, *canny), np.ones((3,3), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if wmin < w < wmax and hmin < h < hmax:
            out.append((x + w//2, ymin + y + h//2, w, h))
    return out

allc = edge_buttons(png, 0, H)
print("\n=== candidates (full) count:", len(allc))
for cx, cy, w, h in sorted(allc, key=lambda t:(t[1],t[0])):
    print(f"  ({cx:4d},{cy:4d}) size=({w}x{h})")

from collections import defaultdict
rows = defaultdict(list)
for cx, cy, w, h in allc:
    rows[round(cy/6)*6].append((cx, cy, w, h))
print("\n=== rows ===")
for y in sorted(rows):
    print(f"  y~{y}: x={[c[0] for c in rows[y]]}")

# save a debug canny of the lower band
roi = im[520:640,:]
cv2.imwrite(r"D:\AIComposer\hermes\_dbg_canny.png", cv2.dilate(cv2.Canny(cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY),20,120),np.ones((3,3),np.uint8)))
print("saved debug canny")

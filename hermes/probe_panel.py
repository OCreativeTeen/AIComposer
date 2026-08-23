import sys; sys.path.insert(0,'hermes')
import time, uiautomation as auto, wf_lib
from PIL import ImageGrab
import cv2, numpy as np
detail_hwnd=198900
wf_lib.activate(detail_hwnd,0.8)
time.sleep(0.5)
r=wf_lib.ctl(detail_hwnd).BoundingRectangle
im=np.array(ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom)))
# panel region physical
x0,x1,y0,y1 = 1029,1404,105,1289
f = im[y0:y1, x0:x1].copy()
cv2.imwrite('hermes/panel_crop.png', f)
print("panel crop shape", f.shape)
g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
bg = int(np.median(g))
# find combobox fields: a horizontal band of width ~ panel width with a border (edge), containing a dropdown arrow
edges = cv2.Canny(g, 35, 110)
# rows with strong horizontal edges (top/bottom border of a field)
row_edges = edges.sum(axis=1)
strong=[i for i in range(len(row_edges)) if row_edges[i] > 120]
print("strong-edge rows (field borders) in panel:", strong)
# For each strong row, find x extents
for y in strong[:30]:
    cols=np.where(edges[y]>0)[0]
    if len(cols):
        print(f"  y={y} xrange={cols.min()}..{cols.max()}")

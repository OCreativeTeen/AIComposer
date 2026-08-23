import cv2, numpy as np
im = cv2.imread('hermes/scene_panel_open.png')
g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
x0=1029; x1=1404
# Scan band y 250..400 for combobox fields: a horizontal run of near-uniform light fill with darker top/bottom border
band = im[250:400, x0:x1]
bg2 = int(np.median(cv2.cvtColor(band,cv2.COLOR_BGR2GRAY)))
# detect field boxes via contour on inverted-threshold of the fill difference from bg
gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
# A readonly combobox has a subtle 1px border ~ value 210 vs bg 240. Threshold edges.
edges = cv2.Canny(gray, 30, 100)
# dilate to connect
edges = cv2.dilate(edges, np.ones((2,3),np.uint8), iterations=1)
cnts,_ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
rects=[]
for c in cnts:
    x,y,w,h = cv2.boundingRect(c)
    # field is wide (panel width ~375), short height ~24-30
    if w>250 and 18<h<40:
        rects.append((x, 250+y, w, h))
rects.sort(key=lambda r:r[1])
print("candidate combobox field boxes (localx, physy, w, h):")
for r in rects:
    print("  ", r, "center_y=", r[1]+r[3]//2)
cv2.imwrite('hermes/combo_fields.png', band)
print("saved hermes/combo_fields.png")

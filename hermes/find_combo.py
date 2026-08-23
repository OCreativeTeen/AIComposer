import cv2, numpy as np
im = cv2.imread('hermes/scene_panel_open.png')
H,W,_=im.shape
g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
bg = int(np.median(g))
# The 分镜 panel x-range ~ 1029..1404 in physical px (from UIA). Search there.
x0,x1 = 1029,1404
sub = im[:, x0:x1]
sg = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
# glyph columns (text)
glyph = (sg.astype(int)-bg) < -25
colcount = glyph.sum(axis=0)
# find contiguous text columns -> these are text/label regions
mask = colcount >= 5
runs=[]; x=0; n=len(mask)
while x<n:
    if mask[x]:
        s=x
        while x<n and mask[x]: x+=1
        runs.append([s,x])
    else: x+=1
# top text band (y < 300): the 选LM提示 label + combobox are near y 250-340
# Find rows with text in the band 240..360
bandmask = (glyph[:, 240:360].sum(axis=1)) >= 4
rows_with_text = np.where(bandmask)[0]
print("text rows in band 240-360 (local 0=1029):", rows_with_text[:40])
# For the combobox: it has a field box. Look at rows 300-340 for a bordered box:
# Detect horizontal line segments (combobox top border) in x-range
# Simpler: print x-extent of text in rows 300..340
for y in range(290,345,5):
    c = np.where(glyph[:,y])[0]
    if len(c):
        print(f"row {y}: text x {c.min()}..{c.max()}  (physical x {c.min()+x0}..{c.max()+x0})")
# The combobox field typically sits just below the label. Save annotated crop
cv2.imwrite('hermes/combo_band.png', sub[280:360, :])
print("saved hermes/combo_band.png")

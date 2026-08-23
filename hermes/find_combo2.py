import cv2, numpy as np
im = cv2.imread('hermes/scene_panel_open.png')
H,W,_=im.shape
g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
bg = int(np.median(g))
x0=1029
# Band for 选LM提示 combobox: y 250..300 (just below the label at ~262)
band = im[250:305, x0:1404]
bg2 = int(np.median(cv2.cvtColor(band,cv2.COLOR_BGR2GRAY)))
# find the combobox field: a row of horizontal edges (top/bottom border)
edges = cv2.Canny(cv2.cvtColor(band,cv2.COLOR_BGR2GRAY),40,120)
row_edges = edges.sum(axis=1)
print("band rows with >80 edge px (local y 0..55):", [i for i in range(len(row_edges)) if row_edges[i]>80])
# Find the dropdown arrow on the right: a small box near right edge of field
# The field spans most of panel width; locate text 'Short Story' glyphs to know vertical center
glyph = (cv2.cvtColor(band,cv2.COLOR_BGR2GRAY).astype(int)-bg2) < -25
colcount = glyph.sum(axis=0)
# text x-range
xs=np.where(colcount>=4)[0]
print("text x-range in band (local):", (int(xs.min()),int(xs.max())) if len(xs) else "none")
# The combobox field box: look at the full panel width for a bordered rectangle near y~270-295
# Save band crop for vision
cv2.imwrite('hermes/combo_lm_band.png', band)
print("saved hermes/combo_lm_band.png shape", band.shape)

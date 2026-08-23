import numpy as np, cv2, os

img = cv2.imread(r"D:\AIComposer\hermes\gem_right.png")
H, Wd, _ = img.shape
print("right pane size", Wd, H)
# The response card copy button is top-right of the card. The card likely starts at x~ a bit right of W/2 boundary.
# Crop top-right quadrant of the right pane to find the icon row
crop = img[40:160, Wd-500:Wd-20]
cv2.imwrite(r"D:\AIComposer\hermes\_rtop.png", crop)
print("saved _rtop.png", crop.shape[1], crop.shape[0])
# also look for the typical icon: small cluster of bright pixels near top-right of the dark card.
# Save a zoomed version of the very top-right 300x140
crop2 = img[40:180, Wd-360:Wd-20]
cv2.imwrite(r"D:\AIComposer\hermes\_rtop2.png", crop2)
print("saved _rtop2.png", crop2.shape[1], crop2.shape[0])

import uiautomation as auto, win32gui, win32con, time
from PIL import ImageGrab
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
W=right-left; H=bottom-top
# The response card: vision said text starts "跑的光," near top of card.
# Card likely occupies right pane y ~ 300..1300. Header icons near top of card.
# Capture right pane full and also a band y 250..520 across full right pane width.
img=ImageGrab.grab(bbox=(left,top,right,bottom))
img.crop((left+W//2, top+250, right, top+540)).save(r"D:\AIComposer\hermes\_cardhead.png")
print("saved _cardhead.png", W//2, 290)

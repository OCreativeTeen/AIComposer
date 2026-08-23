import uiautomation as auto, win32gui, win32con, time
from PIL import ImageGrab
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
W=right-left
# The response card: split right pane into vertical thirds and save each for inspection
img=ImageGrab.grab(bbox=(left+W//2, top, right, bottom))
iw=img.width; ih=img.height
# Save top, mid, bottom thirds
img.crop((0,0,iw,ih//3)).save(r"D:\AIComposer\hermes\_rp_top.png")
img.crop((0,ih//3, iw, 2*ih//3)).save(r"D:\AIComposer\hermes\_rp_mid.png")
img.crop((0,2*ih//3, iw, ih)).save(r"D:\AIComposer\hermes\_rp_bot.png")
print("saved thirds", iw, ih)

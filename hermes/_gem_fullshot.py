import uiautomation as auto, win32gui, win32con, time
from PIL import ImageGrab
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
W=right-left; H=bottom-top
# full window screenshot
img=ImageGrab.grab(bbox=(left,top,right,bottom))
img.save(r"D:\AIComposer\hermes\gem_full.png")
print("saved gem_full.png", W, H)
# The response likely is in the right ~60% . Let's also produce right 70% crop at full height
img.crop((left+int(W*0.30), top+80, right, bottom-40)).save(r"D:\AIComposer\hermes\gem_resp.png")
print("saved gem_resp.png", int(W*0.70), H-120)

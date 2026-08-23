import uiautomation as auto, win32gui, win32con, time
from PIL import ImageGrab
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.8)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
print("window rect", left,top,right,bottom)
img=ImageGrab.grab(bbox=(left,top,right,bottom))
img.save(r"D:\AIComposer\hermes\gem_now.png")
print("saved", img.size)
# also save left half (chat pane) crop
W=img.width; H=img.height
img.crop((0,0,W//2,H)).save(r"D:\AIComposer\hermes\gem_left.png")
print("saved left half", W//2, H)

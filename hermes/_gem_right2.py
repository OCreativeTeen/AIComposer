import uiautomation as auto, win32gui, win32con, time, ctypes
from PIL import ImageGrab
USER32=ctypes.windll.user32
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
W=right-left; H=bottom-top
# fresh right pane screenshot
img=ImageGrab.grab(bbox=(left+W//2, top, right, bottom))
img.save(r"D:\AIComposer\hermes\gem_right.png")
print("saved gem_right.png", W//2, H)

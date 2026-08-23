import uiautomation as auto, win32gui, win32con, time, ctypes
from PIL import ImageGrab
USER32=ctypes.windll.user32
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.8)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
W=right-left; H=bottom-top
# hover over the response card (right-ish, middle vertical)
USER32.SetCursorPos(left + int(W*0.75), top + int(H*0.5)); time.sleep(1.5)
img=ImageGrab.grab(bbox=(left,top,right,bottom))
img.crop((W//2, 0, W, H)).save(r"D:\AIComposer\hermes\gem_right.png")
print("saved right pane after hover", W//2, H)

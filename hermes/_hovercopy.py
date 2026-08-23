import uiautomation as auto, win32gui, win32con, time, ctypes
from PIL import ImageGrab
USER32=ctypes.windll.user32
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
# hover target: full coords (left+1628, top+250)
hx=left+1628; hy=top+250
print("hovering at", hx, hy)
USER32.SetCursorPos(hx, hy); time.sleep(2.0)
img=ImageGrab.grab(bbox=(hx-120, hy-60, hx+120, hy+60))
img.save(r"D:\AIComposer\hermes\_hovercopy.png")
print("saved _hovercopy.png", img.width, img.height)

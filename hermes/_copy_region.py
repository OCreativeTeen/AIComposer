import uiautomation as auto, win32gui, win32con, time
from PIL import ImageGrab
import cv2, numpy as np
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
W=right-left; H=bottom-top
# response card copy icon: vision said right-pane (431,486). Right pane screen origin x = left+W//2
# Tight crop around it: right-pane x 360..560 -> screen 1720+360 .. 1720+560
# screen x range: left+W//2+360 .. left+W//2+560 ; y 420..560
rx0 = left + W//2 + 340
rx1 = left + W//2 + 600
ry0 = top + 420
ry1 = top + 560
img=ImageGrab.grab(bbox=(rx0,ry0,rx1,ry1))
img.save(r"D:\AIComposer\hermes\_copy_region.png")
print("saved _copy_region.png", img.width, img.height, "screen bbox", (rx0,ry0,rx1,ry1))

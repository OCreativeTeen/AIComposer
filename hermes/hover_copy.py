import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
from PIL import ImageGrab
h=395266
wf_lib.activate(h,0.8)
u=ctypes.windll.user32
# hover over code block top-right to reveal copy button: physical (970,470)
u.SetCursorPos(970,470); time.sleep(1.0)
r=wf_lib.ctl(h).BoundingRectangle
im=ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom))
im.crop((600,400,1100,900)).save('hermes/codeblock_hover.png')
print("saved hermes/codeblock_hover.png")

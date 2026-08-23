import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
from PIL import ImageGrab
h=395266
wf_lib.activate(h,0.8)
u=ctypes.windll.user32
u.SetCursorPos(689,849); time.sleep(1.0)
r=wf_lib.ctl(h).BoundingRectangle
im=ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom))
im.crop((550,700,1200,1000)).save('hermes/copybtn_hover.png')
print("saved")

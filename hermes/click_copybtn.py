import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
import pyperclip
h=395266
wf_lib.activate(h,0.8)
u=ctypes.windll.user32
# copy button physical: image(1670,490) -> window at (-11,-11) => physical (1659,479)
cx,cy = 1659, 479
u.SetCursorPos(cx,cy); time.sleep(0.8)
# screenshot around button to confirm
from PIL import ImageGrab
r=wf_lib.ctl(h).BoundingRectangle
ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom)).crop((1550,420,1750,560)).save('hermes/btn_check.png')
u.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); u.mouse_event(0x0004,0,0,0,0); time.sleep(0.8)
txt=pyperclip.paste()
open('hermes/clip_after_btn.txt','w',encoding='utf-8').write(txt)
print("CLIP len", len(txt), "caption count", txt.count('"caption"'), "actor", txt.count('"actor"'))
print("startswith prompt?", txt.startswith("You are a psychological"))
print("tail 200:", txt[-200:])

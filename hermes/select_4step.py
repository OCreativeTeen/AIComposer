import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
from PIL import ImageGrab
import pyperclip
detail_hwnd=198900
u=ctypes.windll.user32
VK_DOWN=0x28; VK_RETURN=0x0D
def keybd(vk,dn,up):
    u.keybd_event(vk,0,0,0); time.sleep(dn); u.keybd_event(vk,0,2,0); time.sleep(up)
wf_lib.activate(detail_hwnd,0.8)
# list should be open from previous click; if not, click to open
# press Down 5 times to reach 4 Step Story (index 5)
for i in range(5):
    keybd(VK_DOWN,0.12,0.3)
    time.sleep(0.2)
time.sleep(0.3)
keybd(VK_RETURN,0.1,0.4)
time.sleep(0.8)
txt=pyperclip.paste()
print("CLIP len", len(txt))
print("has 4 scenes:", 'has 4 scene' in txt.lower() or 'has 4 scene' in txt)
print("--- first 250 ---")
print(txt[:250])
# screenshot to confirm selection
r=wf_lib.ctl(detail_hwnd).BoundingRectangle
ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom)).save('hermes/after_4step.png')

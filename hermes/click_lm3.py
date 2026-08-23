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
# close any open dropdown first via Escape
keybd(0x1B,0.1,0.3)
# click 选LM提示 combobox higher: y=265
wf_lib.click(detail_hwnd, 1289, 265, pre=0.5)
time.sleep(0.9)
r=wf_lib.ctl(detail_hwnd).BoundingRectangle
ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom)).save('hermes/lm_try3.png')
print("clicked (1289,265); saved lm_try3.png")

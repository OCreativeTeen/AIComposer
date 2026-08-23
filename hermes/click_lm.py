import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
from PIL import ImageGrab
detail_hwnd=198900
u=ctypes.windll.user32
VK_DOWN=0x28; VK_RETURN=0x0D
def keybd(vk,dn,up):
    u.keybd_event(vk,0,0,0); time.sleep(dn); u.keybd_event(vk,0,2,0); time.sleep(up)
wf_lib.activate(detail_hwnd,0.8)
# click 选LM提示 combobox at physical (1289,295)
wf_lib.click(detail_hwnd, 1289, 295, pre=0.6)
time.sleep(0.9)
r=wf_lib.ctl(detail_hwnd).BoundingRectangle
im=ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom))
im.save('hermes/lm_open.png')
print("clicked (1289,295); saved hermes/lm_open.png")

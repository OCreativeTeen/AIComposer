import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
from PIL import ImageGrab
detail_hwnd=198900
u=ctypes.windll.user32
VK_DOWN=0x28; VK_RETURN=0x0D; VK_MENU=0x12
def keybd(vk,dn,up):
    u.keybd_event(vk,0,0,0); time.sleep(dn); u.keybd_event(vk,0,2,0); time.sleep(up)
wf_lib.activate(detail_hwnd,0.8)
# click combobox at physical (1216,325)
wf_lib.click(detail_hwnd, 1216, 325, pre=0.6)
time.sleep(0.9)
r=wf_lib.ctl(detail_hwnd).BoundingRectangle
im=ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom))
im.save('hermes/after_combo_click.png')
print("clicked (1216,325); screenshot saved")

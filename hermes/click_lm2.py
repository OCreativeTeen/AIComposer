import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
from PIL import ImageGrab
detail_hwnd=198900
u=ctypes.windll.user32
wf_lib.activate(detail_hwnd,0.8)
# click near the right arrow of the combobox
wf_lib.click(detail_hwnd, 1385, 295, pre=0.5)
time.sleep(0.9)
r=wf_lib.ctl(detail_hwnd).BoundingRectangle
im=ImageGrab.grab(bbox=(r.left,r.top,r.right,r.bottom))
im.save('hermes/lm_open2.png')
print("clicked arrow (1385,295); saved")
# Now try keyboard: Alt+Down then Down x5 Enter (focus should be on combobox now)
VK_DOWN=0x28; VK_RETURN=0x0D; VK_MENU=0x12
def keybd(vk,dn,up):
    u.keybd_event(vk,0,0,0); time.sleep(dn); u.keybd_event(vk,0,2,0); time.sleep(up)
keybd(VK_MENU,0.08,0.05); keybd(VK_DOWN,0.08,0.05); time.sleep(0.7)
for i in range(5):
    keybd(VK_DOWN,0.12,0.3)
time.sleep(0.3)
keybd(VK_RETURN,0.1,0.4)
time.sleep(0.6)
import pyperclip
txt=pyperclip.paste()
print("CLIP len", len(txt), "has4scenes", 'has 4 scene' in txt.lower())
r2=wf_lib.ctl(detail_hwnd).BoundingRectangle
ImageGrab.grab(bbox=(r2.left,r2.top,r2.right,r2.bottom)).save('hermes/lm_after_sel.png')

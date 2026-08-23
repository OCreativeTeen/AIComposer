import sys; sys.path.insert(0, 'hermes')
import time, ctypes, uiautomation as auto, wf_lib
import pyperclip
from PIL import ImageGrab
detail_hwnd = 198900
u = ctypes.windll.user32
VK_DOWN = 0x28; VK_RETURN = 0x0D; VK_MENU = 0x12
def keybd(vk, dn, up):
    u.keybd_event(vk, 0, 0, 0); time.sleep(dn); u.keybd_event(vk, 0, 2, 0); time.sleep(up)
wf_lib.activate(detail_hwnd, 0.8)
wf_lib.click(detail_hwnd, 730, 330, pre=0.6)
time.sleep(0.9)
keybd(VK_MENU, 0.08, 0.05); keybd(VK_DOWN, 0.08, 0.05); time.sleep(0.7)
r = wf_lib.ctl(detail_hwnd).BoundingRectangle
for i in range(6):
    im = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
    im.save(f'hermes/dd_after_{i}.png')
    keybd(VK_DOWN, 0.12, 0.30)
    time.sleep(0.2)
keybd(VK_RETURN, 0.1, 0.4)
time.sleep(0.6)
txt = pyperclip.paste()
print("FINAL CLIP len", len(txt), "has4scenes", 'has 4 scene' in txt.lower())
print(txt[:200])

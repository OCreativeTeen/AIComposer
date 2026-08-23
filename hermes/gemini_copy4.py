import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
import pyperclip
h=395266
wf_lib.activate(h,0.8)
u=ctypes.windll.user32
# click deep inside response body: image (500,700) -> physical (-11+500, -11+700) = (489,689)
u.SetCursorPos(489,689); time.sleep(0.3)
u.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); u.mouse_event(0x0004,0,0,0,0); time.sleep(0.6)
def ctrl_key(vk):
    u.keybd_event(0x11,0,0,0); time.sleep(0.06)
    u.keybd_event(vk,0,0,0); time.sleep(0.1); u.keybd_event(vk,0,2,0)
    time.sleep(0.06); u.keybd_event(0x11,0,2,0); time.sleep(0.15)
ctrl_key(0x41); time.sleep(0.3)
# Try clipboard read BEFORE copy too
before=pyperclip.paste()
ctrl_key(0x56); time.sleep(1.0)
txt=pyperclip.paste()
open('hermes/clip_raw.txt','w',encoding='utf-8').write(txt)
print("before len", len(before), "after len", len(txt))
print("caption count", txt.count('"caption"'), "actor count", txt.count('"actor"'))
print("startswith prompt?", txt.startswith("You are a psychological"))
print("tail 300:", repr(txt[-300:]))

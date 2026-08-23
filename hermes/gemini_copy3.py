import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
import pyperclip, re
h=395266
wf_lib.activate(h,0.8)
u=ctypes.windll.user32
# click in response text region again, then select-all + copy
u.SetCursorPos(289,339); time.sleep(0.3)
u.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); u.mouse_event(0x0004,0,0,0,0); time.sleep(0.5)
def ctrl_key(vk):
    u.keybd_event(0x11,0,0,0); time.sleep(0.06)
    u.keybd_event(vk,0,0,0); time.sleep(0.1); u.keybd_event(vk,0,2,0)
    time.sleep(0.06); u.keybd_event(0x11,0,2,0); time.sleep(0.15)
ctrl_key(0x41); time.sleep(0.3); ctrl_key(0x56); time.sleep(1.0)
txt=pyperclip.paste()
print("CLIP len", len(txt))
print("caption count:", txt.count('"caption"'))
print("actor count:", txt.count('"actor"'))
print("--- TAIL 600 ---")
print(txt[-600:])

import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
import pyperclip
h=395266
wf_lib.activate(h,0.8)
u=ctypes.windll.user32
# Click in the response text region (left window). Physical coords:
# window at (-11,-11). Left window spans image x 0..1730 => physical x -11..1719
# Response text around image x=300,y=350 => physical (289, 339)
cx, cy = 289, 339
u.SetCursorPos(cx, cy); time.sleep(0.3)
u.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); u.mouse_event(0x0004,0,0,0,0); time.sleep(0.5)
def ctrl_key(vk):
    u.keybd_event(0x11,0,0,0); time.sleep(0.06)
    u.keybd_event(vk,0,0,0); time.sleep(0.1); u.keybd_event(vk,0,2,0)
    time.sleep(0.06); u.keybd_event(0x11,0,2,0); time.sleep(0.15)
ctrl_key(0x41)
time.sleep(0.3)
ctrl_key(0x56)  # C
time.sleep(1.0)
txt=pyperclip.paste()
print("CLIP len", len(txt))
print("starts with prompt?", txt.startswith("You are a psychological"))
import re
m=re.search(r'\[.*\]', txt, re.DOTALL)
print("array match len", len(m.group(0)) if m else 0)
print("--- preview 200 ---")
print(txt[:200])

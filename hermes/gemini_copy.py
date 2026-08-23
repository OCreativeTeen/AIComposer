import sys; sys.path.insert(0,'hermes')
import time, ctypes, uiautomation as auto, wf_lib
import pyperclip
h=395266
wf_lib.activate(h,0.8)
u=ctypes.windll.user32
# click a neutral area in the response (left window main area, around x=400,y=600 physical)
u.SetCursorPos(400,600); time.sleep(0.3)
u.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); u.mouse_event(0x0004,0,0,0,0); time.sleep(0.4)
# Ctrl+A then Ctrl+C
def ctrl_key(vk):
    u.keybd_event(0x11,0,0,0); time.sleep(0.05)
    u.keybd_event(vk,0,0,0); time.sleep(0.08); u.keybd_event(vk,0,2,0)
    time.sleep(0.05); u.keybd_event(0x11,0,2,0); time.sleep(0.15)
ctrl_key(0x41)  # A
time.sleep(0.3)
ctrl_key(0x56)  # C (copy)
time.sleep(0.8)
txt=pyperclip.paste()
print("CLIP len", len(txt))
print("has '[' + 'caption':", ('[' in txt and 'caption' in txt))
import re, json
# extract first JSON array
m=re.search(r'\[.*\]', txt, re.DOTALL)
if m:
    print("array len", len(m.group(0)))
    try:
        arr=json.loads(m.group(0))
        print("PARSED scenes:", len(arr))
    except Exception as e:
        print("parse err", e)
print("--- preview 400 ---")
print(txt[:400])

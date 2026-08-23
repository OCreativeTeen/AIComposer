import uiautomation as auto, win32gui, win32process, ctypes, time
USER32=ctypes.windll.user32
# open notebooklm in the ocreativeteen (Gemini) window 0x70494 by driving its address bar
hwnd=0x70494
w=auto.ControlFromHandle(hwnd); w.SetActive(); time.sleep(1.0)
# address bar
addr=None
for t,d in auto.WalkControl(w, maxDepth=14):
    if t.ControlTypeName=='EditControl' and (t.Name or '').strip()=='Address and search bar':
        addr=t; break
if not addr: print("no addr bar"); raise SystemExit
addr.SetFocus(); time.sleep(0.5)
auto.SendKeys('{Ctrl}a'); auto.SendKeys('https://notebooklm.google.com/'); time.sleep(0.5)
auto.SendKeys('{Enter}')
print("navigated ocreativeteen window to notebooklm.google.com")
time.sleep(4)
# report resulting url + account
for t,d in auto.WalkControl(w, maxDepth=14):
    if t.ControlTypeName=='EditControl' and (t.Name or '').strip()=='Address and search bar':
        print("URL now:", t.GetValuePattern().Value)
import re
for t,d in auto.WalkControl(w, maxDepth=30):
    n=(t.Name or '').strip()
    m=re.search(r'\(([\w.]+@[\w.]+)\)', n)
    if m and 'Account' in n:
        print("account:", m.group(1))

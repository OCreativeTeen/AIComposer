import uiautomation as auto, win32gui, win32process, psutil, re
def account_of(hwnd):
    w=auto.ControlFromHandle(hwnd)
    # google account button text like 'Google Account: Home Fun (myhomefun@gmail.com)'
    for t,d in auto.WalkControl(w, maxDepth=30):
        n=(t.Name or '').strip()
        m=re.search(r'\(([\w.]+@[\w.]+)\)', n)
        if m and 'Account' in n:
            return m.group(1)
    return None
for h in (0xe055e, 0x450200, 0x3b0782):
    print(hex(h), "account:", account_of(h))

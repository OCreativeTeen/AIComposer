import time, uiautomation as auto, win32gui, win32con, ctypes
from PIL import ImageGrab
USER32 = ctypes.windll.user32

def find_root():
    for w in auto.GetRootControl().GetChildren():
        nm=w.Name.strip()
        if "AIComposer" in nm and "YT 工具" in nm: return w.NativeWindowHandle,nm
    return None,None
def find_detail():
    rhwnd,_=find_root()
    if not rhwnd: return None,None
    root=auto.ControlFromHandle(rhwnd)
    for c,depth in auto.WalkControl(root,maxDepth=3):
        hw=c.NativeWindowHandle; nm=c.Name.strip()
        if hw and ("摘要" in nm or "拖入" in nm): return hw,nm
    return None,None

hwnd,nm=find_detail()
print("detail",hex(hwnd) if hwnd else None)
if win32gui.IsIconic(hwnd): win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except Exception as e: print("fg",e)
time.sleep(1.2)
ctl=auto.ControlFromHandle(hwnd); r=ctl.BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
print("rect",left,top,right,bottom)
img=ImageGrab.grab(bbox=(left,top,right,bottom))
img.save(r"D:\AIComposer\hermes\detail_now.png")
print("saved", img.size)

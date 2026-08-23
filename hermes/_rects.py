import time, uiautomation as auto, win32gui, win32con, ctypes
from PIL import ImageGrab
USER32=ctypes.windll.user32
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
rhwnd,rnm=find_root(); dhwnd,dnm=find_detail()
print("ROOT", hex(rhwnd) if rhwnd else None, rnm)
print("DETAIL", hex(dhwnd) if dhwnd else None, dnm)
rr=auto.ControlFromHandle(rhwnd).BoundingRectangle
dr=auto.ControlFromHandle(dhwnd).BoundingRectangle
print("ROOT rect:", (rr.left,rr.top,rr.right,rr.bottom))
print("DETAIL rect:", (dr.left,dr.top,dr.right,dr.bottom))
# Is detail a child of root? check parent
# screenshot the ROOT region
if win32gui.IsIconic(rhwnd): win32gui.ShowWindow(rhwnd,win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(rhwnd)
except Exception as e: print("fg",e)
time.sleep(1.2)
img=ImageGrab.grab(bbox=(rr.left,rr.top,rr.right,rr.bottom))
img.save(r"D:\AIComposer\hermes\root_now.png")
print("root saved", img.size)
# also screenshot detail region
img2=ImageGrab.grab(bbox=(dr.left,dr.top,dr.right,dr.bottom))
img2.save(r"D:\AIComposer\hermes\detail_now.png")
print("detail saved", img2.size)

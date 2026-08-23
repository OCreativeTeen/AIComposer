import numpy as np, cv2, os, time, uiautomation as auto, win32gui, win32con, ctypes
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
        hw=c.NativeWindowHandle; # careful
        return None
    return None,None

# reuse
sys_path=r"D:\AIComposer\hermes"
import sys
sys.path.insert(0,sys_path)
import wf_lib as W
hwnd,_=W.find_detail_hwnd()
if win32gui.IsIconic(hwnd): win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except Exception: pass
time.sleep(1.0)
r=W.phys_rect(hwnd)
left,top,right,bottom=r
img=ImageGrab.grab(bbox=(left,top,right,bottom))
im=np.array(img)[:,:,::-1]  # to bgr
H,Wd,_=im.shape
print("size",Wd,H)
# crop action row band generously and save as zoomable
for (ys,ye) in [(560,660),(580,650),(600,660),(550,670)]:
    crop=im[ys:ye+1,:].copy()
    cv2.imwrite(f"D:/AIComposer/hermes/_row_{ys}_{ye}.png", crop)
    print(f"saved _row_{ys}_{ye}.png  {crop.shape[1]}x{crop.shape[0]}")

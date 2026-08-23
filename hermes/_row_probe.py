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
        hw=c.NativeWindowHandle; nm=c.Name.strip()
        if hw and ("摘要" in nm or "拖入" in nm): return hw,nm
    return None,None
hwnd,_=find_detail()
if win32gui.IsIconic(hwnd): win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except Exception: pass
time.sleep(1.0)
ctl=auto.ControlFromHandle(hwnd); r=ctl.BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
img=ImageGrab.grab(bbox=(left,top,right,bottom))
im=cv2.imread(r"D:\AIComposer\hermes\detail_now.png")
H,W,_=im.shape
# inspect a few candidate bands by horizontal edge counts and vertical gaps
for ys,ye in [(590,640),(600,650),(560,640),(580,630)]:
    band=im[ys:ye+1,:]
    g=cv2.cvtColor(band,cv2.COLOR_BGR2GRAY)
    e=cv2.Canny(g,25,120)
    colsum=e.sum(axis=0)
    # find columns that are vertical edges (high) -> these are button borders/gaps
    colthr=max(1,colsum.max()*0.3)
    seg_gap=[x for x in range(W) if colsum[x]>colthr]
    # cluster into segments
    if not seg_gap: 
        print(f"band {ys}-{ye}: no edges"); continue
    segs=[]; gs=seg_gap[0]; gp=seg_gap[0]
    for x in seg_gap[1:]:
        if x-gp>10: segs.append((gs,gp)); gs=x
        gp=x
    segs.append((gs,gp))
    # window centers between consecutive gap-segments = button centers
    centers=[]
    for i in range(len(segs)-1):
        a=segs[i][1]; b=segs[i+1][0]
        if (b-a) > 30:
            centers.append((a+b)//2)
    print(f"band {ys}-{ye}: yc={(ys+ye)//2}  button x-centers={centers}")

import numpy as np, cv2, os, time, uiautomation as auto, win32gui, win32con, ctypes

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
if win32gui.IsIconic(hwnd): win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except Exception: pass
time.sleep(1.0)
ctl=auto.ControlFromHandle(hwnd); r=ctl.BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
from PIL import ImageGrab
img=ImageGrab.grab(bbox=(left,top,right,bottom))
img.save(r"D:\AIComposer\hermes\detail_now.png")
im=cv2.imread(r"D:\AIComposer\hermes\detail_now.png")
H,W,_=im.shape

# Action row band known ~ y 545..600 (center ~580). Crop it.
ys,ye=545,600
band=im[ys:ye+1,:].copy()
bg=cv2.cvtColor(band,cv2.COLOR_BGR2GRAY)
edges=cv2.Canny(bg,25,120)
# column projection to find vertical gaps between buttons
colsum=edges.sum(axis=0)
colthr=max(1, colsum.max()*0.25)
gap=[x for x in range(W) if colsum[x]>colthr]
# boundaries of buttons = between gap clusters
bnds=[]; gs=gap[0]; gp=gap[0]
for x in gap[1:]:
    if x-gp>8: bnds.append((gs,gp)); gs=x
    gp=x
bnds.append((gs,gp))
# keep segments that look like buttons (width 60..200) and are not full-width dividers
btns=[]
for a,b2 in bnds:
    w=b2-a
    if 50 < w < 220:
        btns.append((a,b2))
# merge adjacent close segments? The button border produces 2-3 gap clusters per button.
# Simpler: cluster segments by gap>30 px between consecutive segment centers
centers=[((a+b2)//2) for a,b2 in btns]
# merge centers closer than 40px (same button's left/right border)
merged=[]
for c in sorted(centers):
    if merged and c-merged[-1][1]<40:
        merged[-1]=(merged[-1][0],c)
    else:
        merged.append((c,c))
print("=== detected button x-centers (window coords) ===")
os.makedirs(r"D:\AIComposer\hermes\btn_crops",exist_ok=True)
crops=[]
for i,(c0,c1) in enumerate(merged):
    cx=(c0+c1)//2
    x0=max(0,cx-70); x1=min(W,cx+70)
    crop=band[5:55, x0:x1]
    p=rf"D:\AIComposer\hermes\btn_crops\row_{i}.png"
    cv2.imwrite(p,crop)
    crops.append((cx,p))
    print(f"  idx={i} x={cx} crop={p}")
print("row crop image y-center in full image =", (ys+ye)//2)

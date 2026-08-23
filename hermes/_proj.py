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
print("detail",hex(hwnd) if hwnd else None)
if win32gui.IsIconic(hwnd): win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except Exception as e: print("fg",e)
time.sleep(1.0)
ctl=auto.ControlFromHandle(hwnd); r=ctl.BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
from PIL import ImageGrab
img=ImageGrab.grab(bbox=(left,top,right,bottom)); W,H=img.width,img.height
img.save(r"D:\AIComposer\hermes\detail_now.png")
im=cv2.imread(r"D:\AIComposer\hermes\detail_now.png")
gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
edges=cv2.Canny(gray,15,100)
# row projection: count edge pixels per row
rowsum=edges.sum(axis=1)
# find peaks (rows with many edge pixels) - the action row band
thr=rowsum.max()*0.15
peak_rows=[y for y in range(H) if rowsum[y]>thr]
print("max row edge count:", int(rowsum.max()), "thr:", thr)
# cluster consecutive rows into bands
bands=[]
if peak_rows:
    start=peak_rows[0]; prev=peak_rows[0]
    for y in peak_rows[1:]:
        if y-prev>3: bands.append((start,prev)); start=y
        prev=y
    bands.append((start,prev))
print("=== edge bands (y_start,y_end) ===")
for b in bands: print("  ",b, "height",b[1]-b[0]+1)

# For each band, find vertical gaps (columns with few edge px) to split buttons
for (ys,ye) in bands:
    # column projection within band
    colsum=edges[ys:ye+1,:].sum(axis=0)
    colthr=colsum.max()*0.2
    # columns that are "inside" a button = low edge (button interior), gaps = high edge
    # Instead: button centers = local minima of colsum spaced out
    # Find gaps: cols where colsum > colthr (vertical edges between/around buttons)
    gap_cols=[x for x in range(W) if colsum[x]>colthr]
    if gap_cols:
        # boundaries
        bnds=[]; gs=gap_cols[0]; gp=gap_cols[0]
        for x in gap_cols[1:]:
            if x-gp>5: bnds.append((gs,gp)); gs=x
            gp=x
        bnds.append((gs,gp))
        centers=[]
        for (a,b2) in bnds:
            # skip full-width (the whole row is an edge only if band is a divider)
            if b2-a > W*0.6: continue
            centers.append(((a+b2)//2, (ys+ye)//2))
        if centers:
            print(f"\nBand y={ys}-{ye}: buttons at ->")
            for cx,cy in sorted(centers):
                print(f"   center=({cx},{cy})")

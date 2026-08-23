import numpy as np, cv2, os, time, uiautomation as auto, win32gui, win32con, ctypes
from collections import defaultdict

USER32 = ctypes.windll.user32

def find_root():
    for w in auto.GetRootControl().GetChildren():
        nm = w.Name.strip()
        if "AIComposer" in nm and "YT 工具" in nm:
            return w.NativeWindowHandle, nm
    return None, None

def find_detail():
    rhwnd,_ = find_root()
    if not rhwnd: return None,None
    root = auto.ControlFromHandle(rhwnd)
    for c,depth in auto.WalkControl(root, maxDepth=3):
        hw=c.NativeWindowHandle; nm=c.Name.strip()
        if hw and ("摘要" in nm or "拖入" in nm): return hw,nm
    return None,None

hwnd, nm = find_detail()
print("detail", hex(hwnd) if hwnd else None, nm)
if win32gui.IsIconic(hwnd): win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except Exception as e: print("fg warn", e)
time.sleep(1.2)
ctl = auto.ControlFromHandle(hwnd)
r = ctl.BoundingRectangle
left, top, right, bottom = r.left, r.top, r.right, r.bottom
print("rect", left, top, right, bottom)
from PIL import ImageGrab
img = ImageGrab.grab(bbox=(left, top, right, bottom))
W,H = img.width, img.height
img.save(r"D:\AIComposer\hermes\detail_now.png")
print("saved full", W,H)

# Detect the action row: scan candidate y bands for a run of ~7 uniformly-sized rects sharing y
gray = cv2.cvtColor(cv2.imread(r"D:\AIComposer\hermes\detail_now.png"), cv2.COLOR_BGR2GRAY)
# Canny with low threshold
edges = cv2.dilate(cv2.Canny(gray, 15, 100), np.ones((2,2),np.uint8))
cnts,_ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
allc=[]
for c in cnts:
    x,y,w,h = cv2.boundingRect(c)
    if 50 < w < 220 and 16 < h < 55 and cv2.contourArea(c) > 150:
        allc.append((x+w//2, y+h//2, w, h))
# group by y
rows = defaultdict(list)
for cx,cy,w,h in allc:
    rows[round(cy/6)*6].append((cx,cy,w,h))
# pick the row with the most members (the action row)
best = max(rows.items(), key=lambda kv: len(kv[1])) if rows else (None,[])
print("\n=== best action row y=", best[0], "members=", len(best[1]))
rowmembers = sorted(best[1], key=lambda t:t[0])
for cx,cy,w,h in rowmembers:
    print(f"  x={cx:4d} y={cy:4d} size=({w}x{h})")

# crop each button for labeling
os.makedirs(r"D:\AIComposer\hermes\btn_crops", exist_ok=True)
im = cv2.imread(r"D:\AIComposer\hermes\detail_now.png")
labels=[]
for i,(cx,cy,w,h) in enumerate(rowmembers):
    x0=max(0,cx-80); x1=min(W,cx+80); y0=max(0,cy-30); y1=min(H,cy+30)
    crop = im[y0:y1, x0:x1]
    p = rf"D:\AIComposer\hermes\btn_crops\btn_{i}.png"
    cv2.imwrite(p, crop)
    labels.append(p)
print("\ncrops:", labels)

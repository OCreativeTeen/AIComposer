import uiautomation as auto, win32gui, win32con, time, ctypes
from collections import Counter
USER32=ctypes.windll.user32
panel=auto.WindowControl(searchDepth=1, Name="分镜 / Scene")
print("panel exists:", panel.Exists(2,1))
r=panel.BoundingRectangle
print("panel rect:", (r.left,r.top,r.right,r.bottom))
if win32gui.IsIconic(panel.NativeWindowHandle): win32gui.ShowWindow(panel.NativeWindowHandle, win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(panel.NativeWindowHandle)
except Exception: pass
time.sleep(0.5)
print("\n=== control census (depth up to 12) ===")
c=Counter()
named=[]
for ctrl,depth in auto.WalkControl(panel, maxDepth=12):
    t=ctrl.ControlTypeName
    c[t]+=1
    nm=ctrl.Name.strip()
    if nm:
        rr=ctrl.BoundingRectangle
        named.append((depth,t,nm,rr.left,rr.top,rr.right,rr.bottom))
print(c.most_common())
print("\n=== named controls ===")
for depth,t,nm,l,tp,rr,bt in sorted(named, key=lambda x:(x[3],x[4])):
    print(f"  d{depth} {t} {nm!r} rect=({l},{tp},{rr},{bt})")

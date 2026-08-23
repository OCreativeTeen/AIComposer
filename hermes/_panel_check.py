import sys, time, re, win32gui, uiautomation as auto
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W

dhwnd,_=W.find_detail_hwnd()
print("detail hwnd", hex(dhwnd))
# look for 分镜 panel among children (child toplevel)
rhwnd,_=W.find_root_hwnd()
root=auto.ControlFromHandle(rhwnd)
found=[]
for c,depth in auto.WalkControl(root, maxDepth=5):
    hw=c.NativeWindowHandle; nm=c.Name.strip()
    if hw and ("分镜" in nm or "Scene" in nm):
        r=c.BoundingRectangle
        print("  PANEL d%d hw=%s %r rect=(%d,%d,%d,%d)"%(depth,hex(hw),nm,r.left,r.top,r.right,r.bottom))
        found.append(hw)
print("panels found:", len(found))
# also list TkChild buttons near bottom (the 分镜 panel buttons y~1240 region) under detail
print("\n--- detail children TkChild (buttons) ---")
def h(r): return r[3]-r[1]
def w(r): return r[2]-r[0]
kids=[]
def enum(hwnd,_):
    rect=win32gui.GetWindowRect(hwnd); cls=win32gui.GetClassName(hwnd)
    kids.append((hwnd,cls,rect))
win32gui.EnumChildWindows(dhwnd, enum, None)
btns=[k for k in kids if k[1]=='TkChild' and 20<h(k[2])<120 and 20<w(k[2])<400]
for hw,cls,rect in sorted(btns, key=lambda k:(k[2][1],k[2][0])):
    print(f"  hw={hex(hw)} rect={rect} size=({w(rect)}x{h(rect)})")

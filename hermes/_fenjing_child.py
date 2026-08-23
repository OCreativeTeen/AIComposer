import win32gui, uiautomation as auto, ctypes
USER32=ctypes.windll.user32
panel=auto.WindowControl(searchDepth=1, Name="分镜 / Scene")
phw=panel.NativeWindowHandle
print("panel hwnd", hex(phw), "rect", win32gui.GetWindowRect(phw))
# enumerate child TkChild windows with rects
kids=[]
def enum(hwnd,_):
    rect=win32gui.GetWindowRect(hwnd); cls=win32gui.GetClassName(hwnd)
    kids.append((hwnd,cls,rect))
win32gui.EnumChildWindows(phw, enum, None)
print("total children:", len(kids))
def h(r): return r[3]-r[1]
def w(r): return r[2]-r[0]
# Everything
for hw,cls,rect in sorted(kids, key=lambda k:(k[2][1],k[2][0])):
    if cls=='TkChild':
        print(f"  hw={hex(hw)} rect={rect} size=({w(rect)}x{h(rect)})")

"""Locate the 分镜 panel's scene_content textarea (TkChild) and report a safe
click point (physical, relative to panel UIA origin)."""
import uiautomation as auto, win32gui, sys, ctypes
USER32=ctypes.windll.user32

def find_toplevel(sub):
    res=[]
    def cb(h,_):
        if win32gui.IsWindowVisible(h) and sub in win32gui.GetWindowText(h):
            res.append(h)
        return 1
    win32gui.EnumWindows(cb,None)
    return res

def main():
    hwnd=find_toplevel("分镜")[0]
    r=auto.ControlFromHandle(hwnd).BoundingRectangle
    print("panel origin(UIA):", r.left, r.top, "size", r.width(), r.height())
    # Enumerate TkChild kids; the scene_content textarea is the big one
    kids=[]
    def enum(h,_):
        kids.append((h, win32gui.GetClassName(h), win32gui.GetWindowRect(h))); return 1
    win32gui.EnumChildWindows(hwnd, enum, None)
    big=[]
    for h,cls,rect in kids:
        if cls=='TkChild':
            w,h_=rect[2]-rect[0], rect[3]-rect[1]
            if w>200 and h_>100:   # textarea-like
                big.append((rect[0]+w//2, rect[1]+h_//2, w, h_))
    print("Large TkChild textareas (center x,y,w,h), sorted by y:")
    for c in sorted(big, key=lambda k:k[1]):
        # relative to panel origin
        print(f"  screen=({c[0]},{c[1]}) rel=({c[0]-r.left},{c[1]-r.top}) size=({c[2]}x{c[3]})")

if __name__=='__main__':
    main()

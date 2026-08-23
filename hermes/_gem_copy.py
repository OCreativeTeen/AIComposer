import sys, time, re, ctypes, json
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as wfl
import uiautomation as auto, win32gui, win32con

USER32=ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN=0x0002; MOUSEEVENTF_LEFTUP=0x0004
gem_hw=0x60802
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
WW=right-left
rpx = left + WW//2
vx, vy = 431, 486
absx = rpx + vx
absy = top + vy
print("window", left,top,right,bottom, "WW", WW, "rpx", rpx)
print("clicking copy btn at screen", absx, absy)
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
ctl=auto.ControlFromHandle(gem_hw); ctl.SetActive(); time.sleep(0.5)
USER32.SetCursorPos(absx, absy); time.sleep(0.4)
USER32.mouse_event(MOUSEEVENTF_LEFTDOWN,0,0,0,0); time.sleep(0.09); USER32.mouse_event(MOUSEEVENTF_LEFTUP,0,0,0,0)
time.sleep(1.2)
clip = wfl.clip_text()
print("clip len:", len(clip))
caps = re.findall(r'"caption"\s*:\s*"([^"]{0,30})', clip)
print("caption count:", len(caps))
print("captions:", caps)
print("head 200:", clip[:200].replace(chr(10),' '))

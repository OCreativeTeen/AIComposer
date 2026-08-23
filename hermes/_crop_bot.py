import numpy as np, cv2, time, sys
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W
import win32gui, win32con
from PIL import ImageGrab
hwnd,_=W.find_detail_hwnd()
if win32gui.IsIconic(hwnd): win32gui.ShowWindow(hwnd,win32con.SW_RESTORE)
try: win32gui.SetForegroundWindow(hwnd)
except Exception: pass
time.sleep(1.0)
r=W.phys_rect(hwnd); left,top,right,bottom=r
img=ImageGrab.grab(bbox=(left,top,right,bottom))
im=np.array(img)[:,:,::-1]
H,Wd,_=im.shape
# crop lower bands
for (ys,ye) in [(640,839),(660,839),(640,780),(680,839),(700,839)]:
    crop=im[ys:ye+1,:].copy()
    cv2.imwrite(f"D:/AIComposer/hermes/_bot_{ys}_{ye}.png", crop)
    print(f"saved _bot_{ys}_{ye}.png {crop.shape[1]}x{crop.shape[0]}")

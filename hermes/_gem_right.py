import uiautomation as auto, win32gui, win32con, time
from PIL import ImageGrab
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.8)
r=auto.ControlFromHandle(gem_hw).BoundingRectangle
left,top,right,bottom=r.left,r.top,r.right,r.bottom
W=right-left; H=bottom-top
img=ImageGrab.grab(bbox=(left,top,right,bottom))
# right half = chat response area
img.crop((W//2, 0, W, H)).save(r"D:\AIComposer\hermes\gem_right.png")
print("saved right half", W//2, H)
# also check remote debugging port
import subprocess
out=subprocess.run("wmic process where \"name='chrome.exe'\" get CommandLine /format:csv", capture_output=True, text=True, shell=True).stdout
ports=set()
for line in out.splitlines():
    if "remote-debugging-port" in line:
        import re as _re
        m=_re.search(r"remote-debugging-port=(\d+)", line)
        if m: ports.add(m.group(1))
print("remote-debugging ports found:", ports)

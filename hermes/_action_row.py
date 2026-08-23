import json, ctypes, time, os
import uiautomation as auto
import pyautogui
import win32gui, win32con
import numpy as np, cv2
from PIL import ImageGrab

USER32 = ctypes.windll.user32

# Re-find detail editor by walking the live root each time (never cache across close)
def find_root():
    for w in auto.GetRootControl().GetChildren():
        nm = w.Name.strip()
        if "AIComposer" in nm and "YT 工具" in nm:
            return w.NativeWindowHandle, nm
    return None, None

def find_detail():
    rhwnd, _ = find_root()
    if not rhwnd:
        return None, None
    root = auto.ControlFromHandle(rhwnd)
    for c, depth in auto.WalkControl(root, maxDepth=3):
        hw = c.NativeWindowHandle
        nm = c.Name.strip()
        if hw and ("摘要" in nm or "拖入" in nm):
            return hw, nm
    return None, None

def bring_front(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception as e:
        print("SetForegroundWindow warn:", e)

def rect_of(hwnd):
    ctl = auto.ControlFromHandle(hwnd)
    r = ctl.BoundingRectangle
    return (r.left, r.top, r.right, r.bottom)

def edge_buttons(png_path, ymin, ymax, wmin=60, wmax=200, hmin=18, hmax=50):
    im = cv2.imread(png_path)
    H, W = im.shape[:2]
    ymin = max(0, ymin); ymax = min(H, ymax)
    roi = im[ymin:ymax, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 30, 120), np.ones((2,2), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if wmin < w < wmax and hmin < h < hmax:
            out.append((x + w//2, ymin + y + h//2, w, h))
    return out

hwnd, nm = find_detail()
print("DETAIL hwnd=", hex(hwnd) if hwnd else None, nm)
assert hwnd, "detail editor not found"
bring_front(hwnd); time.sleep(1.2)
left, top, right, bottom = rect_of(hwnd)
print("physical rect:", (left, top, right, bottom), "size", right-left, bottom-top)

os.makedirs(r"D:\AIComposer\hermes\btn_crops", exist_ok=True)
img = ImageGrab.grab(bbox=(left, top, right, bottom))
png = r"D:\AIComposer\hermes\detail_now.png"
img.save(png)
print("saved", png, img.size)

H, W = img.height, img.width
# scan full height for uniform button rows
allc = edge_buttons(png, 0, H)
print("\n=== candidate buttons (full image) ===")
for cx, cy, w, h in sorted(allc, key=lambda t: (t[1], t[0])):
    print(f"  center=({cx:4d},{cy:4d})  size=({w}x{h})")

# group by y (rows)
from collections import defaultdict
rows = defaultdict(list)
for cx, cy, w, h in allc:
    rows[round(cy/8)*8].append((cx, cy, w, h))
print("\n=== rows (y: buttons) ===")
for y in sorted(rows):
    xs = [c[0] for c in rows[y]]
    print(f"  y~{y}: x={xs}")

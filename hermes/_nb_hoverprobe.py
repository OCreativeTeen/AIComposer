import sys; sys.path.insert(0,'hermes')
from _nb_gen import find_nb
import uiautomation as auto, win32gui, time, ctypes
from PIL import ImageGrab
USER32=ctypes.windll.user32

NB_HWND=find_nb()
# find Infographic tile control
tile=None
for t,d in auto.WalkControl(auto.ControlFromHandle(NB_HWND), maxDepth=46):
    n=(t.Name or '').strip()
    if n=='Infographic' and t.ControlTypeName in ('HyperlinkControl','ButtonControl','ListItemControl','GroupControl'):
        tile=t; break
print("tile:", tile, tile.ControlTypeName if tile else None)
if tile:
    r=tile.BoundingRectangle
    print("tile rect", r.left,r.top,r.right,r.bottom)
    cx=(r.left+r.right)//2; cy=(r.top+r.bottom)//2
    # hover center first
    auto.ControlFromHandle(NB_HWND).SetActive(); time.sleep(0.5)
    USER32.SetCursorPos(cx,cy); time.sleep(2.0)  # wait for chevron
    # screenshot a region around the right edge of the tile
    ImageGrab.grab(bbox=(r.left, r.top-10, r.right+40, r.bottom+10)).save('hermes/_nb_hover.png')
    print("saved hover crop of tile at", (r.left, r.top, r.right, r.bottom))
    # also list buttons near right edge
    print("buttons near tile right edge:")
    for t2,d in auto.WalkControl(auto.ControlFromHandle(NB_HWND), maxDepth=46):
        if t2.ControlTypeName=='ButtonControl':
            rr=t2.BoundingRectangle
            if abs(rr.left - r.right) < 80 and abs(rr.top - cy) < 120:
                print("  ", repr(t2.Name), (rr.left,rr.top,rr.right,rr.bottom))

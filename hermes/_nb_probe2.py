import sys; sys.path.insert(0,'hermes')
from _nb_gen import find_nb, w, click_screen
import uiautomation as auto
import time

NB_HWND=find_nb()
print("hwnd", hex(NB_HWND))
click_screen(900,450, pre=1.2)
time.sleep(2)
print("\n--- in-page controls after chevron ---")
seen=set()
for t,d in auto.WalkControl(w(), maxDepth=46):
    n=(t.Name or '').strip()
    if n and n not in seen:
        seen.add(n)
        print(f"  [{t.ControlTypeName}] {n!r} @({t.BoundingRectangle.left},{t.BoundingRectangle.top})")

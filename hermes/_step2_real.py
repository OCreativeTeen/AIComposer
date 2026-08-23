import sys, time, re
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W

dhwnd, nm = W.find_detail_hwnd()
print("DETAIL:", hex(dhwnd) if dhwnd else None)
W.bring_front(dhwnd)
# vision: action row y=715, 场景 x=130
x, y = 130, 715
print(f"clicking 场景 at ({x},{y})...")
W.safe_click(dhwnd, x, y, pre_sleep=1.2, post_sleep=1.8)
phwnd, pnm = W.find_panel_hwnd("分镜")
print("分镜 panel:", hex(phwnd) if phwnd else None, pnm)
clip = W.clip_text()
print("clip len:", len(clip))
print("marker:", re.findall(r'has \d+ scene', clip))
print("first 120:", clip[:120].replace("\n"," "))

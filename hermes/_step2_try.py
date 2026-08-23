import sys, time, re
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W

dhwnd, nm = W.find_detail_hwnd()
print("DETAIL:", hex(dhwnd) if dhwnd else None)
W.bring_front(dhwnd)
# hypothesis from vision: action row y=612, 场景 x≈452
x, y = 452, 612
print(f"clicking 场景 at ({x},{y})...")
W.safe_click(dhwnd, x, y, pre_sleep=1.2, post_sleep=1.5)
phwnd, pnm = W.find_panel_hwnd("分镜")
print("分镜 panel:", hex(phwnd) if phwnd else None, pnm)
clip = W.clip_text()
print("clip len:", len(clip))
print("marker:", re.findall(r'has \d+ scene', clip))
print("first 100:", clip[:100].replace("\n"," "))

import sys, time, re
sys.path.insert(0, r"D:\AIComposer\hermes")
import wf_lib as W

dhwnd, nm = W.find_detail_hwnd()
print("DETAIL:", hex(dhwnd) if dhwnd else None, nm)
assert dhwnd, "no detail editor"
W.bring_front(dhwnd)

# Reference verified: action row y=580, 场景 at x=714 (window-relative, physical)
print("clicking 场景 at (714, 580)...")
ax, ay = W.safe_click(dhwnd, 714, 580, pre_sleep=1.2, post_sleep=1.5)
print("clicked at abs", ax, ay)

# Verify: 分镜 panel should now exist + clipboard should have the story prompt
phwnd, pnm = W.find_panel_hwnd("分镜")
print("分镜 panel hwnd:", hex(phwnd) if phwnd else None, pnm)
clip = W.clip_text()
print("clipboard length:", len(clip))
m = re.findall(r'has \d+ scene', clip)
print("scene-count marker:", m)
print("clipboard first 120 chars:", clip[:120].replace("\n"," "))

"""DPI-aware probe of the AIComposer 摘要 detail editor.
Import uiautomation ONLY to make this process DPI-aware (so win32gui returns
true physical screen coordinates), then locate the detail window via win32gui
and dump real TkChild button rects + a full screenshot. No uiautomation tree
walking (which filtered the window out).
"""
import json
import uiautomation as auto  # noqa: F401  (forces DPI awareness)
import win32gui
from PIL import ImageGrab

OUT_PNG = "hermes/detail_physical.png"
OUT_JSON = "hermes/detail_buttons.json"


def find_detail_hwnd():
    found = []
    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if "摘要" in t and "拖入" in t and "AIComposer" not in t:
            found.append(h)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def main():
    hw = find_detail_hwnd()
    if not hw:
        print(json.dumps({"error": "detail window not found"}))
        return
    rect = win32gui.GetWindowRect(hw)  # physical now
    img = ImageGrab.grab(bbox=rect)
    img.save(OUT_PNG)
    kids = []
    def enum(h, _):
        kids.append((h, win32gui.GetClassName(h), win32gui.GetWindowRect(h)))
    win32gui.EnumChildWindows(hw, enum, None)
    buttons = []
    for h, cls, r in kids:
        w = r[2] - r[0]; ht = r[3] - r[1]
        if cls == "TkChild" and 18 < ht < 60 and 30 < w < 520:
            buttons.append({
                "cx": r[0] + w // 2, "cy": r[1] + ht // 2,
                "x": r[0], "y": r[1], "w": w, "h": ht,
            })
    buttons.sort(key=lambda b: (b["cy"], b["cx"]))
    out = {"hwnd": hex(hw), "window_rect": list(rect),
           "png": OUT_PNG, "buttons": buttons}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"window_rect": list(rect), "png": OUT_PNG,
                      "n_buttons": len(buttons)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

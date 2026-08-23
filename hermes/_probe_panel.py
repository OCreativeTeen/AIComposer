"""Probe the 分镜 / Scene panel: dump ALL child windows with class + physical rect.
Goal: locate the 选LM提示 combobox (ttk.Combobox -> TCombobox class) and the
bottom action row (智能生成/All/NotebookLM/保存/取消) so we click ground truth.
"""
import uiautomation as auto  # noqa: F401 forces DPI awareness
import win32gui, json

def find_panel_hwnd():
    found = []
    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if "分镜" in t:
            found.append(h)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None

def main():
    hw = find_panel_hwnd()
    print("panel hwnd:", hex(hw) if hw else None)
    if not hw:
        return
    rect = win32gui.GetWindowRect(hw)
    print("panel rect:", list(rect))
    kids = []
    def enum(h, _):
        kids.append((h, win32gui.GetClassName(h),
                     win32gui.GetWindowText(h), win32gui.GetWindowRect(h)))
    win32gui.EnumChildWindows(hw, enum, None)
    rows = []
    for h, cls, txt, r in kids:
        w = r[2] - r[0]; ht = r[3] - r[1]
        rows.append((r[1] + ht // 2, r[0] + w // 2, w, ht, cls, txt.strip()))
    rows.sort()
    for cy, cx, w, ht, cls, txt in rows:
        rel_x = cx - rect[0]
        rel_y = cy - rect[1]
        print(f"rel=({rel_x:4d},{rel_y:4d}) cx={cx:4d} cy={cy:4d} w={w:3d} h={ht:2d} {cls!r} {txt!r}")

if __name__ == "__main__":
    main()

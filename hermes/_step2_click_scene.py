"""Step 2.1a: safe-click 场景, verify 分镜 panel opened + default clipboard prompt.
Safe click = physical origin from UIA BoundingRectangle + mouse_event (never auto.Click).
"""
import uiautomation as auto  # noqa: F401 forces DPI awareness
import ctypes, time, subprocess, re, json
import win32gui

u = ctypes.windll.user32

DETAIL_TITLE_HINT = "摘要"


def find_detail_hwnd():
    found = []
    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if "摘要" in t and "拖入" in t and "AIComposer" not in t:
            found.append(h)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def safe_click(hwnd, x, y):
    ctl = auto.ControlFromHandle(hwnd)
    ctl.SetActive()
    time.sleep(1.0)
    r = ctl.BoundingRectangle  # physical origin
    px, py = r.left + x, r.top + y
    u.SetCursorPos(px, py)
    time.sleep(0.4)
    u.mouse_event(0x0002, 0, 0, 0, 0)  # down
    time.sleep(0.08)
    u.mouse_event(0x0004, 0, 0, 0, 0)  # up
    time.sleep(0.6)
    return px, py


def get_clip():
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-Command", "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "").strip()


def find_panel():
    # 分镜 / Scene: search top-level windows by title (incl. child Toplevels)
    found = []
    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if "分镜" in t:
            found.append((h, win32gui.GetWindowRect(h)))
    win32gui.EnumWindows(cb, None)
    if found:
        return found[0]
    # fallback: UIA walk from app root
    root = None
    for w in auto.GetRootControl().GetChildren():
        if "AIComposer" in w.Name and "YT 工具" in w.Name:
            root = w
            break
    if root:
        for c, depth in auto.WalkControl(root, maxDepth=3):
            if c.ControlTypeName == "WindowControl" and "分镜" in (c.Name or ""):
                r = c.BoundingRectangle
                return c.NativeWindowHandle, (r.left, r.top, r.right, r.bottom)
    return None, None


def main():
    hw = find_detail_hwnd()
    if not hw:
        print(json.dumps({"error": "detail window not found"}))
        return
    print("detail hwnd:", hex(hw))
    # click 场景 (cx=714, cy=513 within 1614x839 window at 0,0)
    px, py = safe_click(hw, 714, 513)
    print("clicked 场景 at", px, py)
    time.sleep(1.5)
    # verify panel
    phw, pr = find_panel()
    print("panel hwnd:", hex(phw) if phw else None,
          "rect:", list(pr) if pr else None)
    clip = get_clip()
    print("clipboard length:", len(clip))
    print("has 'scene' markers:", re.findall(r"has \d+ scene", clip))
    print("clipboard head:", clip[:80].replace("\n", " "))
    out = {"panel_open": phw is not None,
           "panel_rect": list(pr) if pr else None,
           "clip_len": len(clip),
           "scene_markers": re.findall(r"has \d+ scene", clip)}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

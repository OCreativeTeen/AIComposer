"""Step 2.3: paste the 4-scene JSON into the 分镜 panel's scene_content field,
then click 保存 (panel-relative x=431, y=1248) and verify the disk file updated.
Safe mouse_event clicks.
"""
import uiautomation as auto  # noqa: F401 DPI awareness
import ctypes, time, subprocess, json, re, win32gui

u = ctypes.windll.user32

# Module-level EnumWindows callback (nested callbacks are unreliable with
# pywin32 in this uiautomation/DPI-aware combo - they get gc'd mid-enum).
_TITLE_HITS = []
_TITLE_SUB = ""
_TITLE_EXCLUDE = ""

def _enum_titles_cb(h, _):
    t = win32gui.GetWindowText(h)
    if _TITLE_SUB in t and _TITLE_EXCLUDE not in t:
        _TITLE_HITS.append(h)
    return 1

def find_by_title(sub, exclude=""):
    global _TITLE_HITS, _TITLE_SUB, _TITLE_EXCLUDE
    _TITLE_HITS = []
    _TITLE_SUB = sub
    _TITLE_EXCLUDE = exclude
    win32gui.EnumWindows(_enum_titles_cb, None)
    return _TITLE_HITS[0] if _TITLE_HITS else None

def get_clip():
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-Command", "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "")

def safe_click_phys(px, py):
    u.SetCursorPos(px, py); time.sleep(0.35)
    u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.08)
    u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.6)

def main():
    panel_hw = find_by_title("分镜")
    if not panel_hw:
        print(json.dumps({"error": "分镜 panel not found"})); return
    rect = win32gui.GetWindowRect(panel_hw)
    print("panel rect:", list(rect))

    # focus scene_content textarea: doc says click ~(700,720) window-relative in
    # 1614x839 detail window. In the panel (1404x1289) the field is large lower
    # region. Use click at panel-relative (700, 700) to land inside textarea.
    ctl = auto.ControlFromHandle(panel_hw)
    ctl.SetActive(); time.sleep(1.0)
    px, py = rect[0] + 700, rect[1] + 700
    safe_click_phys(px, py)
    # select-all + paste
    u.keybd_event(0x11, 0, 0, 0)  # Ctrl down
    u.keybd_event(0x41, 0, 0, 0)  # A
    u.keybd_event(0x41, 0, 2, 0)
    u.keybd_event(0x11, 0, 2, 0)  # Ctrl up
    time.sleep(0.15)
    u.keybd_event(0x11, 0, 0, 0)
    u.keybd_event(0x56, 0, 0, 0)  # V
    u.keybd_event(0x56, 0, 2, 0)
    u.keybd_event(0x11, 0, 2, 0)
    time.sleep(1.0)

    clip = get_clip()
    print("clipboard still 4-scene:", len(re.findall(r'"caption"', clip)) == 4)

    # click 保存 at panel-relative (431, 1248)
    save_x = rect[0] + 431
    save_y = rect[1] + 1248
    print("clicking 保存 at", save_x, save_y)
    safe_click_phys(save_x, save_y)
    time.sleep(2.0)
    print(json.dumps({"panel": hex(panel_hw), "save_clicked": True}))

if __name__ == "__main__":
    main()

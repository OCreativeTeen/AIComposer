"""Step 2.1b: select '4 Step Story' in 选LM提示 combobox of the 分镜 panel.
Click combobox at panel-relative (239,167) -> physical (panel.left+239, panel.top+167),
then VK_DOWN x5, VK_RETURN. Verify clipboard recopies 'has 4 scene'.
Uses safe mouse_event (never auto.Click).
"""
import uiautomation as auto  # noqa: F401 forces DPI awareness
import uiautomation as auto_mod  # the module for SendKey
import ctypes, time, subprocess, re, json, win32gui

u = ctypes.windll.user32

def find_panel_hwnd():
    found = []
    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if "分镜" in t:
            found.append(h)
    win32gui.EnumWindows(cb, None)
    return found[0] if found else None

def get_clip():
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-Command", "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "").strip()

def main():
    hw = find_panel_hwnd()
    if not hw:
        print(json.dumps({"error": "panel not found"}))
        return
    rect = win32gui.GetWindowRect(hw)
    # panel origin physical
    ox, oy = rect[0], rect[1]
    combo_x = ox + 239
    combo_y = oy + 167
    print("panel rect:", list(rect), "combobox at", combo_x, combo_y)

    # safe click on combobox
    ctl = auto.ControlFromHandle(hw)
    ctl.SetActive()
    time.sleep(1.0)
    u.SetCursorPos(combo_x, combo_y)
    time.sleep(0.4)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.5)

    # keyboard nav: Down x5, Enter
    for _ in range(5):
        auto_mod.SendKey(auto_mod.Keys.VK_DOWN)
        time.sleep(0.12)
    time.sleep(0.3)
    auto_mod.SendKey(auto_mod.Keys.VK_RETURN)
    time.sleep(1.0)

    clip = get_clip()
    markers = re.findall(r"has \d+ scene", clip)
    print("clip length:", len(clip))
    print("scene markers:", markers)
    print(json.dumps({"clip_len": len(clip), "scene_markers": markers,
                      "ok": "has 4 scene" in clip}, ensure_ascii=False))

if __name__ == "__main__":
    main()

import uiautomation as auto
import win32gui, win32process, psutil, time, sys

def chrome_top_windows():
    out = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return 1
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            name = win32gui.GetWindowText(hwnd)
            p = psutil.Process(pid); exe = p.name()
        except Exception:
            return 1
        if exe.lower() == "chrome.exe":
            out.append((hwnd, name, pid))
        return 1
    win32gui.EnumWindows(cb, None)
    return out

def activate_tab_and_url(w, tab_title_sub):
    """Click the tab whose title contains sub, then read the address bar."""
    for t, d in auto.WalkControl(w, maxDepth=12):
        if t.ControlTypeName == 'TabItemControl' and tab_title_sub in (t.Name or ''):
            try:
                t.Click()
            except Exception:
                pass
            time.sleep(1.2)
            break
    for t, d in auto.WalkControl(w, maxDepth=12):
        if t.ControlTypeName == 'EditControl' and (t.Name or '').strip() == 'Address and search bar':
            try:
                return t.GetValuePattern().Value
            except Exception:
                return "(addr read fail)"
    return "(no addr)"

def main():
    targets = sys.argv[1:] or ["Google Gemini", "Grok Imagine"]
    wins = chrome_top_windows()
    for hwnd, name, pid in wins:
        w = auto.ControlFromHandle(hwnd)
        # collect tab titles
        tabs = []
        for t, d in auto.WalkControl(w, maxDepth=12):
            if t.ControlTypeName == 'TabItemControl' and (t.Name or '').strip():
                tabs.append((t.Name or '').strip())
        for sub in targets:
            if any(sub in x for x in tabs):
                url = activate_tab_and_url(w, sub)
                print(f"hwnd={hwnd} tab~{sub!r} -> {url}")

if __name__ == "__main__":
    main()

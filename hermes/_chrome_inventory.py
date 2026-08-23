import uiautomation as auto
import win32gui, win32process, psutil

def chrome_top_windows():
    out = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return 1
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            name = win32gui.GetWindowText(hwnd)
        except Exception:
            name = ""
        try:
            p = psutil.Process(pid)
            exe = p.name()
        except Exception:
            exe = ""
        if exe.lower() == "chrome.exe":
            out.append((hwnd, name, pid))
        return 1
    win32gui.EnumWindows(cb, None)
    return out

def main():
    wins = chrome_top_windows()
    print(f"=== {len(wins)} top-level Chrome windows ===")
    for hwnd, name, pid in wins:
        print(f"\n--- hwnd={hwnd} pid={pid} title={name!r}")
        try:
            w = auto.ControlFromHandle(hwnd)
        except Exception as e:
            print("  controlfromhandle err:", e)
            continue
        # address bar
        addr = None
        for t, d in auto.WalkControl(w, maxDepth=8):
            if t.ControlTypeName == 'EditControl' and (t.Name or '').strip() == 'Address and search bar':
                try:
                    v = t.GetValuePattern().Value
                    addr = v
                except Exception:
                    pass
                break
        if addr:
            print("  URL:", addr)
        # tab titles
        tabs = []
        for t, d in auto.WalkControl(w, maxDepth=10):
            if t.ControlTypeName == 'TabItemControl':
                tn = (t.Name or '').strip()
                if tn:
                    tabs.append(tn)
        # dedupe preserving order
        seen = set(); ut = []
        for x in tabs:
            if x not in seen:
                seen.add(x); ut.append(x)
        for x in ut:
            print("  TAB:", x)

if __name__ == "__main__":
    main()

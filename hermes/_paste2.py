import uiautomation as auto
import ctypes, time, subprocess, json, re, win32gui
u = ctypes.windll.user32
_TITLE_HITS = []
_TITLE_SUB = ""
def _enum_titles_cb(h, _):
    t = win32gui.GetWindowText(h)
    if _TITLE_SUB in t:
        _TITLE_HITS.append(h)
    return 1
def find_by_title(sub):
    global _TITLE_HITS, _TITLE_SUB
    _TITLE_HITS = []
    _TITLE_SUB = sub
    win32gui.EnumWindows(_enum_titles_cb, None)
    return _TITLE_HITS[0] if _TITLE_HITS else None

def get_clip():
    r = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command","[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],capture_output=True,text=True,encoding="utf-8",errors="replace")
    return (r.stdout or "")
def safe_click_phys(px,py):
    u.SetCursorPos(px,py); time.sleep(0.35)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08)
    u.mouse_event(0x0004,0,0,0,0); time.sleep(0.6)

# MODULE-LEVEL find (proven to work)
panel_hw = find_by_title("分镜")
print("panel:", hex(panel_hw) if panel_hw else None)
if panel_hw:
    rect = win32gui.GetWindowRect(panel_hw)
    ctl = auto.ControlFromHandle(panel_hw)
    ctl.SetActive(); time.sleep(1.0)
    px, py = rect[0]+700, rect[1]+700
    safe_click_phys(px,py)
    u.keybd_event(0x11,0,0,0); u.keybd_event(0x41,0,0,0); u.keybd_event(0x41,0,2,0); u.keybd_event(0x11,0,2,0); time.sleep(0.15)
    u.keybd_event(0x11,0,0,0); u.keybd_event(0x56,0,0,0); u.keybd_event(0x56,0,2,0); u.keybd_event(0x11,0,2,0); time.sleep(1.0)
    clip=get_clip()
    print("clip 4-scene:", len(re.findall(r'"caption"',clip))==1)  # placeholder
    save_x, save_y = rect[0]+431, rect[1]+1248
    print("save at", save_x, save_y)
    safe_click_phys(save_x, save_y)
    time.sleep(2.0)
    print("done")

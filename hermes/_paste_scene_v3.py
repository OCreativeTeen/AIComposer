"""Step 2.3 (v3): paste 4-scene JSON into the scene_content field at the
CORRECT location (left portion of panel, image ~ (465,800)), then save.
Module-level enum callback pattern (proven reliable).
"""
import uiautomation as auto
import ctypes, time, subprocess, json, re, win32gui

u = ctypes.windll.user32
GEMINI_HWND = 0x60802
COPY_RECT = [2421, 641, 2475, 695]

_TITLE_HITS = []
_TITLE_SUB = ""
def _enum_cb(h, _):
    t = win32gui.GetWindowText(h)
    if _TITLE_SUB in t:
        _TITLE_HITS.append(h)
    return 1
def find_by_title(sub):
    global _TITLE_HITS, _TITLE_SUB
    _TITLE_HITS = []; _TITLE_SUB = sub
    win32gui.EnumWindows(_enum_cb, None)
    return _TITLE_HITS[0] if _TITLE_HITS else None

def get_clip():
    r = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
        "-Command","[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        capture_output=True,text=True,encoding="utf-8",errors="replace")
    return (r.stdout or "")

def click_phys(px,py):
    u.SetCursorPos(px,py); time.sleep(0.35)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08)
    u.mouse_event(0x0004,0,0,0,0); time.sleep(0.6)

def ctrl_key(vk):
    u.keybd_event(0x11,0,0,0); u.keybd_event(vk,0,0,0)
    u.keybd_event(vk,0,2,0); u.keybd_event(0x11,0,2,0)

def main():
    # re-copy gemini JSON
    root = auto.ControlFromHandle(GEMINI_HWND); root.SetActive(); time.sleep(1.0)
    cx=(COPY_RECT[0]+COPY_RECT[2])//2; cy=(COPY_RECT[1]+COPY_RECT[3])//2
    click_phys(cx,cy); time.sleep(1.2)
    clip=get_clip()
    print("clip caption hits:", len(re.findall(r'"caption"',clip)))

    panel=find_by_title("分镜")
    rect=win32gui.GetWindowRect(panel)
    ctl=auto.ControlFromHandle(panel); ctl.SetActive(); time.sleep(1.0)
    # field center per vision: image (465,800) -> rel same
    fx=rect[0]+465; fy=rect[1]+800
    print("clicking field at", fx, fy)
    click_phys(fx,fy)
    time.sleep(0.3)
    ctrl_key(0x41); time.sleep(0.15); ctrl_key(0x56); time.sleep(1.2)
    print("clip after paste:", len(re.findall(r'"caption"',get_clip())))

    # save at rel (431,1248)
    sx=rect[0]+431; sy=rect[1]+1248
    click_phys(sx,sy); time.sleep(2.0)
    time.sleep(0.5)
    # verify disk
    p=r"D:/AI_MEDIA/program/counseling/list/武志紅講心理.json"
    data=json.load(open(p,encoding="utf-8"))
    for r in data:
        if r.get("id")=="Q5k871aSvNU":
            sc=r.get("scene_content")
            caps=[s.get("caption") for s in sc] if isinstance(sc,list) else []
            print("DISK captions:", caps); break
    print(json.dumps({"ok":True},ensure_ascii=False))

if __name__=="__main__":
    main()

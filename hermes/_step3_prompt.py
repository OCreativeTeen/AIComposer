"""Step 3.1: in the 分镜 panel, click NotebookLM button, then keyboard-nav to
Image 幻灯片 -> 单图-一张概括全部场景, which copies the cover prompt to clipboard.
Verify clipboard contains 'Export_variant: image/single'.
Module-level enum callback (proven reliable). Safe mouse_event click.
"""
import uiautomation as auto
import ctypes, time, subprocess, re, win32gui

u = ctypes.windll.user32
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

def main():
    panel=find_by_title("分镜")
    rect=win32gui.GetWindowRect(panel)
    ctl=auto.ControlFromHandle(panel); ctl.SetActive(); time.sleep(1.0)
    # NotebookLM button at rel (292,1248)
    nx=rect[0]+292; ny=rect[1]+1248
    click_phys(nx,ny)
    time.sleep(0.8)
    # keyboard nav: Down (highlight Image 幻灯片), Right (open submenu, item1 highlighted), Return
    auto.SendKey(auto.Keys.VK_DOWN); time.sleep(0.3)
    auto.SendKey(auto.Keys.VK_RIGHT); time.sleep(0.4)
    auto.SendKey(auto.Keys.VK_RETURN); time.sleep(0.8)
    clip=get_clip()
    print("clip len:", len(clip.strip()))
    print("Export_variant:", re.findall(r'Export_variant:\s*\r?\n?\r?\n?(\S+)', clip))
    print("head:", clip[:60].replace("\n"," "))
    print(json.dumps({"clip_len":len(clip.strip()),
                      "variant": (re.findall(r'Export_variant:\s*\r?\n?\r?\n?(\S+)', clip) or [None])[0]},
                     ensure_ascii=False))

if __name__=="__main__":
    import json
    main()

"""Step 3 prep: in the 分镜 panel, click the NotebookLM button, navigate the
context menu to 'Image 幻灯片' -> '单图 · 一张概括全部场景' (single-image cover),
which copies the cover prompt to the clipboard with an Export_variant marker.
Per reference: keyboard nav (coordinate click of menu item no-ops):
  VK_DOWN (highlight Image 幻灯片), VK_RIGHT (open submenu), VK_RETURN (select single).
Verify by re.findall(r'Export_variant:\\s*\\r?\\n\\r?\\n?(\\S+)', clipboard).
"""
import sys; sys.path.insert(0, 'hermes')
from _click import safe_click
import uiautomation as auto, win32gui, time, pyperclip, re, ctypes

USER32 = ctypes.windll.user32

def find_toplevel(sub):
    res=[]
    def cb(h,_):
        if win32gui.IsWindowVisible(h) and sub in win32gui.GetWindowText(h): res.append(h)
        return 1
    win32gui.EnumWindows(cb,None); return res

def send_key(k):
    auto.SendKeys(k); time.sleep(0.25)

def main():
    panel=find_toplevel("分镜")[0]
    # NotebookLM button: panel-rel (292,1240) -> screen
    r=auto.ControlFromHandle(panel).BoundingRectangle
    nb_x = r.left + 292
    nb_y = r.top + 1240
    print("clicking NotebookLM at screen", (nb_x, nb_y))
    safe_click(panel, 292, 1240, pre_sleep=0.9, post_sleep=0.8)
    time.sleep(0.6)
    # menu appeared -> keyboard nav
    send_key('{Down}')      # highlight Image 幻灯片
    send_key('{Right}')     # open submenu (item 1 already highlighted)
    send_key('{Return}')    # select 单图 · 一张概括全部场景
    time.sleep(1.0)
    cb=pyperclip.paste()
    m=re.findall(r'Export_variant:\s*\r?\n\r?\n?(\S+)', cb)
    print("clipboard len:", len(cb))
    print("Export_variant match:", m)
    print("has '单图' / cover keywords:", any(k in cb for k in ['单图','概括','信息图','infographic','Infographic','Export_variant']))

if __name__=='__main__':
    main()

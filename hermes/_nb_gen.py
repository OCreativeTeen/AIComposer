"""NotebookLM infographic cover generation driver.
Steps: click Infographic chevron -> Customize dialog -> set prompt (SetFocus+paste),
set Language (繁體 for tw), Orientation=Portrait, Detail=Concise, Generate.
Then poll for completion and export 3 candidates to JPG.

Coordinates are GROUND-TRUTH from vision probe of the live window:
  Infographic tile ~(830,450), chevron ~(900,450)  [screen coords in 3462x1390]
We click via the window's UIA origin offset.
"""
import uiautomation as auto
import win32gui, time, ctypes, re, sys

USER32 = ctypes.windll.user32

NB_HWND = 0xe055e  # set at runtime

def w():
    return auto.ControlFromHandle(NB_HWND)

def find_nb():
    res=[]
    def cb(h,_):
        if win32gui.IsWindowVisible(h) and 'Story Builder' in win32gui.GetWindowText(h) and 'Google Chrome' in win32gui.GetWindowText(h):
            res.append(h)
        return 1
    win32gui.EnumWindows(cb,None)
    return res[0] if res else None

def click_screen(x, y, pre=0.9, hold=0.09, post=0.6):
    ctl=w(); ctl.SetActive(); time.sleep(pre)
    r=ctl.BoundingRectangle
    ax,ay=r.left+x, r.top+y
    USER32.SetCursorPos(ax,ay); time.sleep(0.3)
    USER32.mouse_event(0x0002,0,0,0,0); time.sleep(hold); USER32.mouse_event(0x0004,0,0,0,0)
    time.sleep(post)
    return ax,ay

def find_control(name_sub, ctype=None, depth=44):
    for t,d in auto.WalkControl(w(), maxDepth=depth):
        n=(t.Name or '').strip()
        if name_sub in n and (ctype is None or t.ControlTypeName==ctype):
            return t
    return None

def find_button(name_sub, depth=44):
    return find_control(name_sub, 'ButtonControl', depth)

def click_button_by_name(name_sub, pre=0.9, post=0.7):
    b=find_button(name_sub)
    if not b:
        # try HyperlinkControl
        b=find_control(name_sub, 'HyperlinkControl')
    if not b:
        raise RuntimeError(f"button not found: {name_sub!r}")
    r=b.BoundingRectangle
    ctl=w(); ctl.SetActive(); time.sleep(pre)
    USER32.SetCursorPos((r.left+r.right)//2,(r.top+r.bottom)//2); time.sleep(0.3)
    USER32.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); USER32.mouse_event(0x0004,0,0,0,0)
    time.sleep(post)
    return True

def set_text(name_sub, text, pre=1.0):
    ta=find_control(name_sub, 'EditControl')
    if not ta:
        raise RuntimeError(f"edit not found: {name_sub!r}")
    ta.SetFocus(); time.sleep(0.8)
    auto.SendKeys('{Ctrl}a'); auto.SendKeys('{Ctrl}v')
    # verify
    v=ta.GetValuePattern().Value
    print(f"  field {name_sub!r} length after paste: {len(v)}")
    return len(v)

def main():
    global NB_HWND
    NB_HWND = find_nb()
    print("NB hwnd", hex(NB_HWND) if NB_HWND else None)
    # open customize dialog via chevron
    click_screen(900, 450, pre=1.0)
    time.sleep(1.5)
    # set prompt
    ok=set_text('Describe the infographic', 'PROMPT_PLACEHOLDER')
    print("prompt set:", ok>0)

if __name__=='__main__':
    main()

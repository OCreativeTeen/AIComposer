"""NotebookLM Customize Infographic driver (live signed-in Profile 3 window).
Assumes the Customize Infographic dialog is OPEN (chevron clicked).
Steps: paste prompt into 'Describe the infographic' edit (verify by value read-back),
select Language for yt_language (tw -> 中文（繁體）), Orientation=Portrait,
Level of Detail=Concise, then click Generate.
"""
import sys; sys.path.insert(0,'hermes')
from _nb_gen import find_nb, w, click_screen, find_control, find_button, click_button_by_name
import uiautomation as auto, win32gui, time, ctypes, re, pyperclip

USER32 = ctypes.windll.user32

NB_HWND = None

def set_text_verify(name_sub, pre=1.0):
    ta = find_control(name_sub, 'EditControl', depth=48)
    if not ta:
        raise RuntimeError(f"edit not found: {name_sub!r}")
    ta.SetFocus(); time.sleep(0.8)
    auto.SendKeys('{Ctrl}a'); auto.SendKeys('{Ctrl}v')
    time.sleep(0.5)
    v = ta.GetValuePattern().Value
    print(f"  field {name_sub!r} pasted length: {len(v)}")
    return len(v)

def select_radio(name_sub, pre=0.8):
    rb = find_control(name_sub, 'RadioButtonControl', depth=48)
    if not rb:
        raise RuntimeError(f"radio not found: {name_sub!r}")
    r = rb.BoundingRectangle
    auto.ControlFromHandle(NB_HWND).SetActive(); time.sleep(pre)
    USER32.SetCursorPos((r.left+r.right)//2,(r.top+r.bottom)//2); time.sleep(0.3)
    USER32.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); USER32.mouse_event(0x0004,0,0,0,0)
    time.sleep(0.5)
    sel = rb.GetSelectionItemPattern().IsSelected
    print(f"  radio {name_sub!r} selected: {sel}")
    return sel

def set_language(tw=True):
    # open the language combobox, choose 中文（繁體）
    cb = find_control('Choose language', 'ComboBoxControl', depth=48)
    if not cb:
        # the combobox may be the control named 'Choose language' itself or its parent
        cb = find_control('Choose language', None, depth=48)
    if not cb:
        raise RuntimeError("language combobox not found")
    r = cb.BoundingRectangle
    auto.ControlFromHandle(NB_HWND).SetActive(); time.sleep(0.8)
    USER32.SetCursorPos((r.left+r.right)//2,(r.top+r.bottom)//2); time.sleep(0.3)
    USER32.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); USER32.mouse_event(0x0004,0,0,0,0)
    time.sleep(1.0)
    # now pick 中文（繁體）
    target = '中文（繁體）' if tw else 'English'
    opt = find_control(target, 'ListItemControl', depth=48) or find_control(target, 'ComboBoxItemControl', depth=48)
    if not opt:
        # try any control containing the text
        opt = find_control(target, None, depth=48)
    if not opt:
        print(f"  WARN: language option {target!r} not found; listing options")
        for t,d in auto.WalkControl(w(), maxDepth=48):
            if '體' in (t.Name or '') or '繁' in (t.Name or '') or 'English' in (t.Name or ''):
                print("    option:", repr(t.Name), t.ControlTypeName)
        return False
    r2 = opt.BoundingRectangle
    USER32.SetCursorPos((r2.left+r2.right)//2,(r2.top+r2.bottom)//2); time.sleep(0.3)
    USER32.mouse_event(0x0002,0,0,0,0); time.sleep(0.09); USER32.mouse_event(0x0004,0,0,0,0)
    time.sleep(0.6)
    print(f"  selected language option {target!r}")
    return True

def generate():
    click_button_by_name('Generate', pre=1.0, post=1.0)
    print("  clicked Generate")

def main():
    global NB_HWND
    NB_HWND = find_nb()
    # 1. paste prompt
    ok = set_text_verify('Describe the infographic')
    print("prompt pasted:", ok>0)
    # 2. language
    lang_ok = set_language(tw=True)
    # 3. orientation
    select_radio('Portrait')
    # 4. detail
    select_radio('Concise')
    # 5. generate
    generate()

if __name__=='__main__':
    main()

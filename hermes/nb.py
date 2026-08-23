import sys, time
sys.path.insert(0, 'hermes')
from wf_lib import *
import uiautomation as auto, pyperclip

H = 395266


def mclick(r):
    u.SetCursorPos(r.left + r.width() // 2, r.top + r.height() // 2)
    time.sleep(0.4)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.8)


def open_dialog():
    activate(H)
    t, nm, r = find(H, lambda t, n, rr: t.ControlTypeName == 'ButtonControl' and n == 'Infographic')
    u.SetCursorPos(r.left + r.width() // 2, r.top + r.height() // 2)
    time.sleep(2.0)
    u.SetCursorPos(r.right - 22, r.top + r.height() // 2)
    time.sleep(1.5)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(4)
    ta, _, _ = find(H, lambda t, n, rr: t.ControlTypeName == 'EditControl'
                    and 'Describe the infographic' in n)
    return ta is not None


def set_radio(name):
    t, nm, r = find(H, lambda t, n, rr: t.ControlTypeName == 'RadioButtonControl' and n == name)
    if not t:
        return None
    try:
        if t.GetSelectionItemPattern().IsSelected:
            return True
    except Exception:
        pass
    mclick(r)
    t, _, _ = find(H, lambda x, n, rr: x.ControlTypeName == 'RadioButtonControl' and n == name)
    return t.GetSelectionItemPattern().IsSelected


def set_language(want='中文（繁體）'):
    t, nm, r = find(H, lambda t, n, rr: t.ControlTypeName == 'ComboBoxControl' and n == 'Choose language')
    cur = ''
    try:
        cur = t.GetValuePattern().Value
    except Exception:
        pass
    print('  language currently:', repr(cur))
    if want in (cur or ''):
        return True
    mclick(r)
    time.sleep(1.5)
    it, n2, r2 = find(H, lambda x, n, rr: x.ControlTypeName == 'ListItemControl' and want in n)
    if it:
        mclick(r2)
        time.sleep(1.0)
        return True
    auto.SendKey(auto.Keys.VK_ESCAPE)
    return False


def submit(prompt):
    ta, _, _ = find(H, lambda t, n, rr: t.ControlTypeName == 'EditControl'
                    and 'Describe the infographic' in n)
    pyperclip.copy(prompt)
    time.sleep(0.4)
    ta.SetFocus()
    time.sleep(0.9)
    auto.SendKeys('{Ctrl}a')
    time.sleep(0.2)
    auto.SendKeys('{Ctrl}v')
    time.sleep(2.0)
    v = ta.GetValuePattern().Value
    print('  prompt chars in field:', len(v))
    if len(v) < 500:
        return False
    g, _, gr = find(H, lambda t, n, rr: t.ControlTypeName == 'ButtonControl' and n == 'Generate')
    mclick(gr)
    time.sleep(3)
    return True


def studio_rows():
    out = []
    for t, d in auto.WalkControl(ctl(H), maxDepth=42):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and t.ControlTypeName == 'ButtonControl' and ('source ·' in n or 'Generating' in n):
            out.append((n, r.left, r.top, r.width(), r.height()))
    return out

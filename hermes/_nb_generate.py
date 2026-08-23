"""Step 3.2: configure + generate ONE NotebookLM cover.
- SetFocus + paste cover prompt into 'Describe the infographic' EditControl.
- Set Language to 中文（繁體） (ComboBox).
- Click Portrait, Concise radios (verify IsSelected).
- Click Generate.
Safe physical clicks. Reports state. (One generation; call 3x for 3 covers.)
"""
import uiautomation as auto
import ctypes, time, subprocess, re, win32gui, json

u = ctypes.windll.user32
NB_HWND = 0x3098c

def walk(root, pred, depth=46):
    for t, d in auto.WalkControl(root, maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            yield t, n, r

def find(root, name_sub, ctype=None):
    for t, n, r in walk(root, lambda t, n, r:
            (ctype is None or t.ControlTypeName == ctype) and name_sub in n):
        return t, n, r
    return None, None, None

def click_phys(cx, cy):
    u.SetCursorPos(cx, cy); time.sleep(0.3)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08)
    u.mouse_event(0x0004,0,0,0,0); time.sleep(0.5)

def get_clip():
    r = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
        "-Command","[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        capture_output=True,text=True,encoding="utf-8",errors="replace")
    return (r.stdout or "")

def main():
    root = auto.ControlFromHandle(NB_HWND)
    root.SetActive(); time.sleep(1.5)

    # 1) paste prompt
    field, fn, fr = find(root, "Describe the infographic", "EditControl")
    if not field:
        print(json.dumps({"error":"Describe field not found"})); return
    field.SetFocus(); time.sleep(0.8)
    auto.SendKeys('{Ctrl}a'); time.sleep(0.1)
    auto.SendKeys('{Ctrl}v'); time.sleep(0.5)
    val = field.GetValuePattern().Value
    print("field chars:", len(val))
    if len(val) < 100:
        print("WARN field empty - paste may have failed")

    # 2) Language -> 中文（繁體）
    lang, ln, lr = find(root, "Choose language", "ComboBoxControl")
    if lang:
        lang.Click(); time.sleep(0.6)
        # expand then pick 中文（繁體）
        for t, n, r in walk(root, lambda t, n, r: '中文（繁體）' in n or '繁體' in n):
            t.Click(); time.sleep(0.5); break
        print("language set attempt done")
    else:
        print("no language combobox found")

    # 3) Portrait + Concise
    for sub, ctype in [("Portrait","RadioButtonControl"),("Concise","RadioButtonControl")]:
        rb, rn, rr = find(root, sub, ctype)
        if rb:
            rb.Click(); time.sleep(0.4)
            sel = rb.GetSelectionItemPattern().IsSelected if rb.GetSelectionItemPattern() else None
            print(f"{sub} selected:", sel)

    # 4) Generate
    gen, gn, gr = find(root, "Generate", "ButtonControl")
    if gen:
        gc = ((gr.left+gr.right)//2, (gr.top+gr.bottom)//2)
        click_phys(*gc)
        print("clicked Generate at", gc)
    time.sleep(1.0)
    print(json.dumps({"field_chars":len(val)}, ensure_ascii=False))

if __name__=="__main__":
    main()

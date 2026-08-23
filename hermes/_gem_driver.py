"""Drive Gemini (live signed-in Chrome) for the 4-scene JSON extraction.
Proven method (references/gemini-scene-extraction.md):
  send: focus 'Enter a prompt for Gemini' edit, verify focus, paste, send Enter
  wait: poll for 'Stop response'/'Stop' button gone + 'Copy code' button present
  extract: click 'Copy code' (response JSON code block) via safe mouse_event
Verifies by clipboard re.findall(r'\"caption\"') == 4 and json parse of 4 list.
"""
import uiautomation as auto
import win32gui, time, re, json, sys, ctypes, pyperclip

USER32 = ctypes.windll.user32

def find_chrome_gemini():
    for w in auto.GetRootControl().GetChildren():
        if "Google Chrome" in w.Name and w.NativeWindowHandle:
            # check it has a gemini app tab active/available
            for t,d in auto.WalkControl(w, maxDepth=14):
                if t.ControlTypeName=='TabItemControl' and 'Google Gemini' in (t.Name or ''):
                    # verify url via address bar? just return hwnd
                    return w.NativeWindowHandle
    return None

def gemini_input(hwnd):
    w=auto.ControlFromHandle(hwnd)
    for t,d in auto.WalkControl(w, maxDepth=42):
        if t.ControlTypeName=='EditControl' and 'prompt for Gemini' in (t.Name or ''):
            return t
    return None

def button_by_name(hwnd, name, depth=44):
    w=auto.ControlFromHandle(hwnd)
    for t,d in auto.WalkControl(w, maxDepth=depth):
        if t.ControlTypeName=='ButtonControl' and (t.Name or '').strip()==name:
            return t
    return None

def safe_click_control(ctl, window_hwnd=None, pre=0.8, hold=0.08, post=0.6):
    # activate the WINDOW (controls have no SetActive), then mouse_event at center
    if window_hwnd:
        try: auto.ControlFromHandle(window_hwnd).SetActive()
        except Exception: pass
    else:
        try: ctl.GetTopLevelControl().SetActive()
        except Exception: pass
    time.sleep(pre)
    r=ctl.BoundingRectangle
    cx=(r.left+r.right)//2; cy=(r.top+r.bottom)//2
    USER32.SetCursorPos(cx,cy); time.sleep(0.3)
    USER32.mouse_event(0x0002,0,0,0,0); time.sleep(hold); USER32.mouse_event(0x0004,0,0,0,0)
    time.sleep(post)

def send_prompt(hwnd, prompt_text):
    ta=gemini_input(hwnd)
    if not ta:
        raise RuntimeError("Gemini input not found")
    ta.SetFocus(); time.sleep(0.8)
    auto.SendKeys('{Ctrl}a'); auto.SendKeys('ZZSENTINELZZ')
    assert ta.GetValuePattern().Value=='ZZSENTINELZZ', "focus verify failed"
    assert auto.GetFocusedControl().Name=='Enter a prompt for Gemini', "focus name mismatch"
    auto.SendKeys('{Ctrl}a'); auto.SendKeys('{Ctrl}v')
    time.sleep(0.5)
    v=ta.GetValuePattern().Value
    assert len(v)>3000, f"paste too short: {len(v)}"
    # send
    auto.SendKeys('{Enter}')
    time.sleep(1.5)

def wait_for_response(hwnd, timeout=180):
    w=auto.ControlFromHandle(hwnd)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        stop=None; copycode=None
        for t,d in auto.WalkControl(w, maxDepth=44):
            n=(t.Name or '').strip()
            if n in ('Stop response','Stop'):
                stop=t
            elif n=='Copy code':
                copycode=t
        if copycode and not stop:
            return True
        if stop:
            time.sleep(2)
            continue
        time.sleep(2)
    return bool(button_by_name(hwnd,'Copy code'))

def extract_json(hwnd):
    cc=button_by_name(hwnd,'Copy code')
    if not cc:
        raise RuntimeError("Copy code button not found")
    safe_click_control(cc, window_hwnd=hwnd)
    cb=pyperclip.paste()
    caps=re.findall(r'"caption"', cb)
    dec=json.JSONDecoder()
    i=cb.find('[')
    objs=[]
    if i>=0:
        try:
            while i<len(cb):
                o,j=dec.raw_decode(cb,i)
                if isinstance(o,list) and len(o)==4:
                    objs=[o]; break
                while j<len(cb) and cb[j] in ' \r\n\t': j+=1
                i=j
        except Exception:
            pass
    return cb, caps, objs

def run():
    hwnd=find_chrome_gemini()
    print("gemini hwnd", hex(hwnd) if hwnd else None)
    prompt=pyperclip.paste()
    assert 'has 4 scene' in prompt, "clipboard not the 4-scene prompt"
    send_prompt(hwnd, prompt)
    print("prompt sent; waiting for response...")
    ok=wait_for_response(hwnd)
    print("response ready:", ok)
    cb,caps,objs=extract_json(hwnd)
    print("caption hits:", len(caps), "parsed 4-list:", bool(objs))
    if objs:
        # re-stage to clipboard as compact json for pasting
        pyperclip.copy(json.dumps(objs[0], ensure_ascii=False))
        print("STAGED 4-scene JSON to clipboard, len", len(json.dumps(objs[0],ensure_ascii=False)))
        return True
    print("FAILED to extract 4-scene JSON")
    return False

if __name__=='__main__':
    sys.exit(0 if run() else 1)

"""Step 2.2: send the 'has 4 scene' prompt into the live signed-in Gemini tab.
- Resolve the named input EditControl ('Enter a prompt for Gemini').
- Sentinel-verify focus (SetFocus + type ZZSENTINELZZ + read back value).
- Ctrl+A / Ctrl+V to paste the clipboard prompt.
- Click the Send button (ButtonControl name contains 'Send'/'发送').
- No response extraction (canvas-rendered, UIA-blind) - handoff to human.
"""
import uiautomation as auto
import ctypes, time, subprocess, json, win32gui

u = ctypes.windll.user32

GEMINI_HWND = 0x60802

def get_clip_len():
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-Command", "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    v = (r.stdout or "")
    return len(v.strip()), v.strip()

def walk(root, pred, depth=40):
    for t, d in auto.WalkControl(root, maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            yield t, n, r

def main():
    root = auto.ControlFromHandle(GEMINI_HWND)
    root.SetActive()
    time.sleep(1.2)

    # resolve input
    inp = None
    for t, n, r in walk(root, lambda t, n, r: t.ControlTypeName == 'EditControl'
                        and 'prompt for Gemini' in n):
        inp = t; break
    if not inp:
        print(json.dumps({"error": "Gemini input not found"}))
        return
    print("input found:", repr(inp.Name))

    # sentinel verify
    inp.SetFocus(); time.sleep(0.8)
    auto.SendKeys('{Ctrl}a'); time.sleep(0.1)
    auto.SendKeys('{Delete}'); time.sleep(0.2)
    auto.SendKeys('ZZSENTINELZZ'); time.sleep(0.3)
    val = inp.GetValuePattern().Value
    print("sentinel value:", repr(val), "focused:", auto.GetFocusedControl().Name)
    if val != 'ZZSENTINELZZ':
        print("WARN: sentinel not set; focus may be wrong")

    # paste clipboard prompt
    auto.SendKeys('{Ctrl}a'); time.sleep(0.1)
    auto.SendKeys('{Delete}'); time.sleep(0.2)
    auto.SendKeys('{Ctrl}v'); time.sleep(1.2)
    val = inp.GetValuePattern().Value
    print("after paste length:", len(val))
    print("paste ok:", len(val) > 3000)

    # click Send button
    sent = False
    for t, n, r in walk(root, lambda t, n, r: t.ControlTypeName == 'ButtonControl'
                        and ('Send' in n or '发送' in n)):
        try:
            t.SetFocus(); time.sleep(0.2); t.Click(); sent = True
            print("clicked send button:", repr(n))
            break
        except Exception as e:
            print("send click failed:", e)
    if not sent:
        # fallback: Enter
        inp.SetFocus(); auto.SendKeys('{Enter}')
        print("fallback: sent Enter")

    time.sleep(2.0)
    after = inp.GetValuePattern().Value
    print("input after send length:", len(after))
    print(json.dumps({"input_found": True, "sentinel_ok": val != 'ZZSENTINELZZ',
                      "paste_len": len(val), "paste_ok": len(val) > 3000,
                      "send_clicked": sent, "input_cleared_after_send": len(after) < 50},
                     ensure_ascii=False))

if __name__ == "__main__":
    main()

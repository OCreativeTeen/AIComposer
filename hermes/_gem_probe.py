import uiautomation as auto, ctypes
USER32 = ctypes.windll.user32

# Find the Gemini Chrome window (NOT notebook). Candidate titles seen earlier:
#  'Debugging Hermes Log Errors - Google Gemini - Google Chrome'  (0x60802)
#  'Story Builder: Young Chinese Protagonists - Gemini Notebook - Google Chrome' (notebook)
#  'Gemini Notebook - Google Chrome' x2 (notebook)
# The spec says Gemini is open in ocreativeteen profile. Let's enumerate all Chrome top-levels + their tabs.
def find_chrome():
    out=[]
    for w in auto.GetRootControl().GetChildren():
        nm=w.Name.strip()
        if "Google Chrome" in nm or "Gemini" in nm or "Grok" in nm or "Notebook" in nm:
            out.append((w.NativeWindowHandle, nm))
    return out

wins=find_chrome()
for hw,nm in wins:
    print("TOP:", hex(hw), repr(nm))

# For each Chrome window, enumerate tabs and read address bar URL
def find(pred, hwnd, depth=40):
    res=[]
    for t,d in auto.WalkControl(auto.ControlFromHandle(hwnd), maxDepth=depth):
        n=(t.Name or '').strip(); r=t.BoundingRectangle
        if r.width() and pred(t,n,r):
            res.append((t,n,r))
    return res

for hw,nm in wins:
    if "Google Chrome" not in nm: 
        continue
    # tabs
    tabs=find(lambda t,n,r: t.ControlTypeName=='TabItemControl' and n, hw)
    addr=find(lambda t,n,r: t.ControlTypeName=='EditControl' and n=='Address and search bar', hw)
    print(f"\n--- Chrome hw={hex(hw)} {nm!r} ---")
    for t,n,r in tabs:
        print(f"   TAB: {n!r}")
    for t,n,r in addr:
        try:
            url=t.GetValuePattern().Value
        except Exception as e:
            url=f"<err {e}>"
        print(f"   ADDR: {url!r}")

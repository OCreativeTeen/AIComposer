import uiautomation as auto, win32gui, win32con, time, ctypes
USER32=ctypes.windll.user32

gem_hw=0x60802
w=auto.ControlFromHandle(gem_hw)
print("window exists:", w.Exists(1,1))
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.8)

def findall(pred, depth=40):
    res=[]
    for t,d in auto.WalkControl(w, maxDepth=depth):
        n=(t.Name or '').strip(); r=t.BoundingRectangle
        if r.width() and pred(t,n,r):
            res.append((t,n,r))
    return res

print("\n=== New chat / Search controls ===")
for t,n,r in findall(lambda t,n,r: ('New chat' in n or 'Search' in n) and t.ControlTypeName in ('ButtonControl','HyperlinkControl','PaneControl')):
    print(f"  {t.ControlTypeName} {n!r} rect=({r.left},{r.top},{r.right},{r.bottom})")

print("\n=== prompt input controls ===")
for t,n,r in findall(lambda t,n,r: 'prompt for Gemini' in n or 'Enter a prompt' in n):
    print(f"  {t.ControlTypeName} {n!r} rect=({r.left},{r.top},{r.right},{r.bottom})")

print("\n=== address bar ===")
for t,n,r in findall(lambda t,n,r: n=='Address and search bar'):
    try: url=t.GetValuePattern().Value
    except Exception as e: url=f"<err {e}>"
    print(f"  {t.ControlTypeName} url={url!r}")

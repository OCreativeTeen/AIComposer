import uiautomation as auto, win32gui, win32con, time
gem_hw=0x60802
if win32gui.IsIconic(gem_hw): win32gui.ShowWindow(gem_hw, win32con.SW_RESTORE)
win32gui.SetForegroundWindow(gem_hw); time.sleep(0.6)
w=auto.ControlFromHandle(gem_hw)
print("=== controls matching Copy/复制/export ===")
for t,d in auto.WalkControl(w, maxDepth=40):
    n=(t.Name or '').strip(); r=t.BoundingRectangle
    if r.width() and ('Copy' in n or '复制' in n or 'Export' in n or '导出' in n or 'Share' in n or '共享' in n or 'Download' in n or '下载' in n):
        print(f"  d{d} {t.ControlTypeName} {n!r} rect=({r.left},{r.top},{r.right},{r.bottom})")
print("=== done scan ===")

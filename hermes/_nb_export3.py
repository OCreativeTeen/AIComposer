"""Step 3 export via per-row ⋮ menu. Click the three-dot menu on a given
infographic row (by index 0..2), then probe for the revealed Export/JPG/Export
Image controls. One row per call. Module-level enum.
"""
import uiautomation as auto
import ctypes, time, subprocess, win32gui, json, os

u = ctypes.windll.user32
NB_HWND = 0x3098c
DL = os.path.expanduser("~/Downloads")
STALE = {"cover1.jpg","cover2.jpg","cover3.jpg"}

def walk(root, pred, depth=46):
    for t, d in auto.WalkControl(root, maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            yield t, n, r

def click_phys(cx, cy):
    u.SetCursorPos(cx, cy); time.sleep(0.3)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0)
    time.sleep(0.7)

def newest_real_jpg(before):
    files=[]
    for f in os.listdir(DL):
        if f.lower().endswith('.jpg') and f not in STALE:
            p=os.path.join(DL,f)
            if os.path.getmtime(p)>=before: files.append(p)
    return max(files,key=os.path.getmtime) if files else None

def main():
    idx = int(__import__('sys').argv[1]) if len(__import__('sys').argv)>1 else 0
    root = auto.ControlFromHandle(NB_HWND)
    root.SetActive(); time.sleep(1.5)
    # row y positions: crop y=540,720,900 -> window y 540,720,900 (crop started at x only)
    row_ys = [540, 720, 900]
    # x of ⋮ menu ~ window 2215 (crop 830 + 1385 offset)
    menu_x = 2215
    y = row_ys[idx]
    before = time.time()
    click_phys(menu_x, y)
    time.sleep(1.0)
    # probe revealed menu items
    print("=== revealed controls after ⋮ click ===")
    found=[]
    for t,n,r in walk(root, lambda t,n,r: any(k in n for k in ['Export','JPG','PNG','Download','Copy','Open','Delete'])):
        print(f"  [{t.ControlTypeName}] {n!r} rect=({r.left},{r.top},{r.right},{r.bottom})")
        found.append((n,(r.left+r.right)//2,(r.top+r.bottom)//2))
    # try to click Export / JPG / Export Image if present
    for label in ['JPG','Export Image','Export']:
        for n,(cx,cy) in found:
            if label in n:
                click_phys(cx,cy); time.sleep(1.0); break
    time.sleep(3)
    nj=newest_real_jpg(before)
    print("new jpg:", os.path.basename(nj) if nj else "NO")
    print(json.dumps({"row":idx,"revealed":[f[0] for f in found],"jpg":bool(nj)},ensure_ascii=False))

if __name__=="__main__":
    main()

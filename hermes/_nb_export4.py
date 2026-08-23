"""Step 3 export: click a row's ⋮ menu at precise coords, reveal + click export.
Row index 0/1/2 -> y 536/596/656, x=3342. After clicking ⋮, probe for the
revealed menu item (Export infographic / Download / JPG), click it, then in the
dialog pick JPG + Export Image. Verify a fresh (non-stale) .jpg in Downloads.
"""
import sys, os, time
import uiautomation as auto
import ctypes, win32gui, subprocess

u = ctypes.windll.user32
NB_HWND = 0x3098c
DL = os.path.expanduser("~/Downloads")
STALE = {"cover1.jpg","cover2.jpg","cover3.jpg"}
MENU_X = 3342
ROW_Y = [536, 596, 656]

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
    idx = int(sys.argv[1]) if len(sys.argv)>1 else 0
    root = auto.ControlFromHandle(NB_HWND)
    root.SetActive(); time.sleep(1.5)
    before = time.time()
    click_phys(MENU_X, ROW_Y[idx])
    time.sleep(1.2)
    # probe revealed menu
    items=[(n,(r.left+r.right)//2,(r.top+r.bottom)//2) for t,n,r in
           walk(root, lambda t,n,r: any(k in n for k in
                 ['Export','Download','JPG','PNG','Copy','Open','Delete','信息图']))]
    print("revealed items:", [i[0] for i in items])
    # click the export/download item
    target=None
    for n,(cx,cy) in items:
        if 'Export' in n or 'Download' in n or '信息图' in n:
            target=(cx,cy); break
    if target:
        click_phys(*target); time.sleep(1.5)
    # now in export dialog: JPG then Export Image
    for _ in range(14):
        jpg=None
        for t,n,r in walk(root, lambda t,n,r: t.ControlTypeName=='ButtonControl' and n=='JPG'):
            jpg=((r.left+r.right)//2,(r.top+r.bottom)//2); break
        if jpg:
            click_phys(*jpg); break
        time.sleep(1.5)
    time.sleep(1.0)
    for _ in range(14):
        ei=None
        for t,n,r in walk(root, lambda t,n,r: t.ControlTypeName=='ButtonControl' and n=='Export Image'):
            ei=((r.left+r.right)//2,(r.top+r.bottom)//2); break
        if ei:
            click_phys(*ei); break
        time.sleep(2)
    time.sleep(3)
    nj=newest_real_jpg(before)
    print("new jpg:", os.path.basename(nj) if nj else "NO")
    print(json.dumps({"row":idx,"revealed":[i[0] for i in items],"jpg":bool(nj)},ensure_ascii=False))

if __name__=="__main__":
    main()

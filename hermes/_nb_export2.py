"""Step 3 export attempt (careful, one at a time). For each infographic row,
reveal + click its per-row Export button, choose JPG, click Export Image,
verify a NEW Chinese-named .jpg lands in Downloads (not the stale cover1-3.jpg).
Module-level enum. Verifies by artifact.
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
    root = auto.ControlFromHandle(NB_HWND)
    root.SetActive(); time.sleep(1.5)
    exported=0
    # loop attempts to find Export buttons; retry a few times as rows reveal
    for attempt in range(3):
        btns=[(t,n,r) for t,n,r in walk(root, lambda t,n,r:
               ('Export信息图' in n or ('Export' in n and 'Image' in n))
               and t.ControlTypeName=='ButtonControl')]
        print(f"attempt {attempt}: export buttons={len(btns)}")
        if not btns: break
        for t,n,r in btns[:1]:  # one per attempt
            gc=((r.left+r.right)//2,(r.top+r.bottom)//2)
            before=time.time()
            click_phys(*gc)
            time.sleep(1.5)
            # JPG
            for bt,bn,br in walk(root, lambda t,n,r: t.ControlTypeName=='ButtonControl' and n=='JPG'):
                click_phys((br.left+br.right)//2,(br.top+br.bottom)//2); break
            time.sleep(1.0)
            # Export Image (poll)
            for _ in range(14):
                ei=None
                for bt,bn,br in walk(root, lambda t,n,r: t.ControlTypeName=='ButtonControl' and n=='Export Image'):
                    ei=((br.left+br.right)//2,(br.top+br.bottom)//2); break
                if ei:
                    click_phys(*ei); break
                time.sleep(2)
            time.sleep(3)
            nj=newest_real_jpg(before)
            print(f"  -> jpg={'YES '+os.path.basename(nj) if nj else 'NO'}")
            if nj: exported+=1
            root.SetActive(); time.sleep(1.0)
    print(json.dumps({"exported_new":exported},ensure_ascii=False))

if __name__=="__main__":
    main()

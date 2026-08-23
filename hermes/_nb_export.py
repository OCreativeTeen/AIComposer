"""Step 3 export: for each completed infographic row, click its per-row
'Export信息图' button, choose JPG, click 'Export Image', verify a .jpg lands
in Downloads. Module-level enum. Iterates all 'Export信息图' buttons found.
"""
import uiautomation as auto
import ctypes, time, subprocess, win32gui, json, os

u = ctypes.windll.user32
NB_HWND = 0x3098c
DL = os.path.expanduser("~/Downloads")

def walk(root, pred, depth=46):
    for t, d in auto.WalkControl(root, maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            yield t, n, r

def click_phys(cx, cy):
    u.SetCursorPos(cx, cy); time.sleep(0.3)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0)
    time.sleep(0.6)

def downloads_newest_jpg(before):
    files = [os.path.join(DL, f) for f in os.listdir(DL) if f.lower().endswith('.jpg')]
    files = [f for f in files if os.path.getmtime(f) >= before]
    return max(files, key=os.path.getmtime) if files else None

def main():
    root = auto.ControlFromHandle(NB_HWND)
    # find all per-row Export信息图 buttons
    root.SetActive(); time.sleep(1.5)
    exports = [(t, n, r) for t, n, r in walk(root, lambda t, n, r:
               'Export信息图' in n or 'Export' in n and 'Image' in n)]
    print("export buttons found:", len(exports))
    count = 0
    for t, n, r in exports:
        gc = ((r.left+r.right)//2, (r.top+r.bottom)//2)
        before = time.time()
        click_phys(*gc)
        time.sleep(1.5)
        # in export dialog: click JPG then Export Image (poll by name)
        dlg_root = root
        # JPG
        for bt, bn, br in walk(dlg_root, lambda t, n, r: t.ControlTypeName=='ButtonControl' and n=='JPG'):
            click_phys((br.left+br.right)//2, (br.top+br.bottom)//2); break
        time.sleep(0.8)
        # Export Image (appears after delay)
        for _ in range(14):
            ei = None
            for bt, bn, br in walk(dlg_root, lambda t, n, r: t.ControlTypeName=='ButtonControl' and n=='Export Image'):
                ei = (br.left+br.right)//2, (br.top+br.bottom)//2; break
            if ei:
                click_phys(*ei); break
            time.sleep(2)
        time.sleep(3)
        nj = downloads_newest_jpg(before)
        print(f"row export {count+1}: jpg={'YES '+os.path.basename(nj) if nj else 'NO'}")
        count += 1
    print(json.dumps({"exported": count}, ensure_ascii=False))

if __name__=="__main__":
    main()

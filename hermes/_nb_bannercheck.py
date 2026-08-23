import uiautomation as auto
for h in (0x450200, 0x3b0782, 0xe055e):
    w=auto.ControlFromHandle(h)
    banner=None; studio_tiles=[]
    for t,d in auto.WalkControl(w, maxDepth=46):
        n=(t.Name or '').strip()
        if 'daily' in n.lower() and 'limit' in n.lower(): banner=n
        if n=='Infographic': studio_tiles.append(True)
    print(hex(h), "| quota banner:", banner, "| infographic tile present:", bool(studio_tiles))

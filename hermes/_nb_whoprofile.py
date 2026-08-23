import uiautomation as auto, win32gui, win32process, psutil
for h in (0x450200, 0x3b0782):
    _,pid=win32process.GetWindowThreadProcessId(h)
    try:
        p=psutil.Process(pid); exe=p.exe().split(chr(92))[-1]
    except Exception as e:
        exe=str(e)
    w=auto.ControlFromHandle(h)
    url=None
    for t,d in auto.WalkControl(w, maxDepth=14):
        if t.ControlTypeName=='EditControl' and (t.Name or '').strip()=='Address and search bar':
            url=t.GetValuePattern().Value; break
    print(hex(h), "pid",pid, "exe", exe, "URL", url)

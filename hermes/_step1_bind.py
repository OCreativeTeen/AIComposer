import json, re, uiautomation as auto, ctypes

USER32 = ctypes.windll.user32
def hwnd_pid(hwnd):
    pid = ctypes.c_int(0)
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

# 1) parse the step1 stdout JSON
raw = open(r"D:\AI_MEDIA\program\step1_stdout.log", encoding="utf-8", errors="ignore").read()
idx = raw.find("{")
dec = json.JSONDecoder()
objs = []
i = idx
while i < len(raw):
    try:
        o, j = dec.raw_decode(raw, i)
    except ValueError:
        break
    objs.append(o)
    while j < len(raw) and raw[j] in " \r\n\t,":
        j += 1
    i = j
print("JSON objects parsed:", len(objs))
qi = objs[0]["queue_item"]
vd = objs[0]["video_detail"]
print("choice_id:", qi["choice_id"])
print("title:", qi["title"])
print("yt_language:", qi["yt_language"])
print("video_detail has scene_content key:", "scene_content" in vd)

# 2) find the editor windows
print("\n=== Editor windows ===")
for w in auto.GetRootControl().GetChildren():
    nm = w.Name.strip()
    hwnd = w.NativeWindowHandle
    if not nm:
        continue
    if "AIComposer" in nm or "摘要" in nm or "拖入" in nm:
        r = w.BoundingRectangle
        print(f"  hwnd={hwnd:#x} pid={hwnd_pid(hwnd)} {w.ControlTypeName} {nm!r} rect=({r.left},{r.top},{r.right},{r.bottom})")

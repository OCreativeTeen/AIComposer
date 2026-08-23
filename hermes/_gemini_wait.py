"""Wait for Gemini generation, then screenshot the window for a visual check.
Also probe for the 'Stop responding' button (present while generating) so we
can report generation state. Saves screenshot to hermes/gemini_wait.png.
"""
import uiautomation as auto
import ctypes, time, subprocess, json, win32gui
from PIL import ImageGrab

GEMINI_HWND = 0x60802
OUT = "hermes/gemini_wait.png"

def walk(root, pred, depth=40):
    for t, d in auto.WalkControl(root, maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            yield t, n, r

def main():
    root = auto.ControlFromHandle(GEMINI_HWND)
    states = []
    for sec in [0, 30, 60, 90, 110]:
        if sec > 0:
            time.sleep(30 if sec != 110 else 20)
        root.SetActive(); time.sleep(0.5)
        rect = win32gui.GetWindowRect(GEMINI_HWND)
        img = ImageGrab.grab(bbox=rect)
        img.save(OUT)
        # detect stop button
        stop = None
        for t, n, r in walk(root, lambda t, n, r: t.ControlTypeName == 'ButtonControl'
                            and ('Stop' in n or '停止' in n)):
            stop = n; break
        states.append({"t+%ds" % sec: {"stop_button": stop}})
    print(json.dumps(states, ensure_ascii=False, indent=2))
    print("screenshot:", OUT)

if __name__ == "__main__":
    main()

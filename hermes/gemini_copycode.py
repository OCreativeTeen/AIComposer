#!/usr/bin/env python3
"""Click Gemini's 'Copy code' button on the JSON response, read clipboard,
validate 4-scene JSON. Retries a couple of times across copy controls.
Saves hermes/gemini_scenes.json on success."""
import sys, time, ctypes, json
import uiautomation as auto
import pyperclip

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 2032376
u = ctypes.windll.user32
w = auto.ControlFromHandle(HWND)

def click_named(name_sub):
    for c, d in auto.WalkControl(w, maxDepth=42):
        nm = (c.Name or "").strip().lower()
        if c.ControlTypeName == "ButtonControl" and name_sub in nm:
            r = c.BoundingRectangle
            cx, cy = r.left + r.width()//2, r.top + r.height()//2
            u.SetCursorPos(cx, cy); time.sleep(0.25)
            u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0)
            return (cx, cy)
    return None

def parse_scenes(text):
    i = text.find("[")
    if i < 0: return None
    dec = json.JSONDecoder()
    try:
        obj, _ = dec.raw_decode(text[i:])
    except Exception:
        return None
    if not isinstance(obj, list) or len(obj) != 4:
        return None
    need = {"caption","voiceover","visual","speaking","actor"}
    for o in obj:
        if not isinstance(o, dict) or not need.issubset(o.keys()):
            return None
    return obj

for label in ("copy code", "copy"):
    pos = click_named(label)
    print("clicked", label, pos)
    time.sleep(1.0)
    clip = pyperclip.paste() or ""
    print(f"  clipboard_len={len(clip)} caption_hits={clip.count('caption')}")
    scenes = parse_scenes(clip)
    if scenes:
        with open("hermes/gemini_scenes.json","w",encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        print("SCENES_FOUND_AND_SAVED n=", len(scenes))
        print("captions:", [s.get("caption") for s in scenes])
        print("RESULT_JSON " + json.dumps({"found":True,"n":len(scenes),"via":label}, ensure_ascii=False))
        sys.exit(0)

print("NO_VALID_JSON_FROM_COPY")
print("RESULT_JSON " + json.dumps({"found":False}, ensure_ascii=False))

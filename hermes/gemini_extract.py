#!/usr/bin/env python3
"""Step 2.3: extract Gemini's 4-scene JSON from the chat via Ctrl+A/Ctrl+C
page scrape. Validates a JSON array of exactly 4 objects with the
caption/voiceover/visual/speaking/actor schema. Prints PROGRESS/FOUND/RETRY.
"""
import sys, time, ctypes, json, re
import uiautomation as auto
import pyperclip

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 2032376
MAX_WAIT = int(sys.argv[2]) if len(sys.argv) > 2 else 180
u = ctypes.windll.user32

w = auto.ControlFromHandle(HWND)

def find_input():
    for c, d in auto.WalkControl(w, maxDepth=42):
        if c.ControlTypeName == "EditControl" and "prompt for Gemini" in (c.Name or ""):
            return c
    return None

def extract_clipboard():
    # drop focus: click top margin of window, then Esc
    r = w.BoundingRectangle
    u.SetCursorPos(r.left + 30, r.top + 8); time.sleep(0.2)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.05); u.mouse_event(0x0004,0,0,0,0)
    time.sleep(0.3)
    auto.SendKeys("{Esc}"); time.sleep(0.4)
    # select all + copy (page scrape)
    auto.SendKeys("{Ctrl}a"); time.sleep(0.4)
    auto.SendKeys("{Ctrl}c"); time.sleep(0.6)
    return pyperclip.paste() or ""

def parse_scenes(text):
    # find first [ ... ] array
    i = text.find("[")
    if i < 0:
        return None
    dec = json.JSONDecoder()
    try:
        obj, _ = dec.raw_decode(text[i:])
    except Exception:
        return None
    if not isinstance(obj, list):
        return None
    if len(obj) != 4:
        return None
    need = {"caption", "voiceover", "visual", "speaking", "actor"}
    for o in obj:
        if not isinstance(o, dict) or not need.issubset(o.keys()):
            return None
    return obj

deadline = time.time() + MAX_WAIT
attempt = 0
last_len = 0
while time.time() < deadline:
    attempt += 1
    clip = extract_clipboard()
    print(f"[attempt {attempt}] clipboard_len={len(clip)}  caption_hits={clip.count('caption') if clip else 0}")
    scenes = parse_scenes(clip)
    if scenes:
        print("SCENES_FOUND")
        # save to file for next step
        with open("hermes/gemini_scenes.json", "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        print("SAVED hermes/gemini_scenes.json")
        # also save raw for debugging
        with open("hermes/gemini_raw.txt", "w", encoding="utf-8") as f:
            f.write(clip)
        print("RESULT_JSON " + json.dumps({"found": True, "n": len(scenes)}, ensure_ascii=False))
        sys.exit(0)
    # detect still-generating (clipboard growing between polls) vs stalled
    time.sleep(6)

print("TIMEOUT_NO_VALID_JSON")
print("RESULT_JSON " + json.dumps({"found": False}, ensure_ascii=False))

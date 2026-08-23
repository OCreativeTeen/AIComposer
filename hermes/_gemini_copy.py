"""Step 2.3: click the 'Copy code' button on the Gemini response card, verify
the clipboard now holds a valid 4-scene JSON array.
"""
import uiautomation as auto
import ctypes, time, subprocess, json, re, win32gui

u = ctypes.windll.user32
GEMINI_HWND = 0x60802
COPY_RECT = [2421, 641, 2475, 695]  # from probe: Copy code button

def get_clip():
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-Command", "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "")

def extract_array(text):
    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.I)
    cleaned = cleaned.replace("```", "").strip()
    dec = json.JSONDecoder()
    for m in re.finditer(r"\[", cleaned):
        try:
            val, _ = dec.raw_decode(cleaned[m.start():])
            if isinstance(val, list):
                return val
        except Exception:
            continue
    return None

def main():
    root = auto.ControlFromHandle(GEMINI_HWND)
    root.SetActive(); time.sleep(1.0)
    cx = (COPY_RECT[0] + COPY_RECT[2]) // 2
    cy = (COPY_RECT[1] + COPY_RECT[3]) // 2
    u.SetCursorPos(cx, cy); time.sleep(0.3)
    u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.08)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(1.2)
    clip = get_clip()
    arr = extract_array(clip)
    print("clip length:", len(clip.strip()))
    print("caption hits:", len(re.findall(r'"caption"', clip)))
    print("json array:", "YES" if arr is not None else "NO",
          "len:", len(arr) if arr else 0)
    if arr:
        keys = list(arr[0].keys()) if arr and isinstance(arr[0], dict) else None
        print("scene0 keys:", keys)
    print(json.dumps({"clip_len": len(clip.strip()),
                      "caption_hits": len(re.findall(r'"caption"', clip)),
                      "is_4scene_array": arr is not None and len(arr) == 4},
                     ensure_ascii=False))

if __name__ == "__main__":
    main()

import sys
print("PYTHON:", sys.executable)
for mod in ("uiautomation", "pyautogui", "pyperclip", "cv2", "win32gui"):
    try:
        __import__(mod)
        print(f"{mod}: OK")
    except Exception as e:
        print(f"{mod}: MISSING {e!r}")

import uiautomation as auto
print("\n=== TOP-LEVEL WINDOWS (filtered) ===")
keys = ("AIComposer", "摘要", "拖入", "Chrome", "Gemini", "Notebook", "Grok", "Google")
seen = set()
for w in auto.GetRootControl().GetChildren():
    nm = w.Name.strip()
    if nm and any(k in nm for k in keys) and nm not in seen:
        seen.add(nm)
        print(f"  hwnd={w.NativeWindowHandle:#x}  {w.ControlTypeName}  {nm!r}")

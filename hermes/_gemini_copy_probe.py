"""Probe the Gemini response card for a copy-control. Gemini code blocks expose a
'Copy code' ButtonControl. If found, we can auto-extract the JSON to clipboard
(cleaner than manual handoff). Report every copy-ish button we can see.
"""
import uiautomation as auto
import json, win32gui, time

GEMINI_HWND = 0x60802

def walk(root, pred, depth=42):
    for t, d in auto.WalkControl(root, maxDepth=depth):
        n = (t.Name or '').strip()
        r = t.BoundingRectangle
        if r.width() and pred(t, n, r):
            yield t, n, r

def main():
    root = auto.ControlFromHandle(GEMINI_HWND)
    root.SetActive(); time.sleep(1.0)
    hits = []
    for t, n, r in walk(root, lambda t, n, r:
                        ('Copy' in n or '复制' in n or 'code' in n.lower())
                        and t.ControlTypeName in ('ButtonControl', 'HyperlinkControl', 'MenuItemControl')):
        hits.append({"name": n, "type": t.ControlTypeName,
                     "rect": [r.left, r.top, r.right, r.bottom]})
    print(json.dumps(hits, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

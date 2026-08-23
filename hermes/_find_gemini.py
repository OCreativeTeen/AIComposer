"""Locate the live signed-in Gemini Chrome window and resolve its input field.
No clicks. Just report hwnd, rect, URL (from address bar), and whether an
'Enter a prompt for Gemini' EditControl exists (the verified-named input).
"""
import uiautomation as auto
import json, subprocess

def get_url(hwnd):
    root = auto.ControlFromHandle(hwnd)
    try:
        addr, _, _ = None, None, None
        for t, d in auto.WalkControl(root, maxDepth=40):
            if t.ControlTypeName == 'EditControl' and (t.Name or '') == 'Address and search bar':
                return t.GetValuePattern().Value
    except Exception:
        pass
    return None

def main():
    results = []
    for w in auto.GetRootControl().GetChildren():
        nm = w.Name
        if 'Google Chrome' in nm and 'Gemini' in nm:
            hw = w.NativeWindowHandle
            rect = w.BoundingRectangle
            root = auto.ControlFromHandle(hw)
            has_input = False
            url = None
            try:
                for t, d in auto.WalkControl(root, maxDepth=40):
                    if t.ControlTypeName == 'EditControl' and 'prompt for Gemini' in (t.Name or ''):
                        has_input = True
                    if t.ControlTypeName == 'EditControl' and (t.Name or '') == 'Address and search bar':
                        url = t.GetValuePattern().Value
            except Exception:
                pass
            results.append({
                'hwnd': hex(hw), 'title': nm,
                'rect': [rect.left, rect.top, rect.right, rect.bottom],
                'named_input': has_input, 'url': url,
            })
    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()

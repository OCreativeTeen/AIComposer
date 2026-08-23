#!/usr/bin/env python3
"""Navigate the Gemini window's active tab to gemini.google.com/app, then
survey for (a) the 'Enter a prompt for Gemini' EditControl and (b) a
'New chat' button. Prints findings as JSON."""
import sys, time, json
import uiautomation as auto

HWND = int(sys.argv[1]) if len(sys.argv) > 1 else 2032376
w = auto.ControlFromHandle(HWND)
w.SetActive(); time.sleep(0.8)

# address bar -> app
addr = None
for c, d in auto.WalkControl(w, maxDepth=40):
    if c.ControlTypeName == "EditControl" and (c.Name or "").strip() == "Address and search bar":
        addr = c; break
if addr:
    addr.SetFocus(); time.sleep(0.4)
    auto.SendKeys("{Ctrl}a"); time.sleep(0.2)
    auto.SendKeys("gemini.google.com/app"); time.sleep(0.2)
    auto.SendKeys("{Enter}")
    print("navigated address bar -> app")
else:
    print("NO_ADDRESS_BAR")

time.sleep(4.0)
# re-resolve address
addr2 = None
for c, d in auto.WalkControl(w, maxDepth=40):
    if c.ControlTypeName == "EditControl" and (c.Name or "").strip() == "Address and search bar":
        addr2 = c; break
print("ADDRESS now:", addr2.GetValuePattern().Value if addr2 else "??")

input_ctrl = None
newchat = None
for c, d in auto.WalkControl(w, maxDepth=40):
    nm = (c.Name or "").strip()
    if c.ControlTypeName == "EditControl" and "prompt for Gemini" in nm:
        input_ctrl = (c.NativeWindowHandle, nm, c.BoundingRectangle.left, c.BoundingRectangle.top)
    if (c.ControlTypeName == "ButtonControl" or c.ControlTypeName == "HyperlinkControl") and nm.lower() == "new chat":
        newchat = (c.NativeWindowHandle, nm, c.BoundingRectangle.left, c.BoundingRectangle.top)
print("INPUT_EDIT:", input_ctrl)
print("NEW_CHAT:", newchat)
print("RESULT_JSON " + json.dumps({
    "address": addr2.GetValuePattern().Value if addr2 else None,
    "input_found": input_ctrl is not None,
    "newchat_found": newchat is not None,
}, ensure_ascii=False))

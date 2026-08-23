"""Reusable AIComposer workflow helpers (Hermes driver side).

Safe Tk clicking: never use auto.Click / SetTopmost on Tk dialogs (crashes the
GUI). Use SetActive + SetCursorPos + mouse_event(MOUSEDOWN/UP). Always verify by
EFFECT (clipboard / disk), never by assuming the click landed.
"""
import time, ctypes, os
import uiautomation as auto
import win32gui, win32con
import pyperclip

USER32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

def find_root_hwnd():
    for w in auto.GetRootControl().GetChildren():
        nm = w.Name.strip()
        if "AIComposer" in nm and "YT 工具" in nm:
            return w.NativeWindowHandle, nm
    return None, None

def find_detail_hwnd():
    rhwnd, _ = find_root_hwnd()
    if not rhwnd:
        return None, None
    root = auto.ControlFromHandle(rhwnd)
    for c, depth in auto.WalkControl(root, maxDepth=3):
        hw = c.NativeWindowHandle
        nm = c.Name.strip()
        if hw and ("摘要" in nm or "拖入" in nm):
            return hw, nm
    return None, None

def find_panel_hwnd(name_sub="分镜"):
    rhwnd, _ = find_root_hwnd()
    if not rhwnd:
        return None, None
    root = auto.ControlFromHandle(rhwnd)
    for c, depth in auto.WalkControl(root, maxDepth=4):
        hw = c.NativeWindowHandle
        nm = c.Name.strip()
        if hw and name_sub in nm:
            return hw, nm
    return None, None

def bring_front(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.3)

def phys_rect(hwnd):
    ctl = auto.ControlFromHandle(hwnd)
    r = ctl.BoundingRectangle
    return (r.left, r.top, r.right, r.bottom)

def safe_click(hwnd, x, y, hold=0.09, pre_sleep=1.0, post_sleep=0.5):
    """Click at (x,y) in PHYSICAL coords relative to hwnd's BoundingRectangle origin."""
    ctl = auto.ControlFromHandle(hwnd)
    ctl.SetActive()
    time.sleep(pre_sleep)
    r = ctl.BoundingRectangle
    ax, ay = r.left + x, r.top + y
    USER32.SetCursorPos(ax, ay)
    time.sleep(0.35)
    USER32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(hold)
    USER32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(post_sleep)
    return ax, ay

def safe_click_abs(ax, ay, hold=0.09, pre_sleep=1.0, post_sleep=0.5):
    ctl = auto.GetForegroundControl()
    ctl.SetActive()
    time.sleep(pre_sleep)
    USER32.SetCursorPos(ax, ay)
    time.sleep(0.35)
    USER32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(hold)
    USER32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(post_sleep)

def clip_text():
    try:
        return pyperclip.paste()
    except Exception as e:
        return f"<clipboard error: {e}>"

if __name__ == "__main__":
    dhwnd, nm = find_detail_hwnd()
    print("detail hwnd", hex(dhwnd) if dhwnd else None, nm)
    print("rect", phys_rect(dhwnd) if dhwnd else None)

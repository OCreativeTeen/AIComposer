"""把另一个进程的顶层窗口拿到前面。

不改进程的 DPI，也不改窗口大小。cli.win_gui_tasks 在导入时会把
进程改成按显示器缩放，已经打开的 Tk 窗口会被按比例缩小，所以这里不用它。
"""

from __future__ import annotations

import ctypes
import tkinter as tk


def _visible_titles(substr: str) -> list[tuple[int, str]]:
    try:
        import win32gui
    except Exception:
        return []
    found: list[tuple[int, str]] = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
        except Exception:
            return
        if substr in title:
            found.append((int(hwnd), title))

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return []
    return found


def find_workflow_window(project_pid: str = "") -> int:
    """已经打开的魔法工作流。标题里有 pid 时只对上这一条。"""
    wanted = (project_pid or "").strip()
    hits = _visible_titles("魔法工作流")
    if wanted:
        for hwnd, title in hits:
            if wanted in title:
                return hwnd
        untitled = [hwnd for hwnd, title in hits if "|" not in title]
        if len(hits) == 1 and untitled:
            return untitled[0]
        return 0
    if len(hits) == 1:
        return hits[0][0]
    return 0


def find_story_window() -> int:
    """列表里双击打开的故事预览，标题以 STORY | 开头。"""
    for hwnd, title in _visible_titles("STORY |"):
        if (title or "").startswith("STORY"):
            return hwnd
    return 0


def raise_window(hwnd: int) -> bool:
    """当前进程正在前台（用户刚点了按钮）时，把 hwnd 拿到前面。不移动、不缩放。"""
    hwnd = int(hwnd or 0)
    if not hwnd:
        return False
    try:
        import win32con
        import win32gui
    except Exception:
        return False
    try:
        if not win32gui.IsWindow(hwnd):
            return False
    except Exception:
        return False
    user32 = ctypes.windll.user32
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    brought = bool(user32.SetForegroundWindow(hwnd))
    if user32.GetForegroundWindow() != hwnd:
        user32.keybd_event(0x12, 0, 0, 0)
        brought = bool(user32.SetForegroundWindow(hwnd)) or brought
        user32.keybd_event(0x12, 0, 2, 0)
    return brought or user32.GetForegroundWindow() == hwnd


# --- moved from gui/downloader.py: Tk window raise helpers ---
def _drop_topmost(win) -> None:
    try:
        win.attributes("-topmost", False)
    except tk.TclError:
        pass


def _hwnds_for_tk(win) -> list[int]:
    hwnds: list[int] = []
    try:
        import ctypes

        user32 = ctypes.windll.user32
        child = int(win.winfo_id())
        root = int(user32.GetAncestor(child, 2) or 0)  # GA_ROOT
        parent = int(user32.GetParent(child) or 0)
        for h in (root, parent, child):
            if h and h not in hwnds:
                hwnds.append(h)
    except Exception:
        pass
    return hwnds


def _map_tk_window_noactivate(win) -> None:
    """Show a Toplevel without AttachThreadInput / SetForegroundWindow."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        SW_SHOWNOACTIVATE = 4
        SW_SHOW = 5
        HWND_TOPMOST = -1
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        SWP_FRAMECHANGED = 0x0020
        flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED
        for hwnd in _hwnds_for_tk(win):
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            user32.ShowWindow(hwnd, SW_SHOW)
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    except Exception:
        pass


def _force_tk_repaint(win) -> None:
    try:
        win.update_idletasks()
    except tk.TclError:
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        # Invalidate only — RDW_UPDATENOW / UpdateWindow / tk.update() wait for
        # paint while Tk is already on the stack and freeze the bridge pump.
        flags = 0x0001 | 0x0004 | 0x0080 | 0x0400
        for hwnd in _hwnds_for_tk(win):
            user32.InvalidateRect(hwnd, None, True)
            user32.RedrawWindow(hwnd, None, None, flags)
    except Exception:
        pass


def _raise_own_window(win) -> None:
    """Map SCENE/STORY. Activation is done by the CLI process, not here."""
    try:
        win.deiconify()
        win.lift()
        win.attributes("-topmost", True)
        _map_tk_window_noactivate(win)
        _force_tk_repaint(win)
        win.after(80, lambda: _force_tk_repaint(win))
        win.after(400, lambda: _drop_topmost(win))
    except tk.TclError:
        pass

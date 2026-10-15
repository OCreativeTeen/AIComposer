"""Tk clipboard / drag-drop path helpers (moved verbatim from gui/downloader.py)."""
import os
from utility.file_util import safe_clipboard_json_copy, show_auto_close_popup
import tkinter as tk
import tkinter.messagebox as messagebox
from utility.file_util import _collect_unique_file_paths


def _copy_text_to_clipboard(widget, text: str) -> None:
    """写入系统剪贴板（审阅窗打开、指令拷贝等）。"""
    s = (text or "").strip()
    if not s:
        return
    hosts: list = []
    if widget is not None:
        hosts.append(widget)
        try:
            top = widget.winfo_toplevel()
            if top is not widget:
                hosts.append(top)
        except tk.TclError:
            pass
    for w in hosts:
        try:
            w.clipboard_clear()
            w.clipboard_append(s)
            w.update_idletasks()
            return
        except tk.TclError:
            continue


def _dnd_paths_splitlist(master_widget, raw) -> list:
    if raw is None or str(raw).strip() == "":
        return []
    try:
        return list(master_widget.tk.splitlist(str(raw)))
    except tk.TclError:
        return []


def _dnd_normalize_file_paths(
    master_widget, raw, *, allow_duplicates: bool = False
) -> list[str]:
    """拖放路径列表（保持 Explorer 给出的先后顺序）。"""
    out: list[str] = []
    for raw_path in _dnd_paths_splitlist(master_widget, raw):
        p = (raw_path or "").strip()
        if p.startswith("{") and p.endswith("}"):
            p = p[1:-1]
        if p:
            out.append(os.path.normpath(p))
    return _collect_unique_file_paths(
        out, label="拖放", allow_duplicates=allow_duplicates
    )


def _read_host_clipboard_text(clipboard_host) -> str:
    try:
        return safe_clipboard_json_copy(clipboard_host.clipboard_get() or "")
    except tk.TclError:
        return ""


def _copy_file_to_clipboard_hdrop(parent, file_path: str) -> bool:
    """将文件复制到 Windows 剪贴板（CF_HDROP），便于粘贴到资源管理器或其它应用。"""
    import struct

    file_path = (file_path or "").strip()
    if not file_path or not os.path.isfile(file_path):
        messagebox.showwarning("提示", "文件不存在。", parent=parent)
        return False
    abs_path = os.path.normpath(os.path.abspath(file_path))
    try:
        import win32clipboard  # type: ignore

        file_list = abs_path + "\0\0"
        file_list_bytes = file_list.encode("utf-16-le")
        dropfiles_offset = 20
        dropfiles = struct.pack("Iiiii", dropfiles_offset, 0, 0, 0, 1)
        data = dropfiles + file_list_bytes
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_HDROP, data)
        win32clipboard.CloseClipboard()
        return True
    except ImportError:
        messagebox.showwarning(
            "提示",
            "复制文件到剪贴板需要 pywin32。\n请运行: pip install pywin32",
            parent=parent,
        )
        return False
    except Exception as exc:
        show_auto_close_popup(parent, "复制失败", str(exc), kind="error")
        return False

#!/usr/bin/env python3
"""按 topic_category 整理好的列表：内容处理与发布（不含 YouTube 下载/更新）。

运行：python GUI_topic.py

原始下载列表仍用 GUI_pm.py。
"""

import tkinter as tk

from project_manager import show_initial_choice_dialog

try:
    import tkinterdnd2 as TkinterDnD

    _ROOT_FACTORY = TkinterDnD.Tk
except ImportError:
    TkinterDnD = None  # type: ignore
    _ROOT_FACTORY = tk.Tk


def main():
    from cli.gui_session import SOURCE_MANUAL, clear_gui_launch_source, set_gui_launch_source

    set_gui_launch_source(SOURCE_MANUAL)
    root = _ROOT_FACTORY()
    root.title("AIComposer — 主题内容")
    try:
        from gui.cli_bridge import register_bridge_root

        register_bridge_root(root)
    except Exception:
        pass
    try:
        root.geometry("1x1+-3000+-3000")
        root.resizable(False, False)
    except tk.TclError:
        pass

    choice, *_rest = show_initial_choice_dialog(root, content_only=True)

    if choice == "cancel":
        clear_gui_launch_source()
        root.destroy()
        return

    try:
        root.mainloop()
    finally:
        clear_gui_launch_source()
    try:
        root.destroy()
    except tk.TclError:
        pass


if __name__ == "__main__":
    main()

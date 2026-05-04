#!/usr/bin/env python3
"""
YT / 项目管理侧入口（与主工作流 GUI_wf.py 分离）。

运行：python GUI_pm.py

使用顶部频道 / 语言 / 风格 / 旁白 / HOST 与原先的欢迎屏一致，仅提供四个 YT 功能按钮。
从视频详情「启动项目」创建新项目后，请另行运行 GUI_wf.py 并用「选择项目」打开该项目，
避免在同一进程内嵌主界面导致难以关闭的背景窗口。
"""

import tkinter as tk

from project_manager import show_initial_choice_dialog


def main():
    root = tk.Tk()
    root.title("AIComposer — YT 工具")
    # 切勿在此处 withdraw(root)。在 Windows 上父窗口被 withdraw 时，其子 Toplevel（欢迎屏）
    # 往往完全不显示。根窗缩到极小并移到屏外，减少空白主窗干扰。
    try:
        root.geometry("1x1+-3000+-3000")
        root.resizable(False, False)
    except tk.TclError:
        pass

    choice, *_rest = show_initial_choice_dialog(root, for_yt_tools=True)

    if choice == "cancel":
        root.destroy()
        return

    # choice == "yt"：业务对话框关闭后轮询会 quit；此处进入事件循环
    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass


if __name__ == "__main__":
    main()

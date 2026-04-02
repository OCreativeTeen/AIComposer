"""
两级标签菜单：第一层为 feature（如 Structure、Melody），悬停展开第二层选项。
用于 Tk 的「添加标签」按钮弹出。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List


def build_tag_cascade_menu(
    parent,
    tag_features_map: Dict[str, List[str]],
    on_pick: Callable[[str, str], None],
) -> tk.Menu:
    """构建带级联子菜单的 Menu；选择某项时调用 on_pick(feature_name, option_label)。"""
    root = tk.Menu(parent, tearoff=0)
    if not tag_features_map:
        root.add_command(label="（tags.json 无配置或为空）", state="disabled")
        return root
    added_any = False
    for feature in sorted(tag_features_map.keys()):
        options = tag_features_map[feature]
        if not isinstance(options, list) or not options:
            continue
        sub_items = [str(x).strip() for x in options if x is not None and str(x).strip()]
        if not sub_items:
            continue
        sub = tk.Menu(root, tearoff=0)
        root.add_cascade(label=feature, menu=sub)
        for o in sub_items:
            sub.add_command(
                label=o,
                command=lambda f=feature, x=o: on_pick(f, x),
            )
        added_any = True
    if not added_any:
        root.add_command(label="（无有效选项）", state="disabled")
    return root


def post_menu_below_widget(menu: tk.Menu, widget: tk.Widget) -> None:
    """在控件左下角弹出菜单（与 ttk 按钮配合）。"""
    widget.update_idletasks()
    x = widget.winfo_rootx()
    y = widget.winfo_rooty() + widget.winfo_height()
    try:
        menu.tk_popup(int(x), int(y))
    finally:
        try:
            menu.grab_release()
        except tk.TclError:
            pass

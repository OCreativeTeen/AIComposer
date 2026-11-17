"""t268: STORY 预览窗「材料」行里的生成区：叙事方式下拉、步数、共 N 集、五个动作按钮的排版。

以前的做法是 ``pack(after=…)`` 一个接一个挂：窗口刚打开时先挂「共 N 集」，之后才挂分隔线和按钮（它们也 ``after=`` 下拉），
结果「共 N 集」被挤到整行最后；选了叙事方式后重新 ``pack_forget`` + ``pack(after=下拉)`` 才跳回下拉后面。
现在这一行的顺序只由一个函数定：叙事方式下拉 → 步数（故事对话 / 固定步数故事 / 图片分解才有）→ 共 N 集 → 分隔线 → 按钮们；
任何时候（第一次排版、切叙事方式、按钮后来才建好）都是同一个顺序，不会跳。
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import config_channel

# 动作按钮（生成节目 / 人物设置 / 场景生成 / 生成查看 / 整理场景）：t268 比原来大约 30%，标签完整显示。
# 原来：字号 9 粗体、padding (3, 6)、width=6（按字符数定死，汉字比 "0" 宽，「生成节目」被截）。
# 现在：字号 10 粗体、padding (10, 8)，不再定死 width（按字的实际宽度加 padding），所以多长的字都不会被截。
BUTTON_STYLE = "StorySmartGenerate.TButton"
BUTTON_FONT = ("Microsoft YaHei UI", 10, "bold")
BUTTON_PADDING = (10, 8)
OLD_BUTTON_FONT = ("Microsoft YaHei UI", 9, "bold")
OLD_BUTTON_PADDING = (3, 6)
OLD_BUTTON_WIDTH = 6
BUTTON_PADX = (0, 3)
SEPARATOR_PADX = 8


def configure_button_style(style_name: str = BUTTON_STYLE) -> str:
    ttk.Style().configure(style_name, font=BUTTON_FONT, padding=BUTTON_PADDING, width=0)  # width=0：按字的实际宽度（主题默认最少 11 个字符宽）
    return style_name


def step_kind(sel: str):
    """步数下拉管什么：dialogue = 故事对话（0 自由规划 / 1–6 固定场景数）；fixed = FlyLink 固定步数故事（1–6）；
    image = 图片分解（取第几步）；None = 这个提示词不用步数。"""
    if config_channel.is_step_image_label(sel):
        return "image"
    if config_channel.is_step_story_label(sel):
        return "fixed"
    if config_channel.series_style_key(sel) == "story_speak":
        return "dialogue"
    return None


def visible_parts(sel: str) -> dict:
    """这个叙事方式要不要显示「步数」和「共 N 集」。"""
    sel = (sel or "").strip()
    return {
        "step": step_kind(sel) is not None,
        "series": not (config_channel.is_step_image_label(sel) or config_channel.is_scene_summary_image_label(sel)),
    }


class GenRow:
    """一行里按固定顺序排的控件。``add(widget, key, **pack_kw)`` 登记（先后 = 从左到右的顺序），``show(key, bool)`` 开关，
    ``relayout()`` 只在实际顺序和应有顺序不一样时才重新排（不闪）。"""

    def __init__(self, master: tk.Misc) -> None:
        self.master = master
        self.items: list[tuple[tk.Widget, str, dict]] = []
        self.hidden: set[str] = set()

    def add(self, widget: tk.Widget, key: str = "", **pack_kw) -> None:
        pack_kw.setdefault("side", tk.LEFT)
        self.items.append((widget, key or f"w{len(self.items)}", pack_kw))

    def show(self, key: str, on: bool) -> None:
        (self.hidden.discard if on else self.hidden.add)(key)

    def wanted(self) -> list[tk.Widget]:
        return [w for w, key, _kw in self.items if key not in self.hidden]

    def current(self) -> list[tk.Widget]:
        mine = {str(w) for w, _k, _kw in self.items}
        return [w for w in self.master.pack_slaves() if str(w) in mine]

    def relayout(self) -> None:
        want = self.wanted()
        if [str(w) for w in self.current()] == [str(w) for w in want]:
            return
        for w, _key, _kw in self.items:
            w.pack_forget()
        for w, key, kw in self.items:
            if key not in self.hidden:
                w.pack(**kw)


def fit_status_label(row: tk.Misc, label: tk.Widget, *, min_wrap: int = 80, slack: int = 14) -> int:
    """材料行放不下时让状态文字（PDF · 图片 0 · 无媒体）自己换行变窄，而不是把右边的按钮挤出窗口。返回设的 wraplength（0 = 不限）。"""
    try:
        total = row.winfo_width()
        if total <= 1:
            return -1
        others = 0
        for child in row.pack_slaves():
            if child is not label:
                others += child.winfo_reqwidth() + 8
        want = total - others - slack
        wrap = 0 if want >= label.winfo_reqwidth() else max(min_wrap, want)
        if int(float(label.cget("wraplength") or 0)) != wrap:
            label.configure(wraplength=wrap)
        return wrap
    except tk.TclError:
        return -1


def text_width(widget: tk.Widget, text: str, font=None) -> int:
    f = tkfont.Font(root=widget, font=font or BUTTON_FONT)
    return int(f.measure(text))
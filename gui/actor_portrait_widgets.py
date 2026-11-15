# -*- coding: utf-8 -*-
"""t443u: 人物窗共用的部件（魔法工作流「人物」窗 wf_actors._open_portrait_dialog 和 STORY 预览的人物窗都用这一份）。

- PersonEditBlock：性别 / 年龄 / 民族 / 名字 一行，下一行「括号描述」（可写）。
- PortraitBrowser：最上面的大图；左右键翻候选肖像（第 0 张 = 这一位现在的肖像），不换人。
"""
from __future__ import annotations

import os
import tkinter as tk
import tkinter.ttk as ttk

from utility.actor_edit_fields import (
    ACTOR_AGES,
    ACTOR_GENDERS,
    ACTOR_RACES,
    actor_edit_combo_values,
    format_actor_edit_fields,
    parse_actor_edit_fields,
)


class PersonEditBlock(ttk.Frame):
    """性别 / 年龄 / 民族 / 名字，下一行括号描述。和工作流人物窗同一套拆分 / 拼回（utility.actor_edit_fields）。"""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.g, self.a, self.r = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.n, self.note = tk.StringVar(), tk.StringVar()
        self.guard = False
        self.boxes = {}
        row = ttk.Frame(self)
        row.pack()
        for lab, var, vals, w, key in (
            ("性别", self.g, ACTOR_GENDERS, 8, "g"),
            ("年龄", self.a, ACTOR_AGES, 12, "a"),
            ("民族", self.r, ACTOR_RACES, 10, "r"),
        ):
            ttk.Label(row, text=lab).pack(side=tk.LEFT, padx=(0, 4))
            box = ttk.Combobox(row, textvariable=var, values=vals, state="normal", width=w)
            box.pack(side=tk.LEFT, padx=(0, 10))
            self.boxes[key] = box
        ttk.Label(row, text="名字").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(row, textvariable=self.n, width=14).pack(side=tk.LEFT)
        note_row = ttk.Frame(self)
        note_row.pack(pady=(4, 0), fill=tk.X)
        ttk.Label(note_row, text="括号描述").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(note_row, textvariable=self.note, width=52).pack(side=tk.LEFT, fill=tk.X, expand=True)

    @property
    def vars(self) -> tuple:
        return self.g, self.a, self.r, self.n, self.note

    def fill(self, body: str) -> dict:
        fields = parse_actor_edit_fields(body)
        self.guard = True
        try:
            self.g.set(fields["gender"])
            self.a.set(fields["age"])
            self.r.set(fields["race"])
            self.n.set(fields["name"])
            self.note.set(fields["note"])
            self.boxes["g"].configure(values=actor_edit_combo_values(ACTOR_GENDERS, fields["gender"]))
            self.boxes["a"].configure(values=actor_edit_combo_values(ACTOR_AGES, fields["age"]))
            self.boxes["r"].configure(values=actor_edit_combo_values(ACTOR_RACES, fields["race"]))
        finally:
            self.guard = False
        return fields

    def body(self) -> str:
        return format_actor_edit_fields(self.g.get(), self.a.get(), self.r.get(), self.n.get(), self.note.get())

    def ident(self) -> str:
        """不含括号描述（身份：性别/年龄/民族/名字）。"""
        return format_actor_edit_fields(self.g.get(), self.a.get(), self.r.get(), self.n.get(), "")

    def on_change(self, callback) -> None:
        def _cb(*_a):
            if not self.guard:
                callback()

        for v in self.vars:
            v.trace_add("write", _cb)


def focus_in_text_field(win) -> bool:
    """焦点在输入框 / 下拉框里（左右键是移光标）。"""
    try:
        focus = win.focus_get()
    except (KeyError, tk.TclError):
        return False
    return isinstance(focus, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text, tk.Spinbox))


class PortraitBrowser:
    """最上面的大图 + 一行说明。左右键翻：第 0 张 = 这一位现在的肖像，后面是候选图。不换人。"""

    def __init__(self, image_label, caption_var, size=(480, 560)):
        self.label = image_label
        self.caption = caption_var
        self.size = size
        self.photo = None
        self.current = ""
        self.items: list = []
        self.source = ""
        self.pos = -1
        self.empty_text = "没有头像"

    def reset(self, current: str, candidates=(), source: str = "", empty_text: str = "没有头像") -> None:
        self.current = current or ""
        self.items = [p for p in (candidates or []) if p]
        self.source = source or ""
        self.pos = -1
        self.empty_text = empty_text
        self.show()

    def step(self, delta: int) -> bool:
        """翻一张；没有候选就什么都不做，返回 False。"""
        if not self.items:
            return False
        n = len(self.items) + 1
        self.pos = (self.pos + 1 + delta) % n - 1
        self.show()
        return True

    def picked(self) -> str:
        """正在看的候选图（不是现在的肖像）；没有返回 ""。"""
        return self.items[self.pos] if 0 <= self.pos < len(self.items) else ""

    def show(self) -> None:
        path = self.picked() or (self.current if self.pos < 0 else "")
        n = len(self.items)
        more = f"    ← → 翻 {n} 张候选（{self.source}）" if n else "    （没有候选图）"
        if self.pos < 0:
            text = ("现在的肖像：" + os.path.basename(self.current)) if self.current else self.empty_text
            self.caption.set(text + more)
        else:
            self.caption.set(f"候选 {self.pos + 1}/{n}（{self.source}）：{os.path.basename(path)}"
                             "    「用这张」或确认 = 设为这一位的肖像")
        if not path or not os.path.isfile(path):
            self.photo = None
            self.label.configure(image="", text=self.empty_text if self.pos < 0 else os.path.basename(path or ""))
            return
        try:
            from PIL import Image, ImageTk

            with Image.open(path) as im:
                img = im.copy()
            img.thumbnail(self.size, Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(img)
            self.label.configure(image=self.photo, text="")
        except Exception:  # noqa: BLE001
            self.photo = None
            self.label.configure(image="", text=os.path.basename(path))

# -*- coding: utf-8 -*-
"""t436u: 预览窗口里 Ctrl+双击场景 JSON → 看这一场的参考图（ref_images），左右键翻，「选这张」= 移到第一张（就是用它）。
只有 1 张就只看；没有就不打开。"""
from __future__ import annotations

import json


def scene_index_at(json_text: str, offset: int) -> int:
    """场景 JSON（一个 list）里，第 offset 个字落在第几场（0 起）；不在任何一场里 / JSON 不对 → -1。"""
    text = json_text or ""
    dec = json.JSONDecoder()
    i = 0
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n or text[i] != "[":
        return -1
    i += 1
    idx = 0
    while i < n:
        while i < n and (text[i].isspace() or text[i] == ","):
            i += 1
        if i >= n or text[i] == "]":
            return -1
        try:
            _obj, end = dec.raw_decode(text, i)
        except ValueError:
            return -1
        if i <= offset < end:
            return idx
        if offset < i:
            return -1
        idx += 1
        i = end
    return -1


def review_paths(scene) -> list:
    """这一场还在磁盘上的参考图（第一张 = 现在用的）。"""
    from utility.project_ref_images import scene_ref_paths

    return scene_ref_paths(scene) if isinstance(scene, dict) else []


def pick_ref_image(scene: dict, path: str) -> list:
    """选这张：移到 ref_images 第一张。"""
    from utility.project_ref_images import select_ref_image

    return select_ref_image(scene, path)


def open_ref_image_review(parent, scene: dict, on_pick=None, *, title: str = "参考图") -> bool:
    """打开看图窗口。没有参考图返回 False（不打开）。选了一张就改 scene 并调 on_pick(scene)。"""
    import tkinter as tk
    import tkinter.ttk as ttk

    paths = review_paths(scene)
    if not paths:
        return False
    state = {"i": 0, "photo": None}
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    head = tk.StringVar()
    ttk.Label(win, textvariable=head).pack(anchor=tk.W, padx=10, pady=(8, 4))
    img_lbl = ttk.Label(win)
    img_lbl.pack(padx=10, pady=4)
    bar = ttk.Frame(win)
    bar.pack(fill=tk.X, padx=10, pady=(4, 10))

    def _show():
        i = state["i"]
        p = paths[i]
        tag = "（现在用的）" if i == 0 else ""
        head.set(f"第 {i + 1} / {len(paths)} 张{tag}：{p}")
        try:
            from PIL import Image, ImageTk

            im = Image.open(p)
            im = im.convert("RGB") if im.mode not in ("RGB", "RGBA") else im
            im.thumbnail((960, 640))
            state["photo"] = ImageTk.PhotoImage(im)
            img_lbl.configure(image=state["photo"], text="")
        except Exception as exc:  # noqa: BLE001
            state["photo"] = None
            img_lbl.configure(image="", text=f"打不开图片：{exc}")
        if len(paths) > 1:
            pick_btn.configure(state=(tk.DISABLED if i == 0 else tk.NORMAL))

    def _move(step):
        state["i"] = (state["i"] + step) % len(paths)
        _show()

    def _pick():
        pick_ref_image(scene, paths[state["i"]])
        win.destroy()
        if callable(on_pick):
            on_pick(scene)

    if len(paths) > 1:
        ttk.Button(bar, text="◀ 上一张", command=lambda: _move(-1)).pack(side=tk.LEFT)
        ttk.Button(bar, text="下一张 ▶", command=lambda: _move(1)).pack(side=tk.LEFT, padx=6)
        pick_btn = ttk.Button(bar, text="选这张", command=_pick)
        pick_btn.pack(side=tk.LEFT, padx=12)
        win.bind("<Left>", lambda _e: _move(-1))
        win.bind("<Right>", lambda _e: _move(1))
        win.bind("<Return>", lambda _e: _pick() if state["i"] else None)
    else:
        pick_btn = None
        ttk.Label(bar, text="只有这一张参考图（只能看）").pack(side=tk.LEFT)
    ttk.Button(bar, text="关闭", command=win.destroy).pack(side=tk.RIGHT)
    win.bind("<Escape>", lambda _e: win.destroy())
    _show()
    win.focus_set()
    return True

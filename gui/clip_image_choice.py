"""Start / end image picker for the scene prompt dialogs (图片提示, 生场视频).

Two small thumbnails (clip_image and clip_image_last), each with a radio button.
The dialogs remember the choice in their own project-config prefs (key "image");
when the saved slot has no file in this scene, clip_image is used for this open only.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

THUMB_W, THUMB_H = 96, 60
SLOTS = (("clip_image", "起始图"), ("clip_image_last", "结束图"))


def _thumb(path: str):
    try:
        from PIL import Image, ImageTk

        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((THUMB_W, THUMB_H))
            return ImageTk.PhotoImage(img)
    except Exception:
        return None


def pack_clip_image_choice(parent, get_path, *, title: str = "交给 LLM 的图", side=tk.LEFT, initial: str = "clip_image"):
    """Pack the picker into ``parent``. ``get_path(key)`` returns the file for clip_image / clip_image_last.

    Returns ``(frame, chosen, to_save)``: ``chosen()`` is the selected key ("clip_image" or
    "clip_image_last"); ``to_save()`` is the value to remember, which keeps ``initial`` when it
    was unavailable in this scene and the user did not pick anything else.
    """
    if initial not in dict(SLOTS):
        initial = "clip_image"
    box = ttk.LabelFrame(parent, text=title, padding=(8, 4))
    box.pack(side=side, anchor=tk.S, padx=(8, 0))
    var = tk.StringVar(master=box, value="clip_image")
    photos = []
    available = set()
    for col, (key, label) in enumerate(SLOTS):
        try:
            path = get_path(key) or ""
        except Exception:
            path = ""
        ok = bool(path) and os.path.isfile(path)
        if ok:
            available.add(key)
        tile = tk.Frame(box, width=THUMB_W, height=THUMB_H, bg="#dddddd")
        tile.grid(row=0, column=col, padx=(0 if col == 0 else 8, 0))
        tile.pack_propagate(False)
        photo = _thumb(path) if ok else None
        if photo is not None:
            photos.append(photo)
            tk.Label(tile, image=photo, bg="#dddddd", bd=0).pack(fill=tk.BOTH, expand=True)
        else:
            tk.Label(tile, text="无" if not ok else label, bg="#dddddd", fg="gray40").pack(fill=tk.BOTH, expand=True)
        ttk.Radiobutton(
            box, text=label, value=key, variable=var, state=("normal" if ok else "disabled")
        ).grid(row=1, column=col, padx=(0 if col == 0 else 8, 0), sticky="w")
    if initial in available:
        var.set(initial)
    box._photos = photos  # keep references
    box._choice_var = var

    def to_save() -> str:
        picked = var.get()
        if initial not in available and picked == "clip_image":
            return initial  # fell back for this scene only; keep the saved choice
        return picked

    return box, var.get, to_save

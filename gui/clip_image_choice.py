"""Start / end image picker for the scene prompt dialogs (图片提示, 生场视频).

Four thumbnails: clip_image, clip_image_last, zero_image, zero_image_last.
The dialogs remember the choice in their own project-config prefs (key "image");
when the saved slot has no file in this scene, clip_image is used for this open only.
Dual-frame video prompts still send clip_image + clip_image_last (see
resolve_video_prompt_images); the picker is for single-frame mode.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from utility.scene_image_slots import IMAGE_CHOICE_LABELS, normalize_image_choice

THUMB_W, THUMB_H = 96, 60
SLOTS = IMAGE_CHOICE_LABELS


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
    """Pack the picker into ``parent``. ``get_path(key)`` returns a slot file.

    Returns ``(frame, chosen, to_save)``: ``chosen()`` is the selected key
    (one of clip_image / clip_image_last / zero_image / zero_image_last);
    ``to_save()`` keeps ``initial`` when it was unavailable in this scene
    and the user did not pick anything else.
    """
    initial = normalize_image_choice(initial)
    box = ttk.LabelFrame(parent, text=title, padding=(8, 4))
    box.pack(side=side, anchor=tk.S, padx=(8, 0))
    var = tk.StringVar(master=box, value="clip_image")
    photos = []
    available = set()
    for i, (key, label) in enumerate(SLOTS):
        row, col = divmod(i, 2)
        try:
            path = get_path(key) or ""
        except Exception:
            path = ""
        ok = bool(path) and os.path.isfile(path)
        if ok:
            available.add(key)
        tile = tk.Frame(box, width=THUMB_W, height=THUMB_H, bg="#dddddd")
        tile.grid(row=row * 2, column=col, padx=(0 if col == 0 else 8, 0), pady=(0 if row == 0 else 4, 0))
        tile.pack_propagate(False)
        photo = _thumb(path) if ok else None
        if photo is not None:
            photos.append(photo)
            tk.Label(tile, image=photo, bg="#dddddd", bd=0).pack(fill=tk.BOTH, expand=True)
        else:
            tk.Label(tile, text="无" if not ok else label, bg="#dddddd", fg="gray40").pack(fill=tk.BOTH, expand=True)
        ttk.Radiobutton(
            box, text=label, value=key, variable=var, state=("normal" if ok else "disabled")
        ).grid(row=row * 2 + 1, column=col, padx=(0 if col == 0 else 8, 0), sticky="w")
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

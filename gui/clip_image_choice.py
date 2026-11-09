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


COVER_PREVIEW_W, COVER_PREVIEW_H = 160, 100


def _thumb(path: str, width: int = THUMB_W, height: int = THUMB_H):
    try:
        from PIL import Image, ImageTk

        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((width, height))
            return ImageTk.PhotoImage(img)
    except Exception:
        return None


def pack_project_cover_preview(parent, path, *, paths=None, title: str = "项目封面（提交给 LLM）", side=tk.LEFT):
    """Preview the project cover(s) for 从封面提取 (no four-slot picker).

    One file: a single larger preview. Several files: larger aspect-aware
    previews with click/radio selection. Selecting does not change the
    project's stored primary cover; it only chooses what this extract uses.
    """
    from utility.scene_image_slots import cover_preview_max_size, normalize_cover_preview_choices

    raw = list(paths) if paths is not None else ([path] if path else [])
    items, selected = normalize_cover_preview_choices(raw, path)
    box = ttk.LabelFrame(parent, text=title, padding=(8, 4))
    box.pack(side=side, anchor=tk.S, padx=(8, 0))
    photos = []
    cells = []

    def _paint(sel: str) -> None:
        box._cover_path = sel
        for cell, item_path in cells:
            on = os.path.normcase(item_path) == os.path.normcase(sel) if sel else False
            try:
                cell.configure(
                    highlightbackground="#1f5fbf" if on else "#cccccc",
                    highlightthickness=3 if on else 1,
                )
            except tk.TclError:
                pass

    def _pick(item_path: str) -> None:
        if var is not None:
            var.set(item_path)
        _paint(item_path)

    if not items:
        tile = tk.Frame(box, width=COVER_PREVIEW_W, height=COVER_PREVIEW_H, bg="#dddddd")
        tile.pack()
        tile.pack_propagate(False)
        tk.Label(tile, text="没有可用的项目封面", bg="#dddddd", fg="gray40").pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            box, text="不会改用场景里选中的图", foreground="gray40", wraplength=180
        ).pack(anchor=tk.W, pady=(4, 0))
        box._photos = photos
        box._cover_path = ""
        return box

    var = tk.StringVar(master=box, value=selected) if len(items) > 1 else None
    row = ttk.Frame(box)
    row.pack(anchor=tk.W)
    for i, item_path in enumerate(items):
        max_w, max_h = cover_preview_max_size(item_path)
        cell = tk.Frame(row, bg="#dddddd", highlightthickness=1, highlightbackground="#cccccc")
        # 16:9 横图并排；9:16 竖图也并排，方便对比
        cell.pack(side=tk.LEFT, padx=(0 if i == 0 else 10, 0), anchor=tk.N)
        cells.append((cell, item_path))
        inner = tk.Frame(cell, width=max_w, height=max_h, bg="#dddddd")
        inner.pack(padx=4, pady=4)
        inner.pack_propagate(False)
        photo = _thumb(item_path, max_w, max_h)
        if photo is not None:
            photos.append(photo)
            img = tk.Label(inner, image=photo, bg="#dddddd", bd=0, cursor="hand2")
        else:
            img = tk.Label(inner, text=os.path.basename(item_path), bg="#dddddd", fg="gray40", cursor="hand2")
        img.pack(fill=tk.BOTH, expand=True)
        img.bind("<Button-1>", lambda _e, p=item_path: _pick(p))
        label = os.path.basename(item_path)
        if len(items) > 1:
            ttk.Radiobutton(
                cell, text=f"{i + 1}/{len(items)}  {label}", value=item_path, variable=var,
                command=lambda p=item_path: _pick(p),
            ).pack(anchor=tk.W, padx=4, pady=(0, 4))
        else:
            ttk.Label(cell, text=label, wraplength=max(180, max_w)).pack(anchor=tk.W, padx=4, pady=(0, 4))
    _paint(selected)
    box._photos = photos
    box._cover_path = selected
    return box


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

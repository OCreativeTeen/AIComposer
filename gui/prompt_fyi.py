"""FYI / 注意 notes for picture and video prompt dialogs.

Text is persisted in each dialog's project-config choice dict (key "fyi").
The include checkbox defaults ON every open; unchecked only skips this run.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


FYI_SEPARATOR = "\n\n---\n\n"


def clean_fyi_text(saved) -> str:
    if isinstance(saved, dict):
        raw = saved.get("fyi")
    else:
        raw = saved
    if not isinstance(raw, str):
        return ""
    return raw.strip()


def prepend_fyi(prompt: str, fyi_text: str, *, include: bool) -> str:
    """Put FYI at the very top of the assembled prompt when include is on."""
    body = (prompt or "").strip()
    note = (fyi_text or "").strip()
    if not include or not note:
        return body
    header = "注意 / FYI\n" + note
    if not body:
        return header
    return header + FYI_SEPARATOR + body


def pack_fyi_note(parent, *, initial_text: str = "", pady=(8, 0)):
    """Multiline FYI box + include checkbox (default ON).

    Returns ``(frame, get_text, include_var)``.
    ``get_text()`` is the current note (stripped). Checkbox is always
    checked on open; callers should not restore an unchecked state.
    """
    box = ttk.LabelFrame(parent, text="注意 / FYI", padding=(8, 4))
    box.pack(fill=tk.X, pady=pady)

    include_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        box,
        text="写入提示词（放在最前面）",
        variable=include_var,
    ).pack(anchor=tk.W)

    text = tk.Text(box, height=3, width=72, wrap=tk.WORD)
    text.pack(fill=tk.X, pady=(4, 0))
    if initial_text:
        text.insert("1.0", initial_text)

    def get_text() -> str:
        return text.get("1.0", "end-1c").strip()

    return box, get_text, include_var

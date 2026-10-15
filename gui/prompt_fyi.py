"""FYI / 注意 notes for picture and video prompt dialogs.

Persisted per dialog in project config as ``fyi_history``: a list of at most
FYI_MAX strings, newest first (index 0 is shown by default). Old configs with a
single ``fyi`` string are migrated to ``[that string]``.
The include checkbox defaults ON every open; unchecked only skips this run.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


FYI_SEPARATOR = "\n\n---\n\n"
FYI_MAX = 6


def _normalize(items) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s and s not in out:
            out.append(s)
    return out[:FYI_MAX]


def clean_fyi_history(saved) -> list[str]:
    """Return FYI history (newest first, <= FYI_MAX) from a saved choice dict."""
    if isinstance(saved, dict):
        hist = saved.get("fyi_history")
        if isinstance(hist, list):
            return _normalize(hist)
        return _normalize([saved.get("fyi")])
    if isinstance(saved, list):
        return _normalize(saved)
    return _normalize([saved])


def clean_fyi_text(saved) -> str:
    """Current (newest) FYI text."""
    hist = clean_fyi_history(saved)
    return hist[0] if hist else ""


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


def _label(i: int, text: str) -> str:
    first = (text.strip().splitlines() or [""])[0]
    if len(first) > 40:
        first = first[:40] + "…"
    return f"{i + 1}. {first or '(空)'}"


def pack_fyi_note(parent, *, history=None, initial_text: str = "", pady=(8, 0)):
    """FYI history combobox + 新增 button + editor + include checkbox (default ON).

    Returns ``(frame, get_text, include_var, get_history)``.
    ``get_text()`` is the selected/edited note. ``get_history()`` returns the
    list to save: edited entry written back to its slot, then moved to front,
    empties dropped, capped at FYI_MAX.
    """
    entries = list(_normalize(history if history is not None else [initial_text]))
    if not entries:
        entries = [""]
    state = {"idx": 0}

    box = ttk.LabelFrame(parent, text="注意 / FYI", padding=(8, 4))
    box.pack(fill=tk.X, pady=pady)

    top = ttk.Frame(box)
    top.pack(fill=tk.X)
    include_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(top, text="写入提示词（放在最前面）", variable=include_var).pack(side=tk.LEFT)

    row = ttk.Frame(box)
    row.pack(fill=tk.X, pady=(4, 0))
    ttk.Label(row, text="历史：").pack(side=tk.LEFT)
    combo_var = tk.StringVar()
    combo = ttk.Combobox(row, textvariable=combo_var, state="readonly", width=56)
    combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    text = tk.Text(box, height=3, width=72, wrap=tk.WORD)
    text.pack(fill=tk.X, pady=(4, 0))

    def commit() -> None:
        entries[state["idx"]] = text.get("1.0", "end-1c").strip()

    def refresh() -> None:
        combo["values"] = [_label(i, e) for i, e in enumerate(entries)]
        combo.current(state["idx"])

    def load(idx: int) -> None:
        state["idx"] = idx
        text.delete("1.0", tk.END)
        text.insert("1.0", entries[idx])
        refresh()

    def on_select(_event=None) -> None:
        commit()
        load(combo.current())

    def on_new() -> None:
        commit()
        entries.insert(0, "")
        del entries[FYI_MAX:]
        load(0)
        text.focus_set()

    ttk.Button(row, text="新增", command=on_new).pack(side=tk.LEFT, padx=(6, 0))
    combo.bind("<<ComboboxSelected>>", on_select)
    text.bind("<KeyRelease>", lambda _e: (commit(), refresh()))
    load(0)

    def get_text() -> str:
        return text.get("1.0", "end-1c").strip()

    def get_history() -> list[str]:
        commit()
        idx = state["idx"]
        ordered = [entries[idx]] + [e for i, e in enumerate(entries) if i != idx]
        return _normalize(ordered)

    return box, get_text, include_var, get_history
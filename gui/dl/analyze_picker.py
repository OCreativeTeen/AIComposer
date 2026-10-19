"""分析报告：选分析方式（频道的 analyze_prompt 选项）和结果放法（替换 / 追加）。"""

import tkinter as tk
import tkinter.ttk as ttk

RESULT_CHOICES = (
    ("replace", "替换分析报告"),
    ("append", "追加到分析报告末尾"),
)


def resolve_choice(options: list, saved=None) -> dict:
    """上次的选择（{key, mode}）对上现在的选项；对不上用第一项 + 替换。"""
    saved = saved if isinstance(saved, dict) else {}
    keys = [o.get("key") for o in (options or []) if isinstance(o, dict)]
    key = saved.get("key") if saved.get("key") in keys else (keys[0] if keys else "")
    mode = saved.get("mode") if saved.get("mode") in {k for k, _ in RESULT_CHOICES} else "replace"
    return {"key": key, "mode": mode}


def ask_analyze_choice(parent, options: list, *, saved=None, title: str = "分析", source_label: str = "") -> dict | None:
    """弹窗选分析方式和结果放法。点「开始」返回 {key, label, mode}，取消返回 None。只有一种方式时也照样显示。"""
    options = [o for o in (options or []) if isinstance(o, dict) and o.get("key")]
    if not options:
        return None
    start = resolve_choice(options, saved)
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.resizable(False, False)
    frm = ttk.Frame(dlg, padding=12)
    frm.pack(fill=tk.BOTH, expand=True)
    if source_label:
        ttk.Label(frm, text=f"原始材料：{source_label}", wraplength=420, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))
    key_var = tk.StringVar(value=start["key"])
    mode_var = tk.StringVar(value=start["mode"])
    box = ttk.LabelFrame(frm, text="分析方式", padding=8)
    box.pack(fill=tk.X)
    for o in options:
        ttk.Radiobutton(box, text=o.get("label") or o["key"], value=o["key"], variable=key_var).pack(anchor=tk.W, pady=1)
    res = ttk.LabelFrame(frm, text="结果", padding=8)
    res.pack(fill=tk.X, pady=(8, 0))
    for value, label in RESULT_CHOICES:
        ttk.Radiobutton(res, text=label, value=value, variable=mode_var).pack(anchor=tk.W, pady=1)
    out = [None]

    def go(_e=None):
        key = key_var.get()
        label = next((o.get("label") or key for o in options if o["key"] == key), key)
        out[0] = {"key": key, "label": label, "mode": mode_var.get()}
        dlg.destroy()

    row = ttk.Frame(frm)
    row.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(row, text="开始", command=go).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)
    dlg.bind("<Return>", go)
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    try:
        dlg.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - dlg.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - dlg.winfo_height()) // 3)
        dlg.geometry(f"+{x}+{y}")
        dlg.grab_set()
    except tk.TclError:
        pass
    dlg.wait_window()
    return out[0]

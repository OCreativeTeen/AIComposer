# -*- coding: utf-8 -*-
"""t275: 用 PDF 生成场景之前问用户：怎么用这份 PDF。

- 一页一个场景（page）：选中的每一页当成一张图，一页一个场景（n 页 = n 场），步数不用（t272 / t273 那条路）；
  生成后第 k 页直接对第 k 场的配图，不再用 Strata 判断。
- 把 PDF 当文字内容（text）：提取选中页的文字，当作「分析内容」（和分析内容走同一个场景提示词：
  gui.dl.prompts_notebooklm 的 _combined_prompt_text_for_label / _build_notebooklm_prompt_for_row，content_override = 这段文字），
  按整个故事来理解生成场景；步数照用，场景数不等于页数。

上一次的选择记在这一条（video_detail["scene_pdf_mode"]），当作默认选中，但每次生成都还是要问。
"""
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk

MODE_KEY = "scene_pdf_mode"
MODE_PAGE = "page"
MODE_TEXT = "text"

TITLE = "场景生成 · PDF"
QUESTION = "这份 PDF 要怎么生成场景？"
BTN_PAGE = "一页一个场景"
BTN_TEXT = "把 PDF 当文字内容"
BTN_CANCEL = "取消"
NO_TEXT_NOTE = "选中的页里提取不到文字（可能是扫描图 / 漫画页），建议选「一页一个场景」。"
NO_TEXT_WARN = (
    "这份 PDF 选中的页里提取不到文字（可能是扫描图或漫画页）。\n\n"
    "请改选「一页一个场景」：每一页当成一张图来生成场景。"
)


def desc_page(n_pages: int) -> str:
    n = max(0, int(n_pages or 0))
    return f"每一页当成一张图，一页生成一个场景（{n} 页 = {n} 场）。步数不用。"


def desc_text(range_text: str, chars: int = 0) -> str:
    got = f"（提取到约 {int(chars)} 字）" if chars else ""
    return f"提取{range_text}的文字，当成分析内容，按整个故事来理解后生成场景{got}。步数照用，场景数不一定等于页数。"


def remembered_mode(video_detail) -> str:
    """这一条上一次选的方式；没有记过 = 一页一个场景。"""
    v = str((video_detail or {}).get(MODE_KEY) or "").strip().lower() if isinstance(video_detail, dict) else ""
    return MODE_TEXT if v == MODE_TEXT else MODE_PAGE


def remember_mode(video_detail, mode: str) -> None:
    if isinstance(video_detail, dict):
        video_detail[MODE_KEY] = MODE_TEXT if mode == MODE_TEXT else MODE_PAGE


def default_mode(last: str, has_text: bool) -> str:
    """Enter / 默认选中：上一次选的；上一次是「当文字内容」但这次提取不到文字 → 一页一个场景。"""
    return MODE_TEXT if (last == MODE_TEXT and has_text) else MODE_PAGE


def ask_pdf_scene_mode(parent, *, pdf_name: str, range_text: str, pages: int, text_chars: int, last: str = MODE_PAGE) -> str:
    """弹窗问用户。返回 "page" / "text"；取消 / Esc 返回空串。
    选了「把 PDF 当文字内容」但这几页提取不到文字：提示并留在窗口里让用户改选。"""
    box = tk.Toplevel(parent)
    box.title(TITLE)
    box.transient(parent)
    box.resizable(False, False)
    res = {"v": ""}
    has_text = int(text_chars or 0) > 0
    ttk.Label(box, text=QUESTION, font=("Microsoft YaHei UI", 11)).pack(padx=20, pady=(14, 2))
    ttk.Label(box, text=f"{pdf_name}（{range_text}，共 {int(pages)} 页）", foreground="gray40").pack(padx=20, pady=(0, 8))

    def pick(mode: str) -> None:
        if mode == MODE_TEXT and not has_text:
            messagebox.showwarning(TITLE, NO_TEXT_WARN, parent=box)
            return
        res["v"] = mode
        box.destroy()

    body = ttk.Frame(box)
    body.pack(padx=20, pady=(0, 6), fill=tk.X)
    btns = {}
    for mode, text, desc in (
        (MODE_PAGE, BTN_PAGE, desc_page(pages)),
        (MODE_TEXT, BTN_TEXT, desc_text(range_text, text_chars)),
    ):
        btns[mode] = ttk.Button(body, text=text, width=18, command=lambda m=mode: pick(m))
        btns[mode].grid(row=len(btns) - 1, column=0, sticky="w", pady=4)
        ttk.Label(body, text=desc, foreground="gray40", wraplength=360, justify=tk.LEFT).grid(
            row=len(btns) - 1, column=1, sticky="w", padx=(10, 0)
        )
    if not has_text:
        ttk.Label(box, text=NO_TEXT_NOTE, foreground="#a05000", wraplength=520, justify=tk.LEFT).pack(padx=20, pady=(0, 6))
    ttk.Button(box, text=BTN_CANCEL, width=8, command=box.destroy).pack(pady=(4, 14))
    default = default_mode(last, has_text)
    box.bind("<Escape>", lambda _e: box.destroy())
    box.bind("<Return>", lambda _e: pick(default))
    btns[default].focus_set()
    try:
        btns[default].configure(default="active")
    except tk.TclError:
        pass
    box.update_idletasks()
    try:
        x = parent.winfo_rootx() + (parent.winfo_width() - box.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - box.winfo_height()) // 3
        box.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass
    box.grab_set()
    parent.wait_window(box)
    return res["v"]

"""t168u: 「生成查看」大窗：三步看历史生成的 名字 → 摘要 → 场景，各选一个。

数据来自 gui.dl.gen_history（只读）。选中后调用方传进来的 on_title / on_summary / on_scenes 去写回、保存。
"""
from __future__ import annotations

import json
import tkinter as tk
import tkinter.ttk as ttk

from gui.dl import gen_history

_FONT = ("Microsoft YaHei UI", 11)
_FONT_BIG = ("Microsoft YaHei UI", 15, "bold")
_FONT_META = ("Microsoft YaHei UI", 9)


_ACTIVE_CANVAS = [None]


def _wheel(e):
    c = _ACTIVE_CANVAS[0]
    if c is None:
        return
    try:
        c.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
    except tk.TclError:
        pass


def _scrollable(parent):
    """竖向可滚动的 Frame。返回 (outer, inner)。"""
    outer = ttk.Frame(parent)
    canvas = tk.Canvas(outer, highlightthickness=0)
    vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    _ACTIVE_CANVAS[0] = canvas
    return outer, inner


def _meta(entry: dict) -> str:
    if entry.get("run") == "当前":
        return "当前"
    return f"第 {entry.get('run')} 次 · {gen_history.display_backend(entry.get('backend'))} · {entry.get('time') or ''}"


def scenes_readable(scenes) -> str:
    lines = []
    for i, sc in enumerate(scenes or [], 1):
        if not isinstance(sc, dict):
            continue
        lines.append(f"━━ 场景 {i}" + (f"：{sc.get('caption')}" if sc.get("caption") else ""))
        for key, label in (("speaking", "说话"), ("visual", "画面"), ("actor", "人物")):
            v = sc.get(key)
            if v in (None, "", []):
                continue
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            lines.append(f"【{label}】{v}")
        for k, v in sc.items():
            if k in ("caption", "speaking", "visual", "actor") or v in (None, "", []):
                continue
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            lines.append(f"【{k}】{v}")
        lines.append("")
    return "\n".join(lines)


def open_gen_review(parent, video_detail, *, current_title="", current_summary="", current_scenes=None,
                    on_title=None, on_summary=None, on_scenes=None):
    path = gen_history.history_path(video_detail)
    hist = gen_history.load(path)
    titles = list(hist["titles"])
    if current_title and current_title not in {t.get("title") for t in titles}:
        titles.insert(0, {"run": "当前", "title": current_title})
    summaries = list(hist["summaries"])
    if current_summary and current_summary.strip() not in {(s.get("text") or "").strip() for s in summaries}:
        summaries.insert(0, {"run": "当前", "text": current_summary})
    sets = list(hist["scene_sets"])
    cur = [s for s in (current_scenes or []) if isinstance(s, dict)]
    if cur and json.dumps(cur, ensure_ascii=False, sort_keys=True) not in {
        json.dumps(s.get("scenes"), ensure_ascii=False, sort_keys=True) for s in sets
    }:
        sets.insert(0, {"run": "当前", "scenes": cur})

    dlg = tk.Toplevel(parent)
    dlg.title("生成查看")
    dlg.transient(parent)
    dlg.geometry("1200x850")
    dlg.minsize(700, 500)
    dlg.resizable(True, True)
    head = ttk.Label(dlg, text="", font=("Microsoft YaHei UI", 13, "bold"))
    head.pack(anchor="w", padx=14, pady=(10, 2))
    note = ttk.Label(dlg, text="", foreground="#555555")
    note.pack(anchor="w", padx=14, pady=(0, 6))
    body = ttk.Frame(dlg)
    body.pack(fill=tk.BOTH, expand=True, padx=14)
    nav = ttk.Frame(dlg)
    nav.pack(fill=tk.X, padx=14, pady=10)
    step = [0]
    page = [0]

    def _done_msg(msg):
        note.config(text=msg, foreground="#0a6b0a")

    def _clear():
        _ACTIVE_CANVAS[0] = None
        for w in body.winfo_children():
            w.destroy()

    def _step_titles():
        head.config(text="第 1 步 / 3：名字")
        note.config(text=f"共 {len(titles)} 个名字。点「选这个」写进名称栏并保存，然后到下一步。", foreground="#555555")
        if not titles:
            ttk.Label(body, text="还没有名字的生成记录。", font=_FONT).pack(anchor="w", pady=20)
            return
        outer, inner = _scrollable(body)
        outer.pack(fill=tk.BOTH, expand=True)
        for t in titles:
            row = ttk.Frame(inner, padding=(8, 10))
            row.pack(fill=tk.X)
            ttk.Button(row, text="选这个", width=10,
                       command=lambda n=t.get("title", ""): _pick_title(n)).pack(side=tk.RIGHT, padx=8)
            ttk.Label(row, text=t.get("title", ""), font=_FONT_BIG).pack(anchor="w")
            ttk.Label(row, text=_meta(t), font=_FONT_META, foreground="#777777").pack(anchor="w")
            ttk.Separator(inner).pack(fill=tk.X)

    def _pick_title(name):
        if callable(on_title) and name:
            on_title(name)
        _done_msg(f"已选名字：{name}")
        _go(1)

    def _step_summaries():
        head.config(text="第 2 步 / 3：摘要")
        note.config(text=f"共 {len(summaries)} 个摘要，上下滚动看全文。点「选这个」写进摘要框并保存。", foreground="#555555")
        if not summaries:
            ttk.Label(body, text="还没有摘要的生成记录。", font=_FONT).pack(anchor="w", pady=20)
            return
        outer, inner = _scrollable(body)
        outer.pack(fill=tk.BOTH, expand=True)
        for s in summaries:
            box = ttk.Frame(inner, padding=(8, 10))
            box.pack(fill=tk.X)
            top = ttk.Frame(box)
            top.pack(fill=tk.X)
            ttk.Label(top, text=_meta(s), font=_FONT_META, foreground="#777777").pack(side=tk.LEFT)
            ttk.Button(top, text="选这个", width=10,
                       command=lambda x=s.get("text", ""): _pick_summary(x)).pack(side=tk.RIGHT, padx=8)
            text = s.get("text", "")
            h = min(30, max(3, len(text) // 60 + text.count("\n") + 1))
            tw = tk.Text(box, wrap=tk.WORD, height=h, font=_FONT, relief="flat", background="#fafafa")
            tw.insert("1.0", text)
            tw.config(state=tk.DISABLED)
            tw.pack(fill=tk.X, pady=(4, 0))
            ttk.Separator(inner).pack(fill=tk.X, pady=(6, 0))

    def _pick_summary(text):
        if callable(on_summary) and text:
            on_summary(text)
        _done_msg("已选摘要。")
        _go(2)

    def _step_scenes():
        head.config(text="第 3 步 / 3：场景")
        if not sets:
            note.config(text="还没有场景的生成记录。", foreground="#555555")
            return
        page[0] = max(0, min(page[0], len(sets) - 1))
        cur_set = sets[page[0]]
        note.config(text=f"版本 {page[0] + 1} / {len(sets)}　{_meta(cur_set)}　·　{len(cur_set.get('scenes') or [])} 场。"
                         "用 ◀ ▶ 翻看各次生成。", foreground="#555555")
        bar = ttk.Frame(body)
        bar.pack(fill=tk.X, pady=(0, 6))
        prev_b = ttk.Button(bar, text="◀ 上一个版本", command=lambda: _page(-1))
        prev_b.pack(side=tk.LEFT)
        next_b = ttk.Button(bar, text="下一个版本 ▶", command=lambda: _page(1))
        next_b.pack(side=tk.LEFT, padx=6)
        if page[0] == 0:
            prev_b.state(["disabled"])
        if page[0] >= len(sets) - 1:
            next_b.state(["disabled"])
        ttk.Button(bar, text="选这个版本", command=lambda: _pick_scenes(cur_set.get("scenes") or [])).pack(side=tk.RIGHT)
        frm = ttk.Frame(body)
        frm.pack(fill=tk.BOTH, expand=True)
        tw = tk.Text(frm, wrap=tk.WORD, font=_FONT)
        vsb = ttk.Scrollbar(frm, orient="vertical", command=tw.yview)
        tw.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        tw.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tw.insert("1.0", scenes_readable(cur_set.get("scenes")))
        tw.config(state=tk.DISABLED)

    def _page(d):
        page[0] += d
        _render()

    def _pick_scenes(scenes):
        """t170u: 写入并保存成功就关窗；失败留着窗口显示原因。"""
        if not (callable(on_scenes) and scenes):
            return
        try:
            res = on_scenes(scenes)
        except Exception as exc:  # noqa: BLE001
            res = (False, str(exc))
        ok, msg = res if isinstance(res, tuple) else (res is not False, "")
        if ok:
            _close()
            return
        note.config(text=f"场景没有写进去：{msg or '保存失败'}", foreground="#b00020")

    steps = (_step_titles, _step_summaries, _step_scenes)

    def _render():
        _clear()
        for w in nav.winfo_children():
            w.destroy()
        steps[step[0]]()
        b = ttk.Button(nav, text="◀ 上一步", command=lambda: _go(step[0] - 1))
        b.pack(side=tk.LEFT)
        if step[0] == 0:
            b.state(["disabled"])
        if step[0] < 2:  # t170u: 第 3 步没有「关闭」，选了版本自动关；标题栏 X 仍可关
            ttk.Button(nav, text="关闭", command=lambda: _close()).pack(side=tk.RIGHT)
        if step[0] < 2:
            ttk.Button(nav, text="跳过 / 下一步 ▶", command=lambda: _go(step[0] + 1)).pack(side=tk.RIGHT, padx=6)
        ttk.Label(nav, text=path, foreground="#999999").pack(side=tk.LEFT, padx=12)

    def _go(i):
        step[0] = max(0, min(2, i))
        _render()

    def _close(_e=None):
        _ACTIVE_CANVAS[0] = None
        dlg.destroy()

    dlg.protocol("WM_DELETE_WINDOW", _close)
    dlg.bind("<Escape>", _close)
    dlg.bind("<MouseWheel>", _wheel)  # Text 自带滚轮；列表页滚当前 Canvas
    _render()
    return dlg

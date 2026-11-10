"""t356u: 封面 / 信息图的分格布局（给 ComfyUI MOSS / QN 的「从封面提取第 N 步」用）。

NotebookLM 的竖屏封面多半是几格左右并排（cover1 / cover2：4 列），也可能上下叠放，或者不规则。
这里只看图里贯穿全高 / 全宽的分界线：按 n 等分的位置附近找边缘，每条分界线都够强才算「确定」。
确定了就能把第 N 格裁出来单独交给图编辑模型（扩散模型数格子不可靠）；不确定就返回空布局，
提示词改用「按阅读顺序第 N 格」的说法。纯本地计算，不调任何服务。
"""
from __future__ import annotations

import os

# 一条线上「有边缘」的像素比例要够高，而且明显高于整条剖面的中位数
_EDGE_DIFF = 24          # 相邻像素 RGB 差之和，超过算边缘
_MIN_LINE_FRACTION = 0.5  # 分界线上至少一半是边缘
_MIN_OVER_MEDIAN = 1.8    # 至少是剖面中位数的 1.8 倍
_SEARCH = 0.03            # 在等分位置 ±3% 内找分界线
_MAX_PANELS = 8


def _profiles(path: str):
    import numpy as np
    from PIL import Image

    with Image.open(path) as src:
        im = src.convert("RGB")
    w, h = im.size
    s = 320.0 / max(w, h)
    small = im.resize((max(8, round(w * s)), max(8, round(h * s))), Image.BILINEAR)
    a = np.asarray(small, dtype=np.float32)
    cols = (np.abs(np.diff(a, axis=1)).sum(axis=2) > _EDGE_DIFF).mean(axis=0)  # 每个 x 处竖线的边缘比例
    rows = (np.abs(np.diff(a, axis=0)).sum(axis=2) > _EDGE_DIFF).mean(axis=1)  # 每个 y 处横线的边缘比例
    return (w, h), cols, rows


def _split_score(profile, n: int):
    """n 等分：返回 (最弱那条分界线的强度, 中位数, 分界位置 0..1 列表)。"""
    import numpy as np

    L = len(profile) + 1
    med = float(np.median(profile))
    cuts, weakest = [], 1.0
    for i in range(1, n):
        c = i * L / n
        r = max(1, int(L * _SEARCH))
        lo, hi = max(0, int(c - r)), min(len(profile), int(c + r) + 1)
        j = lo + int(np.argmax(profile[lo:hi]))
        weakest = min(weakest, float(profile[j]))
        cuts.append((j + 1) / L)
    return weakest, med, cuts


def _confident(weakest: float, med: float) -> bool:
    return weakest >= _MIN_LINE_FRACTION and weakest >= _MIN_OVER_MEDIAN * max(med, 1e-3)


def detect_panel_layout(path: str, count: int = 0) -> dict:
    """返回 {"layout": "columns"|"rows"|"", "count": n, "cuts": [...], "size": (w, h)}。

    ``count``：已知的步骤数（本集封面步骤数）；不知道就给 0，从 2..8 里找最大的一个确定的等分。
    读不了图 / 看不出来：layout = ""。
    """
    out = {"layout": "", "count": int(count or 0), "cuts": [], "size": (0, 0)}
    try:
        size, cols, rows = _profiles(path)
    except Exception:  # noqa: BLE001 — 没有 numpy / 坏图：当成看不出来
        return out
    out["size"] = size
    tries = [int(count)] if count and 2 <= int(count) <= _MAX_PANELS else list(range(_MAX_PANELS, 1, -1))
    for n in tries:
        best = None
        for name, prof in (("columns", cols), ("rows", rows)):
            weakest, med, cuts = _split_score(prof, n)
            if _confident(weakest, med) and (best is None or weakest > best[0]):
                best = (weakest, name, cuts)
        if best:
            out.update(layout=best[1], count=n, cuts=best[2])
            return out
    return out


def panel_box(layout: dict, step: int):
    """第 step 格（从 1 数）在原图上的 (left, top, right, bottom)；布局不确定或超出格数返回 None。"""
    name, n = layout.get("layout"), int(layout.get("count") or 0)
    w, h = layout.get("size") or (0, 0)
    k = int(step or 0)
    if name not in ("columns", "rows") or not (1 <= k <= n) or not (w and h):
        return None
    edges = [0.0] + list(layout.get("cuts") or []) + [1.0]
    if len(edges) != n + 1:
        return None
    a, b = edges[k - 1], edges[k]
    if name == "columns":
        return (round(a * w), 0, round(b * w), h)
    return (0, round(a * h), w, round(b * h))


def crop_cover_panel(path: str, step: int, layout: dict | None = None, out_dir: str = "") -> str:
    """把第 step 格裁成单独一张 PNG（放在临时目录），返回路径；裁不了返回 ""。"""
    from PIL import Image

    lay = layout if isinstance(layout, dict) else detect_panel_layout(path)
    box = panel_box(lay, step)
    if not box:
        return ""
    try:
        with Image.open(path) as src:
            im = src.convert("RGB").crop(box)
    except Exception:  # noqa: BLE001
        return ""
    if out_dir:
        folder = out_dir
    else:
        import tempfile

        folder = os.path.join(tempfile.gettempdir(), "aic_cover_panels")
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    dst = os.path.join(folder, f"{stem}_panel{int(step)}of{lay.get('count')}.png")
    im.save(dst)
    return dst


def prepare_cover_step_input(path: str, step: int, count: int = 0, *, crop: bool = True, out_dir: str = "") -> dict:
    """给 ComfyUI 封面提取准备输入：{"layout", "count", "image", "cropped"}。

    布局确定且能裁 → image = 裁出来的那一格，cropped=True；否则 image = 原封面。
    """
    lay = detect_panel_layout(path, count) if path and os.path.isfile(path) else {"layout": "", "count": int(count or 0)}
    img, cropped = path, False
    if crop and lay.get("layout"):
        got = crop_cover_panel(path, step, lay, out_dir=out_dir)
        if got:
            img, cropped = got, True
    return {"layout": lay.get("layout") or "", "count": int(lay.get("count") or count or 0), "image": img, "cropped": cropped}

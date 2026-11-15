# -*- coding: utf-8 -*-
"""t436u: 最终视频的范围：标记范围 / 本集 / 全部 → 场景下标（含首尾）。"""
from __future__ import annotations

FINAL_SCOPES = (("marker", "标记范围"), ("episode", "本集"), ("all", "全部"))
DEFAULT_SCOPE = "marker"


def normalize_scope(scope) -> str:
    s = str(scope or "").strip()
    return s if s in {k for k, _ in FINAL_SCOPES} else DEFAULT_SCOPE


def final_range_bounds(scope, count: int, marker_bounds, episode_bounds) -> tuple:
    """scope → (start, end)。本集找不到（没选场景）就退回全部。"""
    if count <= 0:
        return 0, 0
    s = normalize_scope(scope)
    if s == "all":
        return 0, count - 1
    if s == "episode":
        a, b = episode_bounds if episode_bounds else (-1, -1)
        if 0 <= a <= b < count:
            return a, b
        return 0, count - 1
    a, b = marker_bounds
    return max(0, min(a, count - 1)), max(0, min(b, count - 1))


def scope_label(scope) -> str:
    return dict(FINAL_SCOPES)[normalize_scope(scope)]

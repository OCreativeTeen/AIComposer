# -*- coding: utf-8 -*-
"""t440u: 每一场都要有分镜 shot（"第几段-共几段"）。没拆过的场 = "1-1"；拆开的几段 = 1-N … N-N（utility/scene_prep 写）。
已有的 shot 不改。"""
from __future__ import annotations

SHOT_FIELD = "shot"
DEFAULT_SHOT = "1-1"


def ensure_scene_shots(scenes) -> int:
    """给没有 shot 的场景补 "1-1"（就地改），返回补了几场。已有的不动。"""
    added = 0
    for s in scenes if isinstance(scenes, list) else []:
        if isinstance(s, dict) and not str(s.get(SHOT_FIELD) or "").strip():
            s[SHOT_FIELD] = DEFAULT_SHOT
            added += 1
    return added


def missing_shots(scenes) -> int:
    """有几场还没有 shot。"""
    return sum(1 for s in (scenes if isinstance(scenes, list) else [])
               if isinstance(s, dict) and not str(s.get(SHOT_FIELD) or "").strip())

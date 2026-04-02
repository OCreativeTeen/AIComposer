"""
视频/项目 tags 文本解析与规范化。

支持：
- 新版：KEY=value（如 ATMOSPHERE=...、Structure=Rising arc），多项可用逗号或 | 分隔；
- 旧版：纯文本项（如 「成瘾」「逃避」），逗号分隔。
"""

from __future__ import annotations

import re
from typing import List, Optional


def parse_tags_list(text: Optional[str]) -> List[str]:
    """
    从输入框单行文本解析为标签列表。
    - 含 | 时：按 | 分段（推荐分隔多枚 KEY=value，避免与值内逗号冲突）。
    - 否则若含 KEY=value：在「逗号 + 下一段 KEY=」处切开。
    - 否则：按逗号分段（旧版纯文本标签）。
    """
    if text is None:
        return []
    s = str(text).strip()
    if not s:
        return []
    if "|" in s:
        return [p.strip() for p in s.split("|") if p.strip()]
    if "=" in s:
        parts = re.split(r",\s*(?=[^\s,|]+=)", s)
        parts = [p.strip() for p in parts if p.strip()]
        if parts:
            return parts
    return [p.strip() for p in s.split(",") if p.strip()]


def tag_key_normalized(tag: str) -> Optional[str]:
    """KEY=value 返回 key 的小写；纯文本无 key 返回 None。"""
    if not tag or "=" not in tag:
        return None
    return tag.split("=", 1)[0].strip().lower() or None


def merge_tag_pick(existing: List[str], feature: str, option: str) -> List[str]:
    """
    追加「feature=option」；若已存在同一 feature（不区分大小写），先移除旧项再追加。
    """
    label = f"{feature}={option}"
    key = feature.strip().lower()
    out: List[str] = []
    for t in existing:
        ts = (t or "").strip()
        if not ts:
            continue
        if "=" in ts:
            k = ts.split("=", 1)[0].strip().lower()
            if k == key:
                continue
        out.append(ts)
    out.append(label)
    return out

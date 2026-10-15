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


# --- moved from gui/downloader.py: text helpers ---
def _plain_item_tags(video: dict) -> list[str]:
    """条目上的分组 tag（纯名称）。预设的「特征=选项」不参与筛选。"""
    if not isinstance(video, dict):
        return []
    raw = video.get("tags")
    if isinstance(raw, list):
        parts = [str(t).strip() for t in raw]
    elif isinstance(raw, str):
        parts = parse_tags_list(raw)
    else:
        return []
    out = []
    for part in parts:
        name = part.strip()
        if not name or "=" in name or name in out:
            continue
        out.append(name)
    return out


def _strip_markdown_embedded_images(text: str) -> tuple[str, int]:
    """丢掉 Markdown 里嵌进去的图片原始数据。正文留下，base64 不要。"""
    import re

    data_uri = re.compile(
        r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+",
        re.IGNORECASE,
    )
    removed = 0
    kept: list[str] = []
    for line in (text or "").splitlines():
        if line.startswith("（另有 ") and "嵌入图片" in line and "不展开" in line:
            continue
        if "<data:image/" in line and ";base64," in line and len(line) > 2000:
            removed += 1
            continue
        cleaned, n = data_uri.subn("", line)
        removed += n
        if cleaned.strip() != line.strip() and not cleaned.strip():
            continue
        kept.append(cleaned)
    body = "\n".join(kept).strip()
    return body, removed

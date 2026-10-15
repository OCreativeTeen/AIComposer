"""scene JSON helpers (moved verbatim from gui/downloader.py)."""
import json
from utility.file_util import safe_clipboard_json_copy


def _parse_scene_json_list(raw) -> list[dict]:
    """解析 scene_content JSON 文本或 list。"""
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(safe_clipboard_json_copy(s))
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(parsed, list):
            return [e for e in parsed if isinstance(e, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    return []


def _scene_content_nonempty_value(scene_content) -> bool:
    """``scene_content`` 是否为非空 list 或可解析的非空 JSON。"""
    if not scene_content:
        return False
    if isinstance(scene_content, list):
        return bool(scene_content)
    if isinstance(scene_content, str):
        t = scene_content.strip()
        if not t:
            return False
        try:
            parsed = json.loads(t)
            return bool(parsed) if isinstance(parsed, list) else bool(parsed)
        except json.JSONDecodeError:
            return bool(t)
    return False

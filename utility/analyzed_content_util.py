"""
Counseling / MESSAGE 模板形态的 analyzed_content 校验与分类用素材解析。

与 config_channel 中 OUTPUT FORMAT（english / chinese：title、key_message、story、
concise_speaking、summary 等）一致；「有效」用于分类/简表等时要求：
  - 顶层为 dict，且含 english、chinese 两个分支（均为 dict）
  - 各分支内 story、summary 均为非空字符串（strip 后）
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, Optional, Tuple


def merge_analyzed_content(base: Any, overlay: Dict[str, Any]) -> Dict[str, Any]:
    """
    将剪贴板/NotebookLM 的 JSON 合并进已有 analyzed_content。
    english / chinese 分支为 dict 时做浅合并（overlay 字段覆盖同名键）。
    """
    bd: Dict[str, Any] = {}
    if isinstance(base, str) and base.strip():
        try:
            p = json.loads(base)
            if isinstance(p, dict):
                bd = copy.deepcopy(p)
        except json.JSONDecodeError:
            pass
    elif isinstance(base, dict):
        bd = copy.deepcopy(base)
    for k, v in overlay.items():
        if k in ("english", "chinese") and isinstance(v, dict):
            existing = bd.get(k)
            if isinstance(existing, dict):
                merged_branch = {**existing, **v}
                bd[k] = merged_branch
            else:
                bd[k] = copy.deepcopy(v)
        else:
            bd[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
    return bd


def analyzed_content_valid_message_shape(ac: Any) -> bool:
    """与 MESSAGE 结构一致：english + chinese，且各含非空 story、summary。"""
    if isinstance(ac, str) and ac.strip():
        try:
            p = json.loads(ac)
            if isinstance(p, dict):
                ac = p
            else:
                return False
        except json.JSONDecodeError:
            return False
    if not isinstance(ac, dict):
        return False

    def _branch_ok(br: Any) -> bool:
        if not isinstance(br, dict):
            return False
        story = br.get("story")
        summ = br.get("summary")
        return bool(str(story or "").strip()) and bool(str(summ or "").strip())

    return _branch_ok(ac.get("english")) and _branch_ok(ac.get("chinese"))


def analyzed_content_to_prompt_text(ac: Any) -> str:
    """供 LLM / 剪贴板：dict、list 序列化为 JSON 字符串。"""
    if ac is None:
        return ""
    if isinstance(ac, str):
        return ac
    if isinstance(ac, (dict, list)):
        try:
            return json.dumps(ac, ensure_ascii=False)
        except Exception:
            return str(ac)
    return str(ac)


def resolve_material_for_topic_classification(video_detail: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """
    为「主题分类」LLM 准备输入文本。
    优先：analyzed_content 符合 MESSAGE 有效形态 → 整段 JSON 字符串。
    否则：使用 video_detail['content'] 正文。
    返回 (payload, err_msg)；payload 为 None 时 err_msg 说明原因。
    """
    ac = video_detail.get("analyzed_content")
    if isinstance(ac, str) and ac.strip():
        try:
            parsed = json.loads(ac)
            if isinstance(parsed, dict):
                ac = parsed
        except json.JSONDecodeError:
            ac = None
    if analyzed_content_valid_message_shape(ac):
        return analyzed_content_to_prompt_text(ac), ""
    body = (video_detail.get("content") or "").strip()
    if body:
        return body, ""
    return None, (
        "缺少用于分类的文本：analyzed_content 须为 JSON，且含 english、chinese，"
        "且各分支内 story、summary 均非空；或请先准备正文 content。"
    )

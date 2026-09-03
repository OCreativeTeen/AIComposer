#!/usr/bin/env python3
"""视频列表「选择队列」：GUI 导出选中行 → ``aiagent/video_choice_queue.json`` → CLI 逐条取用。

用法示例::

    python -m cli.pick_video_choice list
    python -m cli.pick_video_choice next --json
    python -m cli.pick_video_choice next --with-detail --json
    python -m cli.pick_video_choice open <choice_id> --with-detail
    python -m cli.pick_video_choice done <choice_id>
    python -m cli.pick_video_choice skip <choice_id>
"""

from __future__ import annotations

import os
import sys

# 保证从 cli/ 直接运行脚本时仍能 import 项目根模块（config 等）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import argparse
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

import config
import project_manager

VIDEO_CHOICE_QUEUE_JSON = config.VIDEO_CHOICE_QUEUE_JSON
QUEUE_VERSION = 3

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"

# 流水线子状态（``status`` 仍为 in_progress）
WORKFLOW_STATUS_NBIF_TIMEOUT = "nbif_timeout"
WORKFLOW_STEP_NBIF_POLL = "nbif_poll"
WORKFLOW_STEP_ITC = "itc"
WORKFLOW_STEP_VC_REVIEW = "vc_review"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_program_dir() -> None:
    os.makedirs(config.ensure_aiagent_path(), exist_ok=True)


def load_queue() -> dict:
    """读取队列；文件不存在时返回空队列。"""
    path = VIDEO_CHOICE_QUEUE_JSON
    empty = {"version": QUEUE_VERSION, "cursor": 0, "active_choice_id": "", "items": []}
    if not os.path.isfile(path):
        return dict(empty)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = dict(empty)
    if not isinstance(data, dict):
        data = dict(empty)
    if not isinstance(data.get("items"), list):
        data["items"] = []
    if not isinstance(data.get("cursor"), int) or data["cursor"] < 0:
        data["cursor"] = 0
    if not isinstance(data.get("active_choice_id"), str):
        data["active_choice_id"] = str(data.get("active_choice_id") or "").strip()
    data["version"] = QUEUE_VERSION
    return data


def save_queue(data: dict) -> str:
    """写回队列 JSON，返回绝对路径。"""
    if not isinstance(data, dict):
        raise ValueError("queue data 必须是 dict")
    _ensure_program_dir()
    items = data.get("items")
    if not isinstance(items, list):
        items = []
        data["items"] = items
    data["version"] = QUEUE_VERSION
    if "cursor" not in data or not isinstance(data.get("cursor"), int) or data["cursor"] < 0:
        data["cursor"] = 0
    path = VIDEO_CHOICE_QUEUE_JSON
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return os.path.abspath(path)


def _row_lookup_keys(video_detail: dict) -> list[str]:
    if not isinstance(video_detail, dict):
        return []
    keys: list[str] = []
    for k in ("url", "id"):
        v = (video_detail.get(k) or "").strip()
        if v and v not in keys:
            keys.append(v)
    pid = project_manager.list_json_row_workflow_pid(video_detail)
    if pid and pid not in keys:
        keys.append(pid)
    return keys


def _queue_item_dedupe_key(item: dict) -> str:
    list_path = os.path.normcase(os.path.normpath((item.get("list_json_path") or "").strip()))
    row_key = (item.get("row_key") or item.get("url") or item.get("row_id") or "").strip()
    return f"{list_path}\0{row_key}"


def build_queue_item_from_video_detail(
    video_detail: dict,
    *,
    channel_id: str = "",
    channel_path: str = "",
    list_json_path: str = "",
    title: str = "",
    yt_language: str = "",
    visual_style: str = "",
    narrator: str = "",
) -> dict:
    """由列表行构造可写入队列的条目（不含 choice_id / status）。"""
    vd = video_detail if isinstance(video_detail, dict) else {}
    ch_path = (channel_path or "").strip()
    ch_id = (channel_id or "").strip()
    if not ch_id and ch_path:
        ch_id = config.get_channel_id(os.path.basename(ch_path))
    list_path = (list_json_path or "").strip()
    if not list_path and ch_path:
        list_path = config.yt_text_download_list_json_path(ch_id) if ch_id else ""

    row_keys = _row_lookup_keys(vd)
    row_key = row_keys[0] if row_keys else ""

    tags = vd.get("tags", "")
    if isinstance(tags, list):
        tags_text = " | ".join(str(t) for t in tags if t is not None)
    else:
        tags_text = str(tags) if tags else ""

    sc = vd.get("scene_content")
    has_scene = False
    if isinstance(sc, list) and sc:
        has_scene = True
    elif isinstance(sc, str) and sc.strip():
        has_scene = True

    return {
        "channel_id": ch_id,
        "channel_path": ch_path,
        "list_json_path": list_path,
        "row_key": row_key,
        "row_id": (vd.get("id") or "").strip(),
        "url": (vd.get("url") or "").strip(),
        "title": (title or vd.get("title") or vd.get("video_title") or "").strip(),
        "topic_category": (vd.get("topic_category") or "").strip(),
        "topic_subtype": (vd.get("topic_subtype") or "").strip(),
        "tags": tags_text,
        "workflow_pid": project_manager.list_json_row_workflow_pid(vd),
        "language": (vd.get("language") or "").strip(),
        "yt_language": (yt_language or "").strip(),
        "visual_style": (visual_style or "").strip(),
        "narrator": (narrator or "").strip(),
        "has_analyzed_content": bool((vd.get("analyzed_content") or "").strip()),
        "has_scene_content": has_scene,
    }


def export_video_details_to_queue(
    video_details: list[dict],
    *,
    channel_id: str = "",
    channel_path: str = "",
    list_json_path: str = "",
    title_fn=None,
    yt_language: str = "",
    visual_style: str = "",
    narrator: str = "",
) -> tuple[int, int, str]:
    """用当前选中项**整表覆盖**队列（清空旧列表，cursor 归零）。返回 (写入数, 跳过数, 文件路径)。"""
    items: list[dict] = []
    skipped = 0
    now = _utc_now_iso()
    seen: set[str] = set()

    for vd in video_details or []:
        if not isinstance(vd, dict):
            skipped += 1
            continue
        title = ""
        if callable(title_fn):
            try:
                title = (title_fn(vd) or "").strip()
            except Exception:
                title = ""
        base = build_queue_item_from_video_detail(
            vd,
            channel_id=channel_id,
            channel_path=channel_path,
            list_json_path=list_json_path,
            title=title,
            yt_language=yt_language,
            visual_style=visual_style,
            narrator=narrator,
        )
        if not base.get("row_key") and not base.get("workflow_pid"):
            skipped += 1
            continue
        dedupe = _queue_item_dedupe_key(base)
        if dedupe in seen:
            skipped += 1
            continue
        seen.add(dedupe)
        items.append({
            **base,
            "choice_id": uuid.uuid4().hex[:12],
            "exported_at": now,
            "status": STATUS_PENDING,
        })

    data = {
        "version": QUEUE_VERSION,
        "cursor": 0,
        "active_choice_id": "",
        "exported_at": now,
        "items": items,
    }
    path = save_queue(data)
    return len(items), skipped, path


def list_queue_items(*, remaining_only: bool = False) -> list[dict]:
    data = load_queue()
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]
    if remaining_only:
        cursor = int(data.get("cursor") or 0)
        items = items[cursor:]
    return items


def _find_item_by_choice_id(data: dict, choice_id: str) -> dict | None:
    cid = (choice_id or "").strip()
    if not cid:
        return None
    for it in data.get("items") or []:
        if isinstance(it, dict) and (it.get("choice_id") or "").strip() == cid:
            return it
    return None


def normalize_item_status(item: dict) -> str:
    s = (item.get("status") or "").strip().lower() if isinstance(item, dict) else ""
    if s in (STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_DONE):
        return s
    return STATUS_PENDING


def _row_looks_published(item: dict) -> bool:
    """列表行已有发布记录时，显示为已完成（即使队列 JSON 还没写 status）。"""
    row = resolve_video_detail_from_queue_item(item)
    if not isinstance(row, dict):
        return False
    return bool((row.get("publish") or "").strip())


def item_display_status(item: dict) -> tuple[str, str]:
    """``(status_key, 中文标签)``。``done`` 优先认队列字段，其次认列表发布记录。"""
    if not isinstance(item, dict):
        return STATUS_PENDING, "未处理"
    s = normalize_item_status(item)
    wf = (item.get("workflow_status") or "").strip().lower()
    extra = (item.get("processed_at") or "").strip()
    extra_day = extra[:10] if extra else ""
    if s == STATUS_DONE:
        label = "已完成" + (f" {extra_day}" if extra_day else "")
        return STATUS_DONE, label
    if s == STATUS_IN_PROGRESS:
        if wf == WORKFLOW_STATUS_NBIF_TIMEOUT:
            failed = (item.get("workflow_failed_at") or "")[:16].replace("T", " ")
            note = f"（nbif 轮询超时，待 resume）"
            if failed:
                note = f"（nbif 轮询超时 {failed}，待 resume）"
            return STATUS_IN_PROGRESS, f"处理中{note}"
        return STATUS_IN_PROGRESS, "处理中"
    if _row_looks_published(item):
        return STATUS_DONE, "已完成（列表已有发布记录）"
    return STATUS_PENDING, "未处理"


def _set_active_index(data: dict, index: int) -> dict:
    """把 ``items[index]`` 标为处理中，其它处理中的退回未处理。"""
    items = data.get("items") or []
    if index < 0 or index >= len(items) or not isinstance(items[index], dict):
        raise ValueError(f"无效的队列下标: {index}")
    chosen = items[index]
    cid = (chosen.get("choice_id") or "").strip()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        if i == index:
            it["status"] = STATUS_IN_PROGRESS
            continue
        if normalize_item_status(it) == STATUS_IN_PROGRESS:
            it["status"] = STATUS_PENDING
    data["active_choice_id"] = cid
    data["cursor"] = index + 1
    return chosen


def activate_queue_item(choice_id: str) -> dict:
    """按 ``choice_id`` 设为当前条（可重做已完成的）。"""
    cid = (choice_id or "").strip()
    if not cid:
        raise ValueError("choice_id 为空")
    data = load_queue()
    items = data.get("items") or []
    idx = -1
    for i, it in enumerate(items):
        if isinstance(it, dict) and (it.get("choice_id") or "").strip() == cid:
            idx = i
            break
    if idx < 0:
        raise ValueError(f"未找到 choice_id: {cid}")
    chosen = _set_active_index(data, idx)
    save_queue(data)
    return copy.deepcopy(chosen)


def activate_queue_item_at(index_1based: int) -> dict:
    """按 1-based 列表序号设为当前条。"""
    item = queue_item_at(index_1based)
    return activate_queue_item(item.get("choice_id") or "")


def queue_item_at(index_1based: int) -> dict:
    """按 1-based 序号取出条目（不改状态）。"""
    items = list_queue_items()
    if index_1based < 1 or index_1based > len(items):
        raise ValueError(f"序号超出范围: {index_1based}（共 {len(items)} 条）")
    return copy.deepcopy(items[index_1based - 1])


def mark_active_item_done(choice_id: str = "") -> dict | None:
    """当前条（或指定 choice_id）标为已完成。"""
    data = load_queue()
    cid = (choice_id or "").strip() or (data.get("active_choice_id") or "").strip()
    it = _find_item_by_choice_id(data, cid) if cid else None
    if it is None:
        items = [x for x in (data.get("items") or []) if isinstance(x, dict)]
        cursor = int(data.get("cursor") or 0)
        if 1 <= cursor <= len(items):
            it = items[cursor - 1]
    if it is None:
        return None
    it["status"] = STATUS_DONE
    it["processed_at"] = _utc_now_iso()
    for k in (
        "workflow_status",
        "workflow_step",
        "workflow_error",
        "workflow_failed_at",
        "nbi_profile_index",
        "resume_hint",
    ):
        it.pop(k, None)
    save_queue(data)
    return copy.deepcopy(it)


def _workflow_touch_item(
    it: dict,
    *,
    workflow_status: str = "",
    workflow_step: str = "",
    workflow_error: str = "",
    nbi_profile_index: int = 0,
    resume_hint: str = "",
    polls_done: int = 0,
    elapsed_s: float = 0,
) -> None:
    if workflow_status:
        it["workflow_status"] = workflow_status
    if workflow_step:
        it["workflow_step"] = workflow_step
    if workflow_error:
        it["workflow_error"] = workflow_error
    if workflow_status == WORKFLOW_STATUS_NBIF_TIMEOUT:
        it["workflow_failed_at"] = _utc_now_iso()
    if nbi_profile_index > 0:
        it["nbi_profile_index"] = int(nbi_profile_index)
    if resume_hint:
        it["resume_hint"] = resume_hint
    if polls_done > 0:
        it["nbif_polls_done"] = int(polls_done)
    if elapsed_s > 0:
        it["nbif_elapsed_s"] = round(float(elapsed_s), 1)


def mark_active_item_nbif_timeout(
    *,
    choice_id: str = "",
    error_msg: str = "",
    nbi_profile_index: int = 0,
    polls_done: int = 0,
    elapsed_s: float = 0,
) -> dict | None:
    """nbif 轮询超时：保持 in_progress，写入可 resume 的子状态。"""
    data = load_queue()
    cid = (choice_id or "").strip() or (data.get("active_choice_id") or "").strip()
    it = _find_item_by_choice_id(data, cid) if cid else None
    if it is None:
        items = [x for x in (data.get("items") or []) if isinstance(x, dict)]
        cursor = int(data.get("cursor") or 0)
        if 1 <= cursor <= len(items):
            it = items[cursor - 1]
    if it is None:
        return None
    it["status"] = STATUS_IN_PROGRESS
    _workflow_touch_item(
        it,
        workflow_status=WORKFLOW_STATUS_NBIF_TIMEOUT,
        workflow_step=WORKFLOW_STEP_NBIF_POLL,
        workflow_error=(error_msg or "nbif 超时：infographic 仍未 ready").strip(),
        nbi_profile_index=nbi_profile_index,
        polls_done=polls_done,
        elapsed_s=elapsed_s,
        resume_hint="cli\\run_telegram_client_resume.bat — 人工确认 NotebookLM 后从 nbif 继续轮询",
    )
    save_queue(data)
    return copy.deepcopy(it)


def mark_active_item_workflow_step(
    *,
    workflow_step: str,
    choice_id: str = "",
    nbi_profile_index: int = 0,
) -> dict | None:
    """记录流水线进行到哪一步（如 nbi 成功后进入 nbif）。"""
    data = load_queue()
    cid = (choice_id or "").strip() or (data.get("active_choice_id") or "").strip()
    it = _find_item_by_choice_id(data, cid) if cid else None
    if it is None:
        return None
    it["status"] = STATUS_IN_PROGRESS
    it["workflow_step"] = (workflow_step or "").strip()
    it.pop("workflow_status", None)
    it.pop("workflow_error", None)
    it.pop("workflow_failed_at", None)
    it.pop("resume_hint", None)
    if nbi_profile_index > 0:
        it["nbi_profile_index"] = int(nbi_profile_index)
    save_queue(data)
    return copy.deepcopy(it)


def clear_item_nbif_timeout_for_resume(choice_id: str = "") -> dict | None:
    """resume 前：清掉 nbif_timeout 标记，保持 in_progress。"""
    data = load_queue()
    cid = (choice_id or "").strip() or (data.get("active_choice_id") or "").strip()
    it = _find_item_by_choice_id(data, cid) if cid else None
    if it is None:
        return None
    for k in ("workflow_status", "workflow_error", "workflow_failed_at", "resume_hint"):
        it.pop(k, None)
    it["workflow_step"] = WORKFLOW_STEP_NBIF_POLL
    it["status"] = STATUS_IN_PROGRESS
    save_queue(data)
    return copy.deepcopy(it)


def find_nbif_timeout_resume_item() -> dict | None:
    """找上次 nbif 轮询超时、待 resume 的条目（优先 active_choice_id）。"""
    data = load_queue()
    active = (data.get("active_choice_id") or "").strip()
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]

    def _is_nbif_timeout(it: dict) -> bool:
        return (
            (it.get("workflow_status") or "").strip().lower()
            == WORKFLOW_STATUS_NBIF_TIMEOUT
        )

    def _is_nbif_resume_candidate(it: dict) -> bool:
        if normalize_item_status(it) != STATUS_IN_PROGRESS:
            return False
        step = (it.get("workflow_step") or "").strip().lower()
        return step == WORKFLOW_STEP_NBIF_POLL or _is_nbif_timeout(it)

    if active:
        it = _find_item_by_choice_id(data, active)
        if it and (_is_nbif_timeout(it) or _is_nbif_resume_candidate(it)):
            return copy.deepcopy(it)
    for it in reversed(items):
        if _is_nbif_timeout(it):
            return copy.deepcopy(it)
    for it in reversed(items):
        if _is_nbif_resume_candidate(it):
            return copy.deepcopy(it)
    return None


def mark_nbif_resume_succeeded(choice_id: str = "") -> dict | None:
    """itc 下载成功后再清 nbif_timeout 标记。"""
    return clear_item_nbif_timeout_for_resume(choice_id)


def first_pending_story_index() -> int | None:
    """原顺序里第一条未处理（不含处理中 / 已完成）的 1-based 序号。"""
    items = list_queue_items()
    for i, it in enumerate(items, 1):
        key, _ = item_display_status(it)
        if key == STATUS_PENDING:
            return i
    return None


def resolve_story_pick_index(want: str = "") -> int | None:
    """把 ``pick`` 参数解析为 1-based 序号。

    ``next`` / 空：优先第一条未处理；若无未处理但队列非空则回退到 1（可重做处理中/已完成）。
    数字：直接返回对应序号。
    """
    raw = (want or "").strip()
    low = raw.lower().replace(" ", "")
    if low in ("next", "n", "下一个", "下一条", ""):
        idx = first_pending_story_index()
        if idx is not None:
            return idx
        return 1 if list_queue_items() else None
    if raw.isdigit():
        n = int(raw)
        return n if n >= 1 else None
    return None


def describe_queue_stories() -> dict:
    """供 ``story_pickup`` 列出全部故事及处理状态。"""
    data = load_queue()
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]
    active = (data.get("active_choice_id") or "").strip()
    rows: list[dict] = []
    n_pending = n_done = n_busy = 0
    current_index = None
    for i, it in enumerate(items, 1):
        key, zh = item_display_status(it)
        cid = (it.get("choice_id") or "").strip()
        is_current = bool(cid and cid == active)
        if is_current:
            current_index = i
        if key == STATUS_DONE:
            n_done += 1
        elif key == STATUS_IN_PROGRESS:
            n_busy += 1
        else:
            n_pending += 1
        title = (it.get("title") or it.get("row_key") or cid or "?").strip()
        rows.append(
            {
                "index": i,
                "choice_id": cid,
                "title": title,
                "status": key,
                "status_zh": zh,
                "current": is_current,
            }
        )
    return {
        "path": os.path.abspath(VIDEO_CHOICE_QUEUE_JSON),
        "total": len(rows),
        "pending": n_pending,
        "in_progress": n_busy,
        "done": n_done,
        "current_index": current_index,
        "suggest": first_pending_story_index(),
        "rows": rows,
    }


def current_taken_queue_item() -> dict | None:
    """当前正在处理的那一条：优先 ``active_choice_id``，否则 ``items[cursor - 1]``。"""
    data = load_queue()
    cid = (data.get("active_choice_id") or "").strip()
    if cid:
        it = _find_item_by_choice_id(data, cid)
        if it:
            return copy.deepcopy(it)
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]
    cursor = int(data.get("cursor") or 0)
    if cursor < 1 or cursor > len(items):
        return None
    return copy.deepcopy(items[cursor - 1])


def pick_next_item(*, advance: bool = True) -> dict | None:
    """按 ``cursor`` 取下一条；默认取用后标为处理中并前移 cursor。"""
    data = load_queue()
    items = data.get("items") or []
    cursor = int(data.get("cursor") or 0)
    if cursor >= len(items):
        return None
    item = items[cursor]
    if not isinstance(item, dict):
        return None
    if advance:
        _set_active_index(data, cursor)
        save_queue(data)
        item = items[cursor]
    return copy.deepcopy(item)


def advance_queue_cursor(steps: int = 1) -> int:
    """手动前移 cursor（``done`` / ``skip`` 兼容用）。返回新 cursor。"""
    data = load_queue()
    items = data.get("items") or []
    cursor = int(data.get("cursor") or 0)
    cursor = min(cursor + max(1, steps), len(items))
    data["cursor"] = cursor
    save_queue(data)
    return cursor


def reset_queue_cursor() -> None:
    data = load_queue()
    data["cursor"] = 0
    save_queue(data)


def _match_row_in_list(arr: list, item: dict) -> dict | None:
    row_key = (item.get("row_key") or "").strip()
    row_id = (item.get("row_id") or "").strip()
    url = (item.get("url") or "").strip()
    pid = (item.get("workflow_pid") or "").strip()
    for row in arr:
        if not isinstance(row, dict):
            continue
        if row_key and (
            (row.get("url") or "").strip() == row_key
            or (row.get("id") or "").strip() == row_key
        ):
            return row
        if url and (row.get("url") or "").strip() == url:
            return row
        if row_id and (row.get("id") or "").strip() == row_id:
            return row
        if pid and project_manager.list_json_row_workflow_pid(row) == pid:
            return row
    return None


def resolve_video_detail_from_queue_item(item: dict) -> dict | None:
    """从 ``list_json_path`` 读盘，按 row_key / pid 定位完整 video detail 行。"""
    if not isinstance(item, dict):
        return None
    list_path = (item.get("list_json_path") or "").strip()
    if not list_path or not os.path.isfile(list_path):
        return None
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(arr, list):
        return None
    return _match_row_in_list(arr, item)


def parse_scene_content_field(value) -> list | None:
    """把 ``video_detail.scene_content`` 规范成非空 list，否则 ``None``。"""
    if isinstance(value, list):
        return value if value else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
        if isinstance(parsed, list) and parsed:
            return parsed
    return None


def active_video_detail_scene_content() -> list | None:
    """当前队列条对应频道 list 行上的 ``scene_content``（已 scnsave 后为准）。"""
    item = current_taken_queue_item()
    if not item:
        return None
    vd = resolve_video_detail_from_queue_item(item)
    if not vd:
        return None
    return parse_scene_content_field(vd.get("scene_content"))


def active_video_detail_scene_count() -> int:
    sc = active_video_detail_scene_content()
    return len(sc) if sc else 0


SCENE_GROK_CLIP_KEY = "grok_clip"


def grok_clip_paths_from_scene_content(scene_content) -> list[str]:
    """从 ``scene_content`` 各条 ``grok_clip`` 按场景顺序收集 mp4 路径。"""
    if not isinstance(scene_content, list):
        return []
    out: list[str] = []
    for item in scene_content:
        if not isinstance(item, dict):
            continue
        p = (item.get(SCENE_GROK_CLIP_KEY) or "").strip()
        if not p:
            continue
        p = os.path.normpath(os.path.abspath(p))
        if os.path.isfile(p) and p.lower().endswith(".mp4"):
            out.append(p)
    return out


def apply_grok_clips_to_scene_content(
    scene_content: list, clips: list[dict]
) -> list:
    """把 ``[{scene, path}, ...]`` 写回 ``scene_content[i].grok_clip``（1-based scene）。"""
    out = copy.deepcopy(scene_content)
    by_scene: dict[int, str] = {}
    for item in clips or []:
        if isinstance(item, str):
            continue
        if not isinstance(item, dict):
            continue
        p = os.path.normpath(os.path.abspath((item.get("path") or "").strip()))
        if not p:
            continue
        try:
            scene = int(item.get("scene") or 0)
        except (TypeError, ValueError):
            scene = 0
        if scene > 0:
            by_scene[scene] = p
    for i, item in enumerate(out, 1):
        if not isinstance(item, dict):
            continue
        if i in by_scene:
            item[SCENE_GROK_CLIP_KEY] = by_scene[i]
    return out


def persist_active_video_detail_row(video_detail: dict) -> tuple[bool, str]:
    """把内存中的 video_detail 整行写回当前队列条对应的频道 list。"""
    item = current_taken_queue_item()
    if not item:
        return False, "队列无当前条"
    if not isinstance(video_detail, dict):
        return False, "video_detail 无效"
    list_path = (item.get("list_json_path") or "").strip()
    if not list_path or not os.path.isfile(list_path):
        return False, f"频道列表不存在: {list_path or '?'}"
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"读取列表失败: {exc}"
    if not isinstance(arr, list):
        return False, "列表格式无效"
    row = _match_row_in_list(arr, item)
    if not isinstance(row, dict):
        return False, "未在列表中找到当前故事行"
    row.clear()
    row.update(copy.deepcopy(video_detail))
    try:
        config.write_channel_list_json(list_path, arr)
    except OSError as exc:
        return False, f"写入列表失败: {exc}"
    return True, "saved video_detail row"


def persist_active_video_detail_field(field: str, value) -> tuple[bool, str]:
    """把单个字段写回当前队列条对应的频道 list 行。"""
    item = current_taken_queue_item()
    if not item:
        return False, "队列无当前条"
    list_path = (item.get("list_json_path") or "").strip()
    if not list_path or not os.path.isfile(list_path):
        return False, f"频道列表不存在: {list_path or '?'}"
    try:
        with open(list_path, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"读取列表失败: {exc}"
    if not isinstance(arr, list):
        return False, "列表格式无效"
    row = _match_row_in_list(arr, item)
    if not isinstance(row, dict):
        return False, "未在列表中找到当前故事行"
    row[field] = copy.deepcopy(value)
    try:
        config.write_channel_list_json(list_path, arr)
    except OSError as exc:
        return False, f"写入列表失败: {exc}"
    return True, f"saved {field}"


def save_grok_clips_to_active_video_detail(clips: list[dict]) -> tuple[bool, str]:
    """grv 下载后：把各场景 mp4 路径写入 ``video_detail.scene_content``。"""
    sc = active_video_detail_scene_content()
    if not sc:
        return False, "尚无 scene_content（先 scnsave）"
    updated = apply_grok_clips_to_scene_content(sc, clips)
    ok, msg = persist_active_video_detail_field("scene_content", updated)
    if ok:
        vd = resolve_video_detail_from_queue_item(current_taken_queue_item() or {})
        if isinstance(vd, dict):
            vd["scene_content"] = updated
    return ok, msg


def collect_scene_grok_clip_paths() -> list[str]:
    """当前故事场景 clip 路径：优先 ``scene_content.grok_clip``，否则 grok_scene_videos.json。"""
    paths = grok_clip_paths_from_scene_content(active_video_detail_scene_content())
    if paths:
        return paths
    from utility.telegram_session import load_grok_scene_videos

    clips = load_grok_scene_videos()
    out: list[str] = []
    for item in clips:
        p = os.path.normpath(os.path.abspath((item.get("path") or "").strip()))
        if p and os.path.isfile(p):
            out.append(p)
    return out


def resolve_queue_item_by_id(choice_id: str) -> dict | None:
    data = load_queue()
    it = _find_item_by_choice_id(data, choice_id)
    if not it:
        return None
    row = resolve_video_detail_from_queue_item(it)
    return {
        "queue_item": copy.deepcopy(it),
        "video_detail": copy.deepcopy(row) if row else None,
    }


def apply_queue_item_yt_prefs(item: dict) -> dict:
    """将队列条目中的 YT 欢迎屏选项写入内存 LAST_*（并尽量写回 prefs 文件）。"""
    if not isinstance(item, dict):
        return {}
    prefs = config.load_yt_tools_prefs()
    lang = (item.get("yt_language") or prefs.get("language") or project_manager.LAST_YT_LANGUAGE or "tw").strip()
    if lang not in config.LANGUAGES:
        lang = project_manager.LAST_YT_LANGUAGE if project_manager.LAST_YT_LANGUAGE in config.LANGUAGES else "tw"

    vs = (item.get("visual_style") or prefs.get("visual_style") or project_manager.LAST_VISUAL_STYLE or "").strip()
    if vs not in config.VISUAL_STYLE_OPTIONS:
        vs = project_manager.LAST_VISUAL_STYLE

    narr_opts = config.narrator_person_options()
    nar = (item.get("narrator") or prefs.get("narrator") or project_manager.LAST_NARRATOR or "").strip()
    if nar and narr_opts and nar not in narr_opts:
        nar = project_manager.LAST_NARRATOR or (narr_opts[0] if narr_opts else "")

    project_manager.LAST_YT_LANGUAGE = lang
    project_manager.LAST_VISUAL_STYLE = vs
    project_manager.LAST_NARRATOR = nar

    ch = (item.get("channel_id") or prefs.get("channel") or "").strip()
    if ch:
        config.save_yt_tools_prefs({
            "channel": ch,
            "language": lang,
            "narrator": nar,
            "visual_style": vs,
            "reserved": (prefs.get("reserved") or "").strip(),
        })
    return {"channel": ch, "language": lang, "narrator": nar, "visual_style": vs}


def launch_queue_item_gui(item: dict) -> int:
    """跳过欢迎屏 / 列表选择 / 操作菜单，直达该条目的「打开摘要编辑」。"""
    if not isinstance(item, dict):
        print("无效的 queue item", file=sys.stderr)
        return 1

    import tkinter as tk

    try:
        import tkinterdnd2 as TkinterDnD

        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()

    root.title("AIComposer — YT 工具")
    try:
        from gui.cli_bridge import register_bridge_root

        register_bridge_root(root)
    except Exception:
        pass
    try:
        root.geometry("1x1+-3000+-3000")
        root.resizable(False, False)
    except tk.TclError:
        pass

    prefs = apply_queue_item_yt_prefs(item)
    ch = (item.get("channel_id") or prefs.get("channel") or "").strip()
    if not ch:
        ch_path = (item.get("channel_path") or "").strip()
        if ch_path:
            ch = config.get_channel_id(os.path.basename(ch_path))
    if not ch:
        print("队列条目缺少 channel_id", file=sys.stderr)
        return 1

    lang = prefs.get("language") or "tw"
    list_path = (item.get("list_json_path") or "").strip()
    if not list_path:
        list_path = config.yt_text_download_list_json_path(ch)

    row_keys = [
        k
        for k in (
            item.get("row_key"),
            item.get("row_id"),
            item.get("url"),
            item.get("workflow_pid"),
        )
        if (k or "").strip()
    ]
    auto_key = row_keys[0] if row_keys else ""

    from cli.gui_session import SOURCE_QUEUE, clear_gui_launch_source, set_gui_launch_source

    set_gui_launch_source(SOURCE_QUEUE)
    try:
        return _run_queue_item_gui(root, tk, ch, lang, list_path, row_keys)
    finally:
        clear_gui_launch_source()


def _run_queue_item_gui(root, tk, ch, lang, list_path, row_keys) -> int:
    from gui.downloader import MediaGUIManager

    _yt_log = tk.Text(root)

    def _yt_log_fn(w, m):
        try:
            w.insert(tk.END, m + "\n")
        except Exception:
            pass

    yt_gui = MediaGUIManager(root, ch, "temp", {}, _yt_log_fn, _yt_log, language=lang)

    def _poll_standalone_exit():
        try:
            if not root.winfo_exists():
                return
            has_dialog = any(isinstance(w, tk.Toplevel) for w in root.winfo_children())
            if not has_dialog:
                root.quit()
                return
        except tk.TclError:
            return
        root.after(350, _poll_standalone_exit)

    def _run():
        try:
            yt_gui.open_hot_videos_from_list_json(
                list_path,
                auto_open_summary_row_keys=row_keys,
            )
        finally:
            root.after(350, _poll_standalone_exit)

    root.after(0, _run)
    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass
    return 0


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从 aiagent/video_choice_queue.json 逐条取用 GUI 导出的视频选择。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出队列条目")
    p_list.add_argument(
        "--remaining",
        action="store_true",
        help="仅列出尚未取用的条目（cursor 之后）",
    )
    p_list.add_argument("--json", action="store_true", help="JSON 输出")

    p_open = sub.add_parser("open", help="按 choice_id 打开该条 GUI（不按 cursor 顺序）")
    p_open.add_argument("choice_id")
    p_open.add_argument("--json", action="store_true")
    p_open.add_argument(
        "--with-detail",
        action="store_true",
        help="附带从 list JSON 解析的完整 video_detail",
    )
    p_open.add_argument(
        "--no-gui",
        action="store_true",
        help="只设为当前条并输出，不启动 GUI",
    )

    p_next = sub.add_parser("next", help="取下一条（按 cursor 顺序）")
    p_next.add_argument("--json", action="store_true")
    p_next.add_argument(
        "--with-detail",
        action="store_true",
        help="附带从 list JSON 解析的完整 video_detail",
    )
    p_next.add_argument(
        "--no-advance",
        action="store_true",
        help="只预览当前条，不前移 cursor",
    )
    p_next.add_argument(
        "--no-gui",
        action="store_true",
        help="不启动 GUI（仅输出 JSON / 文本，供 agent 使用）",
    )

    p_done = sub.add_parser("done", help="前移 cursor（兼容旧工作流）")
    p_done.add_argument("choice_id", nargs="?", default="")
    p_done.add_argument("--json", action="store_true")

    p_skip = sub.add_parser("skip", help="前移 cursor（跳过当前条）")
    p_skip.add_argument("choice_id", nargs="?", default="")
    p_skip.add_argument("--json", action="store_true")

    p_resolve = sub.add_parser("resolve", help="按 choice_id 解析完整 video detail")
    p_resolve.add_argument("choice_id")
    p_resolve.add_argument("--json", action="store_true")

    sub.add_parser("path", help="打印队列文件绝对路径")
    sub.add_parser("reset-cursor", help="将 cursor 重置为 0")

    p_status = sub.add_parser("status", help="队列统计")
    p_status.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "path":
        print(os.path.abspath(VIDEO_CHOICE_QUEUE_JSON))
        return 0

    if args.command == "list":
        if args.remaining:
            items = list_queue_items(remaining_only=True)
            if args.json:
                _print_json(items)
            else:
                for it in items:
                    print(
                        f"{it.get('choice_id', '?'):12}  "
                        f"{(it.get('title') or it.get('row_key') or '')[:80]}"
                    )
            return 0
        info = describe_queue_stories()
        if args.json:
            _print_json(info)
        else:
            for row in info.get("rows") or []:
                mark = "  ← 当前" if row.get("current") else ""
                print(
                    f"{row['index']}) [{row.get('status_zh')}] "
                    f"{(row.get('title') or '')[:80]}{mark}"
                )
            suggest = info.get("suggest")
            if suggest:
                print(f"建议下一个未处理：{suggest}")
        return 0

    if args.command == "next":
        item = pick_next_item(advance=not args.no_advance)
        if not item:
            if args.json:
                _print_json(None)
            else:
                print("（队列已取完）", file=sys.stderr)
            return 1
        if args.with_detail:
            detail = resolve_video_detail_from_queue_item(item)
            payload = {"queue_item": item, "video_detail": detail}
        else:
            payload = item
        if args.json:
            _print_json(payload)
        if args.no_gui:
            if not args.json:
                print(f"choice_id: {item.get('choice_id')}")
                print(f"title: {item.get('title')}")
                print(f"list: {item.get('list_json_path')}")
                print(f"row_key: {item.get('row_key')}")
            return 0
        return launch_queue_item_gui(item)

    if args.command == "open":
        try:
            item = activate_queue_item(args.choice_id)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.with_detail:
            detail = resolve_video_detail_from_queue_item(item)
            payload = {"queue_item": item, "video_detail": detail}
        else:
            payload = item
        if args.json:
            _print_json(payload)
        if args.no_gui:
            if not args.json:
                print(f"choice_id: {item.get('choice_id')}")
                print(f"title: {item.get('title')}")
            return 0
        return launch_queue_item_gui(item)

    if args.command == "done":
        cursor = advance_queue_cursor()
        if args.json:
            _print_json({"cursor": cursor, "remaining": len(list_queue_items(remaining_only=True))})
        else:
            print(f"cursor → {cursor}")
        return 0

    if args.command == "skip":
        cursor = advance_queue_cursor()
        if args.json:
            _print_json({"cursor": cursor, "remaining": len(list_queue_items(remaining_only=True))})
        else:
            print(f"已跳过，cursor → {cursor}")
        return 0

    if args.command == "resolve":
        payload = resolve_queue_item_by_id(args.choice_id)
        if not payload:
            print(f"未找到 choice_id: {args.choice_id}", file=sys.stderr)
            return 1
        if args.json:
            _print_json(payload)
        else:
            qi = payload["queue_item"]
            print(f"title: {qi.get('title')}")
            print(f"has video_detail: {payload.get('video_detail') is not None}")
        return 0

    if args.command == "reset-cursor":
        reset_queue_cursor()
        print("cursor 已重置为 0")
        return 0

    if args.command == "status":
        data = load_queue()
        total = len(data.get("items") or [])
        cursor = int(data.get("cursor") or 0)
        remaining = max(0, total - cursor)
        info = describe_queue_stories()
        payload = {
            "path": os.path.abspath(VIDEO_CHOICE_QUEUE_JSON),
            "total": total,
            "cursor": cursor,
            "remaining": remaining,
            "pending": info.get("pending"),
            "in_progress": info.get("in_progress"),
            "done": info.get("done"),
            "active_choice_id": data.get("active_choice_id") or "",
            "suggest": info.get("suggest"),
            "exported_at": data.get("exported_at"),
        }
        if args.json:
            _print_json(payload)
        else:
            print(f"队列: {payload['path']}")
            print(
                f"合计: {total}  未处理: {payload['pending']}  "
                f"处理中: {payload['in_progress']}  已完成: {payload['done']}"
            )
            print(f"cursor: {cursor}  remaining(旧): {remaining}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

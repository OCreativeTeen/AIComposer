"""Persist StoryProducer run-state on the current story list item as ``workflow``.

The list row stores a ``workflow`` object with ``stage`` / ``infographic_status``
for resume, plus flat helper fields (LM, Gemini files, cover pick, nbi/grv).
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from typing import Any

WORKFLOW_KEY = "workflow"

STAGE_INIT = "INIT"
STAGE_GEMINI_DONE = "GEMINI_DONE"
STAGE_INFOGRAPHIC_PENDING = "INFOGRAPHIC_PENDING"
STAGE_INFOGRAPHIC_DONE = "INFOGRAPHIC_DONE"
STAGE_COMPLETED = "COMPLETED"
STAGES = (
    STAGE_INIT,
    STAGE_GEMINI_DONE,
    STAGE_INFOGRAPHIC_PENDING,
    STAGE_INFOGRAPHIC_DONE,
    STAGE_COMPLETED,
)

INFO_NONE = "NONE"
INFO_SUBMITTED = "SUBMITTED"
INFO_COMPLETED = "COMPLETED"
INFO_FAILED = "FAILED"

TARGET_GEMINI_ONLY = "GEMINI_ONLY"
TARGET_INFOGRAPHIC_ONLY = "INFOGRAPHIC_ONLY"
TARGET_FULL = "FULL_PROCESS"
TARGETS = (TARGET_GEMINI_ONLY, TARGET_INFOGRAPHIC_ONLY, TARGET_FULL)

STAGE_RANK = {
    STAGE_INIT: 0,
    STAGE_GEMINI_DONE: 1,
    STAGE_INFOGRAPHIC_PENDING: 1,
    STAGE_INFOGRAPHIC_DONE: 2,
    STAGE_COMPLETED: 3,
}
TARGET_RANK = {
    TARGET_GEMINI_ONLY: 1,
    TARGET_INFOGRAPHIC_ONLY: 2,
    TARGET_FULL: 3,
}

SCENE_CLIP_KEY = "clip"
SCENE_GROK_CLIP_KEY = "grok_clip"
DEFAULT_CLIP_START = 0.0
DEFAULT_CLIP_END = 10.0
DEFAULT_CLIP_SPEED = 1.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty_workflow() -> dict[str, Any]:
    return {
        "stage": STAGE_INIT,
        "infographic_status": INFO_NONE,
        "selected_infographic_image": None,
        "step": "",
        "updated_at": "",
        "lm_label": "",
        "visual_style": "",
        "narrator": "",
        "instruction": "",
        "nbp_mode": "",
        "nbp_variant": "",
        "nbp_label": "",
        "gemini_pending_regen_choice": False,
        "gemini_pending_pick": False,
        "gemini_files": [],
        "gemini_picked": 0,
        "gemini_picked_path": "",
        "gemini_regen_or_reuse": "",
        "cover_pending_gen_choice": False,
        "cover_gen_choice": "",
        "cover_pending_pick": False,
        "cover_files": [],
        "cover_picked": 0,
        "cover_selected_path": "",
        "cover_expected": 3,
        "cover_existing_count": 0,
        "nbi_index": 0,
        "nbi_profile": "",
        "grv_variant": 3,
        "grv_profile_index": 0,
        "grv_profile": "",
        "grok_clips": [],
        "grok_video_results": [],
        "grv_review_pending": False,
    }


def _lift(out: dict, nested: dict, mapping: dict[str, str]) -> None:
    for old, new in mapping.items():
        if old not in nested:
            continue
        if new not in out or out.get(new) in ("", None, [], 0, False):
            out[new] = copy.deepcopy(nested[old])


def flatten_workflow(raw: dict | None) -> dict[str, Any]:
    """Lift leftover nested gemini/cover/nbi/grv/nbp objects into flat keys."""
    out = dict(raw or {})
    gem = out.pop("gemini", None)
    if isinstance(gem, dict):
        _lift(
            out,
            gem,
            {
                "pending_regen_choice": "gemini_pending_regen_choice",
                "pending_pick": "gemini_pending_pick",
                "files": "gemini_files",
                "picked": "gemini_picked",
                "picked_path": "gemini_picked_path",
                "regen_or_reuse": "gemini_regen_or_reuse",
            },
        )
    cover = out.pop("cover", None)
    if isinstance(cover, dict):
        _lift(
            out,
            cover,
            {
                "pending_gen_choice": "cover_pending_gen_choice",
                "gen_choice": "cover_gen_choice",
                "pending_pick": "cover_pending_pick",
                "files": "cover_files",
                "picked": "cover_picked",
                "selected_path": "cover_selected_path",
                "expected": "cover_expected",
                "existing_count": "cover_existing_count",
            },
        )
    nbi = out.pop("nbi", None)
    if isinstance(nbi, dict):
        _lift(out, nbi, {"index": "nbi_index", "profile": "nbi_profile"})
    grv = out.pop("grv", None)
    if isinstance(grv, dict):
        _lift(
            out,
            grv,
            {
                "variant": "grv_variant",
                "profile_index": "grv_profile_index",
                "profile": "grv_profile",
            },
        )
    nbp = out.pop("nbp", None)
    if isinstance(nbp, dict):
        _lift(
            out,
            nbp,
            {"mode": "nbp_mode", "variant": "nbp_variant", "label": "nbp_label"},
        )
    return out


def get_workflow(item: dict | None) -> dict[str, Any]:
    row = item if isinstance(item, dict) else {}
    raw = row.get(WORKFLOW_KEY)
    base = empty_workflow()
    if not isinstance(raw, dict):
        return base
    return _deep_merge(base, flatten_workflow(raw))


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def persist_workflow(item: dict, patch: dict | None = None) -> dict[str, Any]:
    """Merge *patch* into the story item's top-level ``workflow`` node and write the list row."""
    from cli.video_choice_queue import persist_active_video_detail_field

    wf = get_workflow(item)
    if patch:
        wf = _deep_merge(wf, patch)
    wf = _deep_merge(empty_workflow(), flatten_workflow(wf))
    wf["updated_at"] = _utc_now()
    if isinstance(item, dict):
        item[WORKFLOW_KEY] = wf
    persist_active_video_detail_field(WORKFLOW_KEY, wf)
    return wf


def restore_session_fields(session) -> None:
    """Copy workflow notes back onto the in-memory session after pick."""
    wf = get_workflow(getattr(session, "video_detail", None))
    if wf.get("lm_label"):
        session.lm_label = str(wf.get("lm_label") or "")
    if wf.get("visual_style"):
        session.visual_style = str(wf.get("visual_style") or "")
    if wf.get("narrator"):
        session.narrator = str(wf.get("narrator") or "")
    if wf.get("instruction"):
        session.instruction = str(wf.get("instruction") or "")
    session.gemini_paths = list(wf.get("gemini_files") or [])
    session.gemini_pick = int(wf.get("gemini_picked") or 0)
    session.cover_path = str(
        wf.get("cover_selected_path")
        or (getattr(session, "video_detail", None) or {}).get("cover_image")
        or wf.get("selected_infographic_image")
        or ""
    )
    session.nbi_index = int(wf.get("nbi_index") or 0)
    if int(wf.get("grv_variant") or 0) >= 1:
        session.grv_variant = int(wf.get("grv_variant"))


def _iter_list_workflows(list_path: str):
    path = (list_path or "").strip()
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(arr, list):
        return
    for row in arr:
        if not isinstance(row, dict):
            continue
        wf = row.get(WORKFLOW_KEY)
        if isinstance(wf, dict):
            yield flatten_workflow(wf)


def latest_int_field(list_path: str, field: str) -> int:
    """Most recently updated integer field on any story ``workflow`` in this list."""
    best_i = 0
    best_t = ""
    for wf in _iter_list_workflows(list_path) or []:
        try:
            idx = int(wf.get(field) or 0)
        except (TypeError, ValueError):
            idx = 0
        if idx < 1:
            continue
        ts = str(wf.get("updated_at") or "")
        if ts >= best_t:
            best_t = ts
            best_i = idx
    return best_i


def next_ring_index(last: int, n: int, *, override: int | None = None) -> int:
    size = max(1, int(n or 1))
    if override is not None:
        return max(1, min(int(override), size))
    if last < 1:
        return 1
    return (int(last) % size) + 1


def next_nbi_index(list_path: str, n_profiles: int, *, override: int | None = None) -> int:
    last = latest_int_field(list_path, "nbi_index")
    return next_ring_index(last, n_profiles, override=override)


def next_grv_index(list_path: str, n_profiles: int, *, override: int | None = None) -> int:
    """``grv`` profile：仅 ``config.GROK_IMAGINE_PROFILE_INDICES`` 轮换环（默认 1、6）。"""
    from utility.telegram_session import next_grok_imagine_profile_index

    idx, _ = next_grok_imagine_profile_index(override=override)
    return idx


def list_path_from_session(session) -> str:
    item = getattr(session, "queue_item", None) or {}
    return str(item.get("list_json_path") or "").strip()


def normalize_cover_gen_choice(raw: str) -> str:
    text = (raw or "").strip().lower()
    if text in ("1", "gen", "generate", "yes", "y", "生成", "nbp", "new"):
        return "generate"
    if text in ("2", "skip", "no", "n", "跳过", "itcs", "use", "已有"):
        return "skip"
    return ""


def parse_target_stage(raw: str) -> str:
    text = (raw or "").strip().lower().replace(" ", "").replace("-", "_")
    if text in ("1", "gemini", "gemini_only", "stage1", "scn", "场景", "阶段一"):
        return TARGET_GEMINI_ONLY
    if text in (
        "2",
        "infographic",
        "infographic_only",
        "cover",
        "stage2",
        "封面",
        "阶段二",
    ):
        return TARGET_INFOGRAPHIC_ONLY
    if text in ("3", "full", "full_process", "all", "stage3", "全程", "阶段三", "clips"):
        return TARGET_FULL
    return ""


def scene_clip_path(scene: dict | None) -> str:
    if not isinstance(scene, dict):
        return ""
    return str(scene.get(SCENE_CLIP_KEY) or scene.get(SCENE_GROK_CLIP_KEY) or "").strip()


def scene_has_clip(scene: dict | None) -> bool:
    return bool(scene_clip_path(scene))


def normalize_scene_content(scenes: list | None) -> list:
    """Ensure each scene has a ``clip`` field (null until Grok writes a path)."""
    out: list = []
    for raw in scenes or []:
        if not isinstance(raw, dict):
            continue
        item = copy.deepcopy(raw)
        if SCENE_CLIP_KEY not in item:
            item[SCENE_CLIP_KEY] = None
        out.append(item)
    return out


def apply_scene_clips(scene_content: list, clips: list[dict] | None) -> list:
    """Write ``clip`` (+ legacy ``grok_clip``) and default trim fields."""
    out = copy.deepcopy(scene_content) if isinstance(scene_content, list) else []
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
        if i not in by_scene:
            if SCENE_CLIP_KEY not in item:
                item[SCENE_CLIP_KEY] = None
            continue
        path = by_scene[i]
        item[SCENE_CLIP_KEY] = path
        item[SCENE_GROK_CLIP_KEY] = path
        if item.get("clip_start") in (None, ""):
            item["clip_start"] = DEFAULT_CLIP_START
        if item.get("clip_end") in (None, ""):
            item.pop("clip_end", None)
        if item.get("clip_speed") in (None, ""):
            item["clip_speed"] = DEFAULT_CLIP_SPEED
    return out


def persist_scene_clips(clips: list[dict] | None) -> tuple[bool, str]:
    """Copy clips into gen_video and write ``scene_content[].clip``."""
    from cli.video_choice_queue import save_grok_clips_to_active_video_detail

    return save_grok_clips_to_active_video_detail(list(clips or []))


def infer_stage(video_detail: dict | None) -> str:
    """Derive ``workflow.stage`` from persisted fields + scene/cover/clip data."""
    row = video_detail if isinstance(video_detail, dict) else {}
    wf = get_workflow(row)
    declared = str(wf.get("stage") or "").strip().upper()
    if declared not in STAGES:
        declared = ""

    scenes = row.get("scene_content")
    has_scenes = isinstance(scenes, list) and bool(scenes)
    clips_all = bool(has_scenes) and all(scene_has_clip(s) for s in scenes)

    cover = str(
        row.get("cover_image") or wf.get("selected_infographic_image") or ""
    ).strip()
    info = str(wf.get("infographic_status") or INFO_NONE).strip().upper()

    if clips_all:
        return STAGE_COMPLETED
    if cover:
        return STAGE_INFOGRAPHIC_DONE
    if info == INFO_SUBMITTED or declared == STAGE_INFOGRAPHIC_PENDING:
        return STAGE_INFOGRAPHIC_PENDING
    # ``workflow.stage=GEMINI_DONE`` alone is not enough — scene_content must exist.
    if has_scenes:
        return STAGE_GEMINI_DONE
    return STAGE_INIT


def meets_target(stage: str, target: str) -> bool:
    st = (stage or STAGE_INIT).strip().upper()
    tg = (target or TARGET_FULL).strip().upper()
    if tg not in TARGET_RANK:
        tg = TARGET_FULL
    if tg == TARGET_FULL:
        return st == STAGE_COMPLETED
    return STAGE_RANK.get(st, 0) >= TARGET_RANK.get(tg, 3)


def preview_scene_json(path: str, *, limit: int = 8) -> str:
    p = (path or "").strip()
    if not p:
        return "（无文件）"
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return f"（无法读取：{exc}）"
    if not isinstance(data, list):
        return "（不是场景数组）"
    lines: list[str] = []
    for i, sc in enumerate(data[:limit], 1):
        if not isinstance(sc, dict):
            continue
        cap = str(sc.get("caption") or "").strip() or "（无 caption）"
        lines.append(f"  {i}. {cap}")
    if len(data) > limit:
        lines.append(f"  … 共 {len(data)} 场")
    return "\n".join(lines) or "（空）"


def find_next_unfinished_index(
    target: str,
    *,
    skip_ids: set[str] | None = None,
) -> int | None:
    """1-based queue index of the next story that has not reached *target*."""
    from cli.video_choice_queue import (
        STATUS_DONE,
        list_queue_items,
        normalize_item_status,
        resolve_video_detail_from_queue_item,
    )

    skip = {str(x).strip() for x in (skip_ids or set()) if str(x).strip()}
    tg = (target or TARGET_FULL).strip().upper() or TARGET_FULL
    for i, it in enumerate(list_queue_items(), 1):
        if not isinstance(it, dict):
            continue
        cid = str(it.get("choice_id") or "").strip()
        if cid and cid in skip:
            continue
        if normalize_item_status(it) == STATUS_DONE:
            continue
        vd = resolve_video_detail_from_queue_item(it)
        stage = infer_stage(vd if isinstance(vd, dict) else {})
        if meets_target(stage, tg):
            continue
        return i
    return None


def any_unfinished_needs_gemini(
    target: str,
    *,
    skip_ids: set[str] | None = None,
) -> bool:
    """True if any not-yet-finished queue item is still at INIT (needs scnge)."""
    from cli.video_choice_queue import (
        STATUS_DONE,
        list_queue_items,
        normalize_item_status,
        resolve_video_detail_from_queue_item,
    )

    skip = {str(x).strip() for x in (skip_ids or set()) if str(x).strip()}
    tg = (target or TARGET_FULL).strip().upper() or TARGET_FULL
    for it in list_queue_items():
        if not isinstance(it, dict):
            continue
        cid = str(it.get("choice_id") or "").strip()
        if cid and cid in skip:
            continue
        if normalize_item_status(it) == STATUS_DONE:
            continue
        vd = resolve_video_detail_from_queue_item(it)
        stage = infer_stage(vd if isinstance(vd, dict) else {})
        if meets_target(stage, tg):
            continue
        if stage == STAGE_INIT:
            return True
    return False


def story_clip_paths(video_detail: dict | None) -> list[str]:
    """Ordered mp4 paths from ``scene_content[].clip`` (scene 1→N)."""
    return [
        str(seg.get("path") or "")
        for seg in story_clip_segments(video_detail)
        if str(seg.get("path") or "").strip()
    ]


def story_clip_segments(video_detail: dict | None) -> list[dict]:
    """Ordered clip segments from ``scene_content`` (scene 1→N)."""
    from cli.video_choice_queue import grok_clip_segments_from_scene_content

    row = video_detail if isinstance(video_detail, dict) else {}
    sc = row.get("scene_content")
    return grok_clip_segments_from_scene_content(sc if isinstance(sc, list) else [])


def story_has_all_clips(video_detail: dict | None) -> bool:
    row = video_detail if isinstance(video_detail, dict) else {}
    scenes = row.get("scene_content")
    if not isinstance(scenes, list) or not scenes:
        return False
    return all(scene_has_clip(s) for s in scenes if isinstance(s, dict))


def story_has_any_clips(video_detail: dict | None) -> bool:
    return bool(story_clip_paths(video_detail))


def find_next_clip_ready_index(
    *,
    skip_ids: set[str] | None = None,
    require_all: bool = True,
    skip_published: bool = False,
) -> int | None:
    """1-based queue index of the next story that has scene clip(s) for GUI review."""
    from cli.video_choice_queue import list_queue_items, resolve_video_detail_from_queue_item

    skip = {str(x).strip() for x in (skip_ids or set()) if str(x).strip()}
    for i, it in enumerate(list_queue_items(), 1):
        if not isinstance(it, dict):
            continue
        cid = str(it.get("choice_id") or "").strip()
        if cid and cid in skip:
            continue
        vd = resolve_video_detail_from_queue_item(it)
        row = vd if isinstance(vd, dict) else {}
        if require_all:
            if not story_has_all_clips(row):
                continue
        elif not story_has_any_clips(row):
            continue
        if skip_published and (
            str(row.get("video") or "").strip()
            or str(row.get("publish") or "").strip()
        ):
            continue
        return i
    return None


def story_gui_review_done(item: dict | None, *, session_reviewed: set[str] | None = None) -> bool:
    """True if this queue row was marked done in run_gui (session or queue JSON)."""
    if not isinstance(item, dict):
        return False
    cid = str(item.get("choice_id") or "").strip()
    reviewed = session_reviewed or set()
    if cid and cid in reviewed:
        return True
    if (item.get("gui_review_done_at") or "").strip():
        return True
    step = (item.get("workflow_step") or "").strip().lower()
    from cli.video_choice_queue import WORKFLOW_STEP_GUI_REVIEW_DONE

    return step == WORKFLOW_STEP_GUI_REVIEW_DONE


def format_gui_pick_menu(
    *,
    session_reviewed: set[str] | None = None,
    require_all: bool = True,
) -> str:
    """Interactive run_gui menu: list all stories + clip / GUI-review status."""
    from cli.video_choice_queue import list_queue_items, resolve_video_detail_from_queue_item

    items = list_queue_items()
    if not items:
        return "队列是空的。"
    lines = [
        "请选要 GUI 审阅的故事（回复序号 1 / 2 / 3 …）：",
        "发 list 刷新列表；exit 结束。可重复选已审阅的条目。",
        "有 clip 即可打开（未齐全会载入已有片段）。",
        "",
    ]
    reviewed = session_reviewed or set()
    suggest: int | None = None
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        vd = resolve_video_detail_from_queue_item(it)
        row = vd if isinstance(vd, dict) else {}
        clips = story_clip_paths(row)
        scenes = row.get("scene_content")
        n_sc = len(scenes) if isinstance(scenes, list) else 0
        title = (
            (it.get("title") or row.get("title") or "")
            .strip()
            or "?"
        )[:48]
        if story_has_all_clips(row):
            clip_mark = "全clip"
        elif clips:
            clip_mark = f"{len(clips)}/{n_sc} clip"
        else:
            clip_mark = "无clip"
        if story_gui_review_done(it, session_reviewed=reviewed):
            gui_mark = "✓GUI已审阅"
        else:
            gui_mark = "未审阅"
            if suggest is None and clips:
                suggest = i
        video_mark = " [有成片]" if str(row.get("video") or "").strip() else ""
        lines.append(f"{i}. [{gui_mark}] [{clip_mark}] {title}{video_mark}")
    if suggest is not None:
        lines.append(f"\n建议下一条未审阅：{suggest}")
    return "\n".join(lines)


def format_clip_queue_progress() -> str:
    from cli.video_choice_queue import list_queue_items, resolve_video_detail_from_queue_item

    lines = ["队列 clip 进度（GUI 审阅）："]
    items = list_queue_items()
    if not items:
        return "队列是空的。"
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        vd = resolve_video_detail_from_queue_item(it)
        row = vd if isinstance(vd, dict) else {}
        clips = story_clip_paths(row)
        scenes = row.get("scene_content")
        n_sc = len(scenes) if isinstance(scenes, list) else 0
        title = (
            (it.get("title") or row.get("title") or "")
            .strip()
            or "?"
        )[:48]
        mark = ""
        if story_has_all_clips(row):
            mark = " ✓全clip"
        elif clips:
            mark = f" ({len(clips)}/{n_sc} clip)"
        else:
            mark = " (无clip)"
        if str(row.get("video") or "").strip():
            mark += " [有成片]"
        lines.append(f"{i}. {title}{mark}")
    return "\n".join(lines)


def format_queue_progress(target: str = TARGET_FULL) -> str:
    from cli.video_choice_queue import list_queue_items, resolve_video_detail_from_queue_item

    tg = (target or TARGET_FULL).strip().upper() or TARGET_FULL
    lines = ["队列进度："]
    items = list_queue_items()
    if not items:
        return "队列是空的。"
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        vd = resolve_video_detail_from_queue_item(it)
        row = vd if isinstance(vd, dict) else {}
        stage = infer_stage(row)
        title = (
            (it.get("title") or row.get("title") or "")
            .strip()
            or "?"
        )[:48]
        done = " ✓" if meets_target(stage, tg) else ""
        lines.append(f"{i}. [{stage}] {title}{done}")
    return "\n".join(lines)

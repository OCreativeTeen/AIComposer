"""Single source of truth for Grok scene clips: ``workflow.grok_video_results``."""

from __future__ import annotations

import copy
import os
from typing import Any

from utility.clip_trim import clip_end_means_full_length

DEFAULT_CLIP_START = 0.0
DEFAULT_CLIP_SPEED = 1.0

SCENE_CLIP_LEGACY_KEYS = (
    "clip",
    "grok_clip",
    "clip_start",
    "clip_end",
    "clip_speed",
)

WORKFLOW_LEGACY_CLIP_KEYS = (
    "grok_clips",
    "grok_download_results",
)


def _scene_int(raw: object) -> int:
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def normalize_grok_video_result(raw: dict | None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    scene = _scene_int(raw.get("scene"))
    if scene < 1:
        return None
    out: dict[str, Any] = {"scene": scene}
    status = str(raw.get("status") or "").strip()
    if status:
        out["status"] = status
    label = str(raw.get("label") or "").strip()
    if label:
        out["label"] = label
    err = str(raw.get("error") or "").strip()
    if err:
        out["error"] = err
    path = str(raw.get("path") or "").strip()
    if path:
        out["path"] = os.path.normpath(os.path.abspath(path))
    dl = str(raw.get("download_path") or "").strip()
    if dl:
        out["download_path"] = os.path.normpath(os.path.abspath(dl))
    try:
        out["clip_start"] = float(raw.get("clip_start", DEFAULT_CLIP_START))
    except (TypeError, ValueError):
        out["clip_start"] = DEFAULT_CLIP_START
    end_raw = raw.get("clip_end", raw.get("end"))
    if end_raw in (None, "") or clip_end_means_full_length(end_raw):
        out.pop("clip_end", None)
    else:
        try:
            out["clip_end"] = float(end_raw)
        except (TypeError, ValueError):
            out.pop("clip_end", None)
    try:
        out["clip_speed"] = float(raw.get("clip_speed", raw.get("speed", DEFAULT_CLIP_SPEED)))
    except (TypeError, ValueError):
        out["clip_speed"] = DEFAULT_CLIP_SPEED
    return out


def _index_results(results: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for item in results or []:
        rec = normalize_grok_video_result(item)
        if rec:
            out[int(rec["scene"])] = rec
    return out


def _merge_rec(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if v in (None, ""):
            continue
        out[k] = copy.deepcopy(v)
    return normalize_grok_video_result(out) or out


def build_grok_video_results_from_legacy(video_detail: dict | None) -> list[dict]:
    """Merge ``grok_video_results`` + legacy workflow/scene_content clip fields."""
    from storyproducer.workflow import get_workflow

    row = video_detail if isinstance(video_detail, dict) else {}
    wf = get_workflow(row)
    by_scene = _index_results(list(wf.get("grok_video_results") or []))

    for item in wf.get("grok_clips") or []:
        if not isinstance(item, dict):
            continue
        scene = _scene_int(item.get("scene"))
        if scene < 1:
            continue
        cur = by_scene.get(scene, {"scene": scene})
        p = str(item.get("path") or "").strip()
        patch: dict[str, Any] = {}
        if p:
            patch["path"] = p
        if not cur.get("status"):
            patch["status"] = "ok"
        by_scene[scene] = _merge_rec(cur, patch)

    for item in wf.get("grok_download_results") or []:
        if not isinstance(item, dict):
            continue
        scene = _scene_int(item.get("scene"))
        if scene < 1:
            continue
        cur = by_scene.get(scene, {"scene": scene})
        p = str(item.get("path") or "").strip()
        patch: dict[str, Any] = {}
        if p:
            patch["download_path"] = p
            if not cur.get("path"):
                patch["path"] = p
        st = str(item.get("status") or "").strip()
        if st:
            patch["status"] = st
        err = str(item.get("error") or "").strip()
        if err:
            patch["error"] = err
        by_scene[scene] = _merge_rec(cur, patch)

    sc = row.get("scene_content")
    if isinstance(sc, list):
        for i, item in enumerate(sc, 1):
            if not isinstance(item, dict):
                continue
            p = str(item.get("clip") or item.get("grok_clip") or "").strip()
            if not p:
                continue
            cur = by_scene.get(i, {"scene": i})
            patch: dict[str, Any] = {"path": p}
            if item.get("clip_start") not in (None, ""):
                patch["clip_start"] = item.get("clip_start")
            if item.get("clip_end") not in (None, ""):
                patch["clip_end"] = item.get("clip_end")
            if item.get("clip_speed") not in (None, ""):
                patch["clip_speed"] = item.get("clip_speed")
            if not cur.get("status"):
                patch["status"] = "ok"
            by_scene[i] = _merge_rec(cur, patch)

    return [
        normalize_grok_video_result(by_scene[k])
        for k in sorted(by_scene)
        if normalize_grok_video_result(by_scene[k])
    ]


def get_grok_video_results(
    video_detail: dict | None, *, migrate: bool = True
) -> list[dict]:
    from storyproducer.workflow import get_workflow

    row = video_detail if isinstance(video_detail, dict) else {}
    wf = get_workflow(row)
    raw = list(wf.get("grok_video_results") or [])
    if raw:
        out = [
            rec
            for rec in (normalize_grok_video_result(x) for x in raw)
            if rec
        ]
        if out:
            return out
    if migrate:
        return build_grok_video_results_from_legacy(row)
    return []


def grok_video_result_for_scene(video_detail: dict | None, scene: int) -> dict | None:
    n = _scene_int(scene)
    if n < 1:
        return None
    for rec in get_grok_video_results(video_detail):
        if int(rec.get("scene") or 0) == n:
            return rec
    return None


def scene_has_grok_clip(video_detail: dict | None, scene: int) -> bool:
    n = _scene_int(scene)
    if n < 1:
        return False
    for rec in get_grok_video_results(video_detail):
        if _scene_int(rec.get("scene")) != n:
            continue
        p = str(rec.get("path") or "").strip()
        if p and os.path.isfile(p):
            return True
    return False


def grok_clip_segment_from_result(rec: dict | None) -> dict | None:
    norm = normalize_grok_video_result(rec)
    if not norm:
        return None
    p = str(norm.get("path") or "").strip()
    if not p or not os.path.isfile(p) or not p.lower().endswith(".mp4"):
        return None
    end_raw = norm.get("clip_end")
    end = None if clip_end_means_full_length(end_raw) else end_raw
    return {
        "scene": int(norm.get("scene") or 0),
        "path": p,
        "start": float(norm.get("clip_start", DEFAULT_CLIP_START)),
        "end": end,
        "speed": float(norm.get("clip_speed", DEFAULT_CLIP_SPEED)),
    }


def grok_clip_segments_from_video_detail(video_detail: dict | None) -> list[dict]:
    """Review/concat segments in ``grok_video_results`` list order (duplicates allowed)."""
    row = video_detail if isinstance(video_detail, dict) else {}
    out: list[dict] = []
    for rec in get_grok_video_results(row):
        seg = grok_clip_segment_from_result(rec)
        if seg:
            out.append(seg)
    return out


def grok_clip_paths_from_video_detail(video_detail: dict | None) -> list[str]:
    return [
        str(seg.get("path") or "")
        for seg in grok_clip_segments_from_video_detail(video_detail)
        if str(seg.get("path") or "").strip()
    ]


def strip_scene_content_clip_fields(scene_content: list | None) -> list:
    out: list = []
    for raw in scene_content or []:
        if not isinstance(raw, dict):
            out.append(raw)
            continue
        item = copy.deepcopy(raw)
        for key in SCENE_CLIP_LEGACY_KEYS:
            item.pop(key, None)
        out.append(item)
    return out


def strip_workflow_clip_legacy(wf: dict | None) -> dict:
    out = copy.deepcopy(wf) if isinstance(wf, dict) else {}
    for key in WORKFLOW_LEGACY_CLIP_KEYS:
        out.pop(key, None)
    return out


def merge_generation_results(
    existing: list[dict] | None, generated: list[dict] | None
) -> list[dict]:
    by_scene = _index_results(existing or [])
    for item in generated or []:
        if not isinstance(item, dict):
            continue
        scene = _scene_int(item.get("scene"))
        if scene < 1:
            continue
        cur = by_scene.get(scene, {"scene": scene})
        patch = {
            "status": item.get("status"),
            "label": item.get("label"),
            "error": item.get("error"),
        }
        by_scene[scene] = _merge_rec(cur, patch)
    return [
        normalize_grok_video_result(by_scene[k])
        for k in sorted(by_scene)
        if normalize_grok_video_result(by_scene[k])
    ]


def _download_patch(item: dict) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    p = str(item.get("path") or "").strip()
    if p:
        patch["path"] = p
    dl = str(item.get("download_path") or "").strip()
    if dl:
        patch["download_path"] = dl
    st = str(item.get("status") or "").strip()
    if st:
        patch["status"] = st
    for key in ("clip_start", "clip_end", "clip_speed", "label", "error"):
        if item.get(key) not in (None, ""):
            patch[key] = item.get(key)
    if "status" not in patch:
        patch["status"] = "ok"
    return patch


def merge_download_clips(
    existing: list[dict] | None, clips: list[dict] | None
) -> list[dict]:
    """Merge download paths into results; preserve list order and duplicate scenes."""
    dl_map: dict[int, dict] = {}
    for item in clips or []:
        if not isinstance(item, dict):
            continue
        scene = _scene_int(item.get("scene"))
        if scene >= 1:
            dl_map[scene] = item

    existing_norm = [
        rec
        for rec in (normalize_grok_video_result(x) for x in (existing or []))
        if rec
    ]
    if not existing_norm:
        return [
            normalize_grok_video_result({"scene": s, **_download_patch(item)})
            for s, item in sorted(dl_map.items())
            if normalize_grok_video_result({"scene": s, **_download_patch(item)})
        ]

    out: list[dict] = []
    updated: set[int] = set()
    for rec in existing_norm:
        scene = _scene_int(rec.get("scene"))
        if scene in dl_map and scene not in updated:
            updated.add(scene)
            merged = _merge_rec(rec, _download_patch(dl_map[scene]))
            out.append(merged if merged else rec)
        else:
            out.append(rec)
    for scene, item in sorted(dl_map.items()):
        if scene in updated:
            continue
        merged = normalize_grok_video_result({"scene": scene, **_download_patch(item)})
        if merged:
            out.append(merged)
    return out


def apply_review_segments(
    existing: list[dict] | None, segments: list[dict] | None
) -> list[dict]:
    """Replace timeline from review dialog (order preserved; same scene may repeat)."""
    meta_by_scene = _index_results(existing or [])
    out: list[dict] = []
    for i, seg in enumerate(segments or [], 1):
        if not isinstance(seg, dict):
            continue
        scene = _scene_int(seg.get("scene") or i)
        if scene < 1:
            scene = i
        base = meta_by_scene.get(scene, {"scene": scene})
        patch: dict[str, Any] = {
            "scene": scene,
            "path": seg.get("path"),
            "clip_start": seg.get("start", seg.get("clip_start", DEFAULT_CLIP_START)),
            "clip_end": seg.get("end", seg.get("clip_end")),
            "clip_speed": seg.get("speed", seg.get("clip_speed", DEFAULT_CLIP_SPEED)),
            "status": base.get("status") or "ok",
        }
        for key in ("label", "error", "download_path"):
            if base.get(key):
                patch[key] = base.get(key)
        norm = normalize_grok_video_result(_merge_rec(base, patch))
        if norm:
            out.append(norm)
    return out


def story_has_all_clips(video_detail: dict | None) -> bool:
    row = video_detail if isinstance(video_detail, dict) else {}
    scenes = row.get("scene_content")
    if not isinstance(scenes, list) or not scenes:
        return False
    for i in range(1, len(scenes) + 1):
        if not scene_has_grok_clip(row, i):
            return False
    return True


def story_has_any_clips(video_detail: dict | None) -> bool:
    return bool(grok_clip_paths_from_video_detail(video_detail))

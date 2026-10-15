"""generated-video file lookup (moved verbatim from gui/dl/list_store.py)."""
import os
import config
import project_manager
from utility.file_util import _sanitize_list_row_id_stem
from gui.dl.row_keys import _video_youtube_id
from datetime import datetime
from utility.file_util import _read_plain_text_file


GEN_VIDEO_SLIDE_KEY = "slide"


def _video_detail_project_pid(vd) -> str:
    """列表项绑定的工作流 pid（仅 ``project_profile.pid``）。"""
    return project_manager.list_json_row_workflow_pid(vd if isinstance(vd, dict) else {})


def _gen_video_id_stem_candidates_for_row(video: dict) -> list[str]:
    """匹配 / 命名 gen_video 里 ``<stem>.mp4`` 的候选 stem（有序、去重）。
    含外层 ``id``、YouTube id、``project_profile.pid`` 及旧字段。"""
    if not isinstance(video, dict):
        return []
    ordered: list[str] = []
    seen: set[str] = set()

    def add_raw(raw: object) -> None:
        s = _sanitize_list_row_id_stem(str(raw or "").strip())
        if s and s not in seen:
            seen.add(s)
            ordered.append(s)

    add_raw(video.get("id"))
    add_raw(_video_youtube_id(video))
    add_raw(video.get("youtube_id"))
    pp = video.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(pp, dict):
        add_raw(pp.get("youtube_video_id"))
        add_raw(pp.get("youtube_id"))
        add_raw(pp.get("video_id"))
        add_raw(pp.get("source_video_id"))
    add_raw(_video_detail_project_pid(video))
    return ordered


def _find_gen_video_slide_for_row(video: dict) -> str:
    """``gen_video/<id>.pdf`` 或 video_detail['slide'] 记录的幻灯片路径。"""
    if not isinstance(video, dict):
        return ""
    stored = (video.get(GEN_VIDEO_SLIDE_KEY) or "").strip()
    if stored and os.path.isfile(stored):
        return os.path.abspath(stored)
    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if not gen_dir:
        return ""
    for stem in _gen_video_id_stem_candidates_for_row(video):
        p = os.path.join(gen_dir, stem + ".pdf")
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""


# --- moved from gui/downloader.py: generated-video file lookup ---
def _gen_video_watermark_dest_filename(video_detail: dict | None) -> str:
    """按 ``_gen_video_id_stem_candidates_for_row`` 顺序选用 stem（与条目 ``id`` 一致）；均无则时间戳。"""
    if isinstance(video_detail, dict):
        for stem in _gen_video_id_stem_candidates_for_row(video_detail):
            if stem:
                return stem + ".mp4"
    return datetime.now().strftime("%Y%m%d_%H%M%S") + ".mp4"


def _gen_video_cover_webp_dest_filename(
    video_detail: dict | None = None,
    *,
    source_image_path: str = "",
) -> str:
    """封面 webp 目标名：保留源图文件名（NotebookLM artifact 标题），否则回退 id stem。"""
    stem = _title_from_cover_image_path(source_image_path)
    if stem and not stem.startswith("_itc"):
        return stem + ".webp"
    if isinstance(video_detail, dict):
        for cand in _gen_video_id_stem_candidates_for_row(video_detail):
            if cand:
                return cand + ".webp"
    return datetime.now().strftime("%Y%m%d_%H%M%S") + ".webp"


GEN_VIDEO_CLIP_SEGMENTS_KEY = "gen_video_clip_segments"


def _normalize_gen_video_clip_segment(seg) -> dict | None:
    if not isinstance(seg, dict):
        return None
    from utility.clip_trim import clip_end_means_full_length

    p = (seg.get("path") or "").strip()
    if not p:
        return None
    p = os.path.normpath(p)
    if not os.path.isfile(p):
        return None
    try:
        start = float(seg.get("start", 0.0))
        speed = round(float(seg.get("speed") or 1.0), 1)
    except (TypeError, ValueError):
        return None
    end_raw = seg.get("end")
    out: dict = {"path": p, "start": start, "speed": speed}
    try:
        scene = int(seg.get("scene") or 0)
        if scene >= 1:
            out["scene"] = scene
    except (TypeError, ValueError):
        pass
    if end_raw not in (None, "") and not clip_end_means_full_length(end_raw):
        try:
            out["end"] = float(end_raw)
        except (TypeError, ValueError):
            pass
    return out


def _get_gen_video_clip_segments(video_detail: dict) -> list[dict]:
    """审阅窗片段：``workflow.grok_video_results``，旧数据回退 ``gen_video_clip_segments``。"""
    if not isinstance(video_detail, dict):
        return []
    from utility.grok_video_results import grok_clip_segments_from_video_detail

    from_results: list[dict] = []
    for seg in grok_clip_segments_from_video_detail(video_detail):
        n = _normalize_gen_video_clip_segment(seg)
        if n:
            from_results.append(n)
    if from_results:
        return from_results
    raw = video_detail.get(GEN_VIDEO_CLIP_SEGMENTS_KEY)
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for seg in raw:
        n = _normalize_gen_video_clip_segment(seg)
        if n:
            out.append(n)
    return out


def _set_gen_video_clip_segments(video_detail: dict, segments: list[dict]) -> None:
    """把审阅结果写入 ``workflow.grok_video_results``（含 path / clip_start / clip_end）。"""
    if not isinstance(video_detail, dict):
        return
    from storyproducer.workflow import WORKFLOW_KEY, get_workflow
    from utility.gen_video_store import copy_into_gen_video
    from utility.grok_video_results import (
        apply_review_segments,
        build_grok_video_results_from_legacy,
        strip_scene_content_clip_fields,
        strip_workflow_clip_legacy,
    )

    normalized: list[dict] = []
    for seg in segments or []:
        n = _normalize_gen_video_clip_segment(seg)
        if not n:
            continue
        src = n["path"]
        try:
            n["path"] = copy_into_gen_video(src)
        except Exception as exc:
            print(f"copy clip to gen_video failed: {exc}")
        normalized.append(n)

    existing = build_grok_video_results_from_legacy(video_detail)
    merged = apply_review_segments(existing, normalized)
    wf = strip_workflow_clip_legacy(get_workflow(video_detail))
    wf["grok_video_results"] = merged
    video_detail[WORKFLOW_KEY] = wf
    sc = video_detail.get("scene_content")
    if isinstance(sc, list):
        video_detail["scene_content"] = strip_scene_content_clip_fields(sc)
    video_detail.pop(GEN_VIDEO_CLIP_SEGMENTS_KEY, None)


STORY_MEDIA_KEY = "media"


STORY_TRANSCRIPT_KEY = "transcript"


def _find_item_media_file(video: dict) -> str:
    if not isinstance(video, dict):
        return ""
    stored = (video.get(STORY_MEDIA_KEY) or "").strip()
    if stored and os.path.isfile(stored):
        return os.path.abspath(stored)
    return ""


def _find_item_transcript_file(video: dict) -> str:
    """这条的媒体文字稿（带时间戳、说话人）。没有或文件不在就返回空字符串。"""
    if not isinstance(video, dict):
        return ""
    stored = (video.get(STORY_TRANSCRIPT_KEY) or "").strip()
    if stored and os.path.isfile(stored):
        return os.path.abspath(stored)
    # 记录里没有时，看媒体旁边有没有同名的 .txt（文字稿和媒体同名，只是扩展名不同）。
    media = _find_item_media_file(video)
    if media:
        guess = os.path.splitext(media)[0] + ".txt"
        if os.path.isfile(guess):
            return os.path.abspath(guess)
    return ""


def _item_transcript_text(video: dict) -> tuple[str, str]:
    """(文字稿路径, 文字稿内容)。没有文字稿或内容是空的，返回 ("", "")。"""
    path = _find_item_transcript_file(video)
    if not path:
        return "", ""
    try:
        text = _read_plain_text_file(path).strip()
    except OSError:
        return "", ""
    return (path, text) if text else ("", "")


def _gen_video_slide_pdf_dest_filename(video_detail: dict | None) -> str:
    """幻灯片 PDF：与成片 mp4 同 stem，扩展名为 ``.pdf``（``gen_video/<id>.pdf``）。"""
    if isinstance(video_detail, dict):
        for stem in _gen_video_id_stem_candidates_for_row(video_detail):
            if stem:
                return stem + ".pdf"
    return datetime.now().strftime("%Y%m%d_%H%M%S") + ".pdf"


def _title_from_cover_image_path(image_path: str) -> str:
    """封面图路径 → 文件名（无扩展名）。"""
    base = os.path.basename((image_path or "").strip())
    stem, _ = os.path.splitext(base)
    return (stem or base).strip()


def _find_gen_video_mp4_for_row(video: dict) -> str:
    if isinstance(video, dict):
        stored = (video.get("video") or "").strip()
        if stored and os.path.isfile(stored):
            return os.path.abspath(stored)
    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if not gen_dir:
        return ""
    try:
        os.makedirs(gen_dir, exist_ok=True)
    except OSError:
        pass
    if not isinstance(video, dict):
        return ""
    for stem in _gen_video_id_stem_candidates_for_row(video):
        p = os.path.join(gen_dir, stem + ".mp4")
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""


def _find_gen_video_webp_for_row(video: dict) -> str:
    """封面：优先故事 ``cover_image``（首张），否则 ``gen_video/<id>.webp``。"""
    if isinstance(video, dict):
        stored = project_manager.get_primary_cover_image(video)
        if stored:
            return stored
    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if not gen_dir:
        return ""
    if not isinstance(video, dict):
        return ""
    for stem in _gen_video_id_stem_candidates_for_row(video):
        p = os.path.join(gen_dir, stem + ".webp")
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""


def _gen_video_storage_dir() -> str:
    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if gen_dir:
        try:
            os.makedirs(gen_dir, exist_ok=True)
        except OSError:
            pass
    return gen_dir

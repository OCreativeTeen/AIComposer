"""成片处理：裁剪（可选）→ 末帧延长 → 拼接 → 水印 → publish/gen_video。

两条入口共用同一套 ffmpeg 流程：

- CLI ``video_concat``：不裁剪、不变速，按 Telegram 记下的场景顺序拼接。
- ``SummaryMp4ReviewDialog``：审阅窗只负责裁剪/排序 UI，确认后调用这里
  （带 start/end/speed）。
"""
from __future__ import annotations

import os
import threading
from datetime import datetime

import config
import project_manager
from utility.ffmpeg_processor import FfmpegProcessor, resolve_watermark_for_channel
from utility.file_util import safe_copy_overwrite, safe_remove

# 与原先 SummaryMp4ReviewDialog 确认后的定格时长一致
CLIP_END_FREEZE_SEC = 0.66


def _sanitize_stem(raw_id: str) -> str:
    rid = (raw_id or "").strip()
    if not rid:
        return ""
    bad = '\\/:*?"<>|\r\n\t'
    s = "".join(c if c not in bad else "_" for c in rid)
    return s[:200] if len(s) > 200 else s


def gen_video_dest_filename(video_detail: dict | None) -> str:
    """与摘要窗审阅保存相同：``gen_video/<id>.mp4``（优先条目 id）。"""
    if isinstance(video_detail, dict):
        ordered: list[str] = []

        def add(raw) -> None:
            stem = _sanitize_stem(str(raw or ""))
            if stem and stem not in ordered:
                ordered.append(stem)

        add(video_detail.get("id"))
        add(video_detail.get("youtube_id"))
        pp = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
        if isinstance(pp, dict):
            add(pp.get("youtube_video_id"))
            add(pp.get("youtube_id"))
            add(pp.get("video_id"))
            add(pp.get("source_video_id"))
            add(pp.get("pid"))
        add(project_manager.list_json_row_workflow_pid(video_detail))
        if ordered:
            return ordered[0] + ".mp4"
    return datetime.now().strftime("%Y%m%d_%H%M%S") + ".mp4"


def _paths_in_scene_order(clips: list[dict] | list[str]) -> list[str]:
    rows: list[tuple[int, str]] = []
    for i, item in enumerate(clips or [], 1):
        if isinstance(item, str):
            p = os.path.normpath(os.path.abspath(item.strip()))
            scene = i
        elif isinstance(item, dict):
            p = os.path.normpath(os.path.abspath((item.get("path") or "").strip()))
            try:
                scene = int(item.get("scene") or i)
            except (TypeError, ValueError):
                scene = i
        else:
            continue
        if p and os.path.isfile(p):
            rows.append((scene, p))
    rows.sort(key=lambda x: x[0])
    return [p for _, p in rows]


def _normalize_segments(segments: list[dict]) -> list[dict]:
    out: list[dict] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        p = os.path.normpath(os.path.abspath((seg.get("path") or "").strip()))
        if not p or not os.path.isfile(p):
            continue
        item = {"path": p}
        if "start" in seg:
            item["start"] = float(seg.get("start") or 0.0)
        if "end" in seg:
            item["end"] = float(seg.get("end") or 0.0)
        if "speed" in seg:
            item["speed"] = float(seg.get("speed") or 1.0)
        out.append(item)
    return out


def _resolve_dest_abs(
    *,
    dest_abs: str = "",
    gen_dir: str = "",
    dest_name: str = "",
    video_detail: dict | None = None,
) -> str:
    if (dest_abs or "").strip():
        return os.path.abspath(dest_abs.strip())
    folder = (gen_dir or getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or "").strip()
    if not folder:
        raise RuntimeError("未配置 INPUT_MEDIA_GEN_VIDEO_PATH（publish/gen_video）")
    name = (dest_name or "").strip() or gen_video_dest_filename(video_detail)
    return os.path.abspath(os.path.join(folder, name))


def _resolve_watermark(
    *,
    wm_path: str = "",
    wm_opts: dict | None = None,
    channel_key: str = "",
) -> tuple[str, dict]:
    path = (wm_path or "").strip()
    if path and os.path.isfile(path):
        return path, dict(wm_opts or {})
    found, opts = resolve_watermark_for_channel(channel_key or "")
    if not found:
        raise RuntimeError(
            r"未找到水印 PNG（请放在 program/<频道>/ 下，或配置频道 watermark.path）。"
        )
    return found, dict(opts or wm_opts or {})


def concat_segments_to_gen_video(
    segments: list[dict],
    *,
    pid: str,
    lang: str,
    dest_abs: str = "",
    gen_dir: str = "",
    dest_name: str = "",
    video_detail: dict | None = None,
    wm_path: str = "",
    wm_opts: dict | None = None,
    channel_key: str = "",
    trim: bool = True,
) -> str:
    """裁剪（可选）→ 末帧延长 → 拼接 → 水印，写入 dest。

    ``segments``：``[{path, start?, end?, speed?}, ...]``，顺序即拼接顺序。
    ``trim=False`` 时跳过裁剪/变速（CLI 自动成片）。
    返回成片绝对路径；失败抛 ``RuntimeError``。
    """
    segs = _normalize_segments(segments)
    if not segs:
        raise RuntimeError("没有可拼接的 mp4")

    out_abs = _resolve_dest_abs(
        dest_abs=dest_abs,
        gen_dir=gen_dir,
        dest_name=dest_name,
        video_detail=video_detail,
    )
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    wm_file, wm_use = _resolve_watermark(
        wm_path=wm_path, wm_opts=wm_opts, channel_key=channel_key
    )

    work_pid = pid or "yt_wm"
    ff = FfmpegProcessor(work_pid, lang or "zh")
    stage_tmps: list[str] = []
    concat_tmp = ""
    wm_tmp = ""
    try:
        processed: list[str] = []
        for seg in segs:
            src = seg["path"]
            if trim and ("start" in seg or "end" in seg or float(seg.get("speed") or 1.0) != 1.0):
                st = float(seg.get("start") or 0.0)
                en = float(seg.get("end") or 0.0)
                spd = float(seg.get("speed") or 1.0)
                if en <= st:
                    raise RuntimeError(f"裁剪区间无效：{os.path.basename(src)}")
                tp = ff.trim_video(src, st, en, volume=1.0, speed=spd)
                if not tp:
                    raise RuntimeError(f"裁剪失败：{os.path.basename(src)}")
                stage_tmps.append(tp)
                src = tp
            frozen = ff.extend_clip_end_with_last_frame(src, CLIP_END_FREEZE_SEC)
            if not frozen:
                raise RuntimeError(
                    f"末帧延长 {CLIP_END_FREEZE_SEC:.2f}s 失败：{os.path.basename(src)}"
                )
            if frozen != src:
                stage_tmps.append(frozen)
            processed.append(frozen)
        if len(processed) == 1:
            source = processed[0]
        else:
            source = ff.concat_videos(processed, True)
            concat_tmp = source or ""
            if not source:
                raise RuntimeError(f"拼接 {len(processed)} 段失败。")
        wm_tmp = config.get_temp_file(work_pid, "mp4")
        if not ff.apply_watermark_to_video(source, wm_tmp, wm_file, wm_use):
            raise RuntimeError("叠加水印失败。")
        safe_copy_overwrite(wm_tmp, out_abs)
        FfmpegProcessor.invalidate_duration_cache(out_abs)
        safe_remove(wm_tmp)
        wm_tmp = ""
        return os.path.abspath(out_abs)
    finally:
        for t in stage_tmps:
            if t and t != out_abs and t != concat_tmp:
                try:
                    safe_remove(t)
                except Exception:
                    pass
        if concat_tmp and concat_tmp not in stage_tmps and concat_tmp != out_abs:
            try:
                safe_remove(concat_tmp)
            except Exception:
                pass
        if wm_tmp:
            try:
                safe_remove(wm_tmp)
            except Exception:
                pass


def concat_scene_clips(
    clip_paths: list[str],
    *,
    pid: str,
    lang: str,
    channel_key: str,
    video_detail: dict | None = None,
) -> str:
    """CLI 简化入口：整段 clip，不裁剪、不变速。"""
    paths = [
        os.path.normpath(os.path.abspath(p))
        for p in (clip_paths or [])
        if (p or "").strip() and os.path.isfile(p)
    ]
    if not paths:
        raise RuntimeError("没有可拼接的 mp4（请先 gvd）")
    return concat_segments_to_gen_video(
        [{"path": p} for p in paths],
        pid=pid,
        lang=lang,
        channel_key=channel_key,
        video_detail=video_detail,
        trim=False,
    )


def concat_recorded_scene_clips(clips: list[dict] | list[str] | None = None) -> str:
    """用队列当前条 + Telegram 记下的场景 clip 生成成片。"""
    from aiagent.video_choice_queue import (
        current_taken_queue_item,
        resolve_video_detail_from_queue_item,
    )

    if clips is None:
        from utility.telegram_session import load_grok_scene_videos

        clips = load_grok_scene_videos()
    paths = _paths_in_scene_order(clips)
    if not paths:
        raise RuntimeError("还没有记录 grok 场景 video。先 gvd。")

    item = current_taken_queue_item() or {}
    vd = resolve_video_detail_from_queue_item(item) if item else None
    pid = ""
    if isinstance(vd, dict):
        pid = project_manager.list_json_row_workflow_pid(vd) or str(vd.get("id") or "")
    if not pid:
        pid = str(item.get("workflow_pid") or item.get("row_id") or "yt_wm")
    lang = str(item.get("yt_language") or "zh").strip() or "zh"
    channel = str(item.get("channel_id") or item.get("channel_path") or "").strip()
    return concat_scene_clips(
        paths,
        pid=pid,
        lang=lang,
        channel_key=channel,
        video_detail=vd if isinstance(vd, dict) else None,
    )


def run_concat_worker(
    *,
    segments: list[dict],
    pid: str,
    lang: str,
    on_done,
    wm_path: str = "",
    wm_opts: dict | None = None,
    gen_dir: str = "",
    dest_name: str = "",
    dest_abs: str = "",
    video_detail: dict | None = None,
    channel_key: str = "",
    trim: bool = True,
) -> None:
    """后台线程跑 ``concat_segments_to_gen_video``，结束调用 ``on_done(path, err, n)``。"""

    def _worker():
        out_ok = ""
        err_msg = ""
        n = len(segments or [])
        try:
            out_ok = concat_segments_to_gen_video(
                segments,
                pid=pid,
                lang=lang,
                dest_abs=dest_abs,
                gen_dir=gen_dir,
                dest_name=dest_name,
                video_detail=video_detail,
                wm_path=wm_path,
                wm_opts=wm_opts,
                channel_key=channel_key,
                trim=trim,
            )
        except Exception as ex:
            err_msg = str(ex)
        on_done(out_ok, err_msg, n)

    threading.Thread(target=_worker, daemon=True).start()

"""CLI YouTube 发布：跳过审阅窗手工调整，直接上传当前故事成片。

对应摘要窗「审阅发布」→「发布到 YouTube」里的上传，但：

- 标题用对话框默认（scene 首条 caption / 原标题）
- 描述素材来源可问 1/2/3（与对话框单选相同）；``default`` 走对话框默认优先级
- **不问定时**：一律立即上传（unlisted），不弹日历
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import config
import project_manager
from gui.publish_metadata_dialog import (
    default_publish_description_source,
    description_text_for_source,
    list_available_description_sources,
    resolve_publish_default_title,
    scene_content_list_for_publish,
)


def resolve_current_publish_context() -> dict:
    """当前队列条 + video_detail + 成片 mp4。缺一则抛 RuntimeError。"""
    from aiagent.video_choice_queue import (
        current_taken_queue_item,
        resolve_video_detail_from_queue_item,
    )

    item = current_taken_queue_item()
    if not item:
        raise RuntimeError("队列没有当前条目。先 next / go 打开这条故事。")
    vd = resolve_video_detail_from_queue_item(item)
    if not isinstance(vd, dict):
        raise RuntimeError("找不到当前条目的 video_detail（list_json 对不上）。")
    lang = (
        str(item.get("yt_language") or vd.get("language") or "zh").strip() or "zh"
    )
    channel_id = str(item.get("channel_id") or "").strip()
    channel_path = str(item.get("channel_path") or "").strip()
    if not channel_id and channel_path:
        channel_id = os.path.basename(channel_path.rstrip("\\/"))
    mp4 = _resolve_mp4(vd)
    if not mp4:
        raise RuntimeError(
            "当前条目还没有成片 mp4。先 video_concat，"
            "或确认 publish/gen_video/<id>.mp4 存在。"
        )
    return {
        "item": item,
        "video_detail": vd,
        "language": lang,
        "channel_id": channel_id,
        "channel_path": channel_path,
        "mp4_path": mp4,
    }


def _resolve_mp4(video_detail: dict) -> str:
    from gui.story_video_concat import gen_video_dest_filename

    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if gen_dir:
        cand = os.path.join(gen_dir, gen_video_dest_filename(video_detail))
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    try:
        from gui.downloader import _find_gen_video_mp4_for_row

        found = _find_gen_video_mp4_for_row(video_detail)
        if found and os.path.isfile(found):
            return os.path.abspath(found)
    except Exception:
        pass
    return ""


def list_publish_description_choices(ctx: dict | None = None) -> list[tuple[str, str]]:
    ctx = ctx or resolve_current_publish_context()
    vd = ctx["video_detail"]
    lang = ctx["language"]
    scenes = scene_content_list_for_publish(language=lang, video_detail=vd)
    review = project_manager.publish_description_source_text(vd)
    return list_available_description_sources(
        language=lang,
        scene_content_list=scenes,
        analyzed_content=vd.get("analyzed_content") or "",
        review_script_text=review,
    )


def default_publish_source_key(ctx: dict | None = None) -> str:
    ctx = ctx or resolve_current_publish_context()
    vd = ctx["video_detail"]
    lang = ctx["language"]
    scenes = scene_content_list_for_publish(language=lang, video_detail=vd)
    review = project_manager.publish_description_source_text(vd)
    return default_publish_description_source(
        analyzed=vd.get("analyzed_content") or "",
        scenes=scenes,
        review_script=review,
        language=lang,
    )


def build_publish_metadata(ctx: dict, source_key: str | None = None) -> dict:
    vd = ctx["video_detail"]
    lang = ctx["language"]
    scenes = scene_content_list_for_publish(language=lang, video_detail=vd)
    review = project_manager.publish_description_source_text(vd)
    key = (source_key or "").strip() or default_publish_source_key(ctx)
    title = resolve_publish_default_title(language=lang, video_detail=vd)
    if not title:
        title = (vd.get("title") or vd.get("video_title") or "").strip()
    if not title:
        raise RuntimeError("没有可用的 YouTube 标题（scene caption / 原标题都空）。")
    title = config.chinese_convert(title, lang)
    desc = description_text_for_source(
        key,
        language=lang,
        scene_content_list=scenes,
        analyzed_content=vd.get("analyzed_content") or "",
        review_script_text=review,
    ).strip()
    if not desc:
        raise RuntimeError(f"描述素材「{key}」为空，换一个来源。")
    desc = config.chinese_convert(desc, lang)
    return {"title": title, "description": desc, "source": key}


def _patch_list_row(item: dict, updates: dict) -> None:
    from aiagent.video_choice_queue import _match_row_in_list

    list_path = (item.get("list_json_path") or "").strip()
    if not list_path or not os.path.isfile(list_path):
        raise RuntimeError("条目没有有效的 list_json_path，无法写回发布结果。")
    with open(list_path, "r", encoding="utf-8") as f:
        arr = json.load(f)
    if not isinstance(arr, list):
        raise RuntimeError("list_json 不是数组。")
    row = _match_row_in_list(arr, item)
    if not isinstance(row, dict):
        raise RuntimeError("列表里找不到当前条目。")
    row.update(updates)
    config.write_channel_list_json(list_path, arr)


def publish_current_story(*, source_key: str | None = None) -> dict:
    """立即 unlisted 上传当前成片。返回 ``watch_url`` / ``video_id`` 等。"""
    ctx = resolve_current_publish_context()
    meta = build_publish_metadata(ctx, source_key)
    ch_key = ctx["channel_id"]
    cfg = config.get_channel_config(ch_key) if ch_key else None
    if not cfg:
        raise RuntimeError(f"未找到频道配置：{ch_key or '(空)'}")

    lang = ctx["language"]
    title = meta["title"]
    summary = meta["description"]
    disp_name = config.chinese_convert(
        title.strip().replace(" ", "_").replace("\n", "_"), lang
    )
    mp4_path = ctx["mp4_path"]

    from gui.downloader import MediaDownloader

    uploader = MediaDownloader.__new__(MediaDownloader)
    vid, published_iso = MediaDownloader.upload_video(
        uploader,
        mp4_path,
        None,
        disp_name,
        summary,
        lang,
        None,
        cfg["channel_key"],
        cfg.get("channel_id") or ch_key,
        cfg["channel_category_id"],
        [],
        privacy="unlisted",
        publish_at=None,
    )
    vid_s = str(vid).strip() if vid is not None else ""
    watch = f"https://www.youtube.com/watch?v={vid_s}" if vid_s else ""
    pub_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    updates = {"publish": pub_str}
    if watch:
        updates["url"] = watch
    from gui.downloader import _apply_publish_create_date

    vd = dict(ctx["video_detail"])
    vd.update(updates)
    _apply_publish_create_date(vd, publish_at=None, published_iso=published_iso or "")
    if vd.get("create_date"):
        updates["create_date"] = vd["create_date"]
    _patch_list_row(ctx["item"], updates)

    tg_lines: list[str] = []
    try:
        from utility.telegram_notify import notify_youtube_publish_extras

        tg_lines = notify_youtube_publish_extras(
            mp4_path=mp4_path,
            watch_url=watch,
            title_line=disp_name,
            summary=summary,
        )
    except Exception as exc:
        tg_lines = [f"Telegram（旁路异常）: {exc}"]

    archive_msg = ""
    try:
        from gui.downloader import _move_published_input_media_files

        archive_msg = _move_published_input_media_files(mp4_path, vd) or ""
    except Exception as exc:
        archive_msg = f"归档跳过：{exc}"

    return {
        "video_id": vid_s,
        "watch_url": watch,
        "title": disp_name,
        "source": meta["source"],
        "mp4_path": mp4_path,
        "telegram": tg_lines,
        "archive": archive_msg,
    }

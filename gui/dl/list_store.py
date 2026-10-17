"""channel / topic list JSON storage (moved verbatim from gui/dl/youtube_dl.py)."""
import os
import copy
import config
import project_manager
import json
from datetime import datetime
from gui.dl.gen_video_files import GEN_VIDEO_SLIDE_KEY, _find_gen_video_slide_for_row, _gen_video_id_stem_candidates_for_row, _video_detail_project_pid  # re-export


def _write_channel_list_json_file(list_path: str, data) -> None:
    """写 ``program/<channel>/list/*.json``，写入前自动备份到 ``list/_backup/``。"""
    config.write_channel_list_json(list_path, data)


def _channel_list_dir_for_media_downloader(youtube_dir: str) -> str:
    """若 ``youtube_dir`` 为 ``<频道>/Download``，列表目录为 ``<频道>/list``；否则（如项目路径）为 ``<youtube_dir>/list``。"""
    norm = os.path.normpath(youtube_dir)
    if os.path.basename(norm) == "Download":
        return config.channel_list_json_dir_abs(os.path.dirname(norm))
    return os.path.join(norm, "list")


def _downloader_aux_dir(youtube_dir: str) -> str:
    """下载器辅助文件目录（cookies、频道 info 等）。

    频道 GUI（``youtube_dir=<channel>/Download``）→ ``program/<channel>``（原 ``Download/work``）。
    项目内 ``MediaDownloader`` → 项目目录 ``youtube_dir`` 本身。
    """
    norm = os.path.normpath(youtube_dir or "")
    if os.path.basename(norm) == "Download":
        return os.path.dirname(norm)
    return norm


def _youtube_row_source_title(video_detail: dict) -> str:
    """原视频标题（列表行外层 ``title``，兼容旧顶层 ``video_title``）。"""
    if not isinstance(video_detail, dict):
        return ""
    return (video_detail.get("title") or video_detail.get("video_title") or "").strip()


def _youtube_row_project_title(video_detail: dict) -> str:
    """项目成片名（``project_profile.video_title``）。"""
    if not isinstance(video_detail, dict):
        return ""
    prof = video_detail.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict):
        return (prof.get("video_title") or "").strip()
    return ""


def _youtube_row_display_title(video_detail: dict) -> str:
    """业务逻辑用标题：若有 ``project_profile.video_title`` 则优先成片名；否则原视频标题。"""
    proj = _youtube_row_project_title(video_detail)
    if proj:
        return proj
    return _youtube_row_source_title(video_detail)


def _infer_channel_list_item_media_dir(item: dict, channel_path: str = "") -> str:
    """推断频道列表条目字幕/媒体目录 ``program/<ch>/Download/media``。"""
    if isinstance(item, dict):
        for key in ("transcribed_file", "audio_path", "video_path"):
            p = (item.get(key) or "").strip()
            if not p:
                continue
            d = os.path.dirname(os.path.abspath(p))
            if d and os.path.isdir(d):
                return d
            if d:
                return d
    ch = (channel_path or "").strip()
    if ch:
        return os.path.join(ch, "Download", "media")
    return ""


def _normalize_channel_list_item_for_storage(item: dict, channel_path: str = "") -> None:
    """无项目行：外层统一 ``title``，顶层 ``video_title`` 仅作旧数据合并进 ``title``。
    有 ``project_profile`` 的行：外层 ``title`` 表示原视频标题，不因顶层 ``video_title`` 改写 ``title``；收窄 ``project_profile``。"""
    if not isinstance(item, dict):
        return
    prof = item.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict) and prof:
        item.pop("video_title", None)
    else:
        t = (item.get("title") or "").strip()
        vt = (item.get("video_title") or "").strip()
        item["title"] = t if t else vt
        item.pop("video_title", None)
    item.pop("project_id", None)
    item.pop("project_pid", None)
    item.pop("pid", None)
    item.pop("youtube_source_id", None)
    item.pop("youtube_watch_url", None)
    item.pop("published_watch_url", None)
    config.migrate_content_to_transcribed_file(
        item,
        media_dir=_infer_channel_list_item_media_dir(item, channel_path),
    )
    prof = item.get(project_manager.PROJECT_PROFILE_KEY)
    if isinstance(prof, dict):
        item[project_manager.PROJECT_PROFILE_KEY] = project_manager.profile_for_list_storage(copy.deepcopy(prof))
    _sync_project_video_title_on_list_row(item)
    project_manager.sync_list_item_id_and_profile_pid(item)


_GENERIC_PROJECT_VIDEO_TITLES = frozenset({"", "新项目", "未命名", "default_title"})


def _sync_project_video_title_on_list_row(
    row: dict, selected_config: dict | None = None
) -> None:
    """``project_profile.video_title`` 优先 scene 首场景 caption，避免「新项目」占位。"""
    if not isinstance(row, dict):
        return
    prof = row.get(project_manager.PROJECT_PROFILE_KEY)
    if not isinstance(prof, dict) or not prof:
        return
    cfg = selected_config if isinstance(selected_config, dict) else {}
    pending = str(row.pop(project_manager.PENDING_PROJECT_TITLE_KEY, "") or "").strip()
    if pending:
        # 建项目之前用户选定的名称（拖进文件时改名等）：直接作成片名
        merged = copy.deepcopy(prof)
        merged["video_title"] = pending
        row[project_manager.PROJECT_PROFILE_KEY] = project_manager.profile_for_list_storage(merged)
        if isinstance(selected_config, dict):
            selected_config["video_title"] = pending
        return
    sc = row.get("scene_content") or cfg.get("scene_content")
    sc_title = (project_manager.title_from_scene_content(sc) or "").strip()
    vt = (prof.get("video_title") or cfg.get("video_title") or "").strip()
    if vt and vt not in _GENERIC_PROJECT_VIDEO_TITLES:
        return
    pick = sc_title
    if not pick:
        return
    merged = copy.deepcopy(prof)
    merged["video_title"] = pick
    row[project_manager.PROJECT_PROFILE_KEY] = project_manager.profile_for_list_storage(
        merged
    )


def _normalize_channel_videos_for_storage(items, channel_path: str = "") -> None:
    """就地规范化列表条目。"""
    if not items:
        return
    for it in items:
        if isinstance(it, dict):
            _normalize_channel_list_item_for_storage(it, channel_path)


# --- moved from gui/downloader.py: channel / topic list JSON storage ---


def _persist_channel_videos(mgr) -> bool:
    try:
        _write_channel_list_json_file(
            mgr.downloader.channel_list_json,
            mgr.downloader.channel_videos,
        )
        return True
    except Exception as e:
        print(f"保存 channel 列表失败: {e}")
        return False


def _topic_category_program_list_path(channel_path: str, topic_category: str) -> str:
    d = config.ensure_channel_list_by_topic_dir(channel_path)
    return os.path.join(d, config.topic_category_list_file_basename(topic_category))


def _youtube_row_scene_meta_title(video_detail: dict) -> str:
    """scene_content 首条 caption。"""
    if not isinstance(video_detail, dict):
        return ""
    sc = video_detail.get("scene_content")
    if isinstance(sc, list) and sc and isinstance(sc[0], dict):
        return project_manager.caption_from_scene_content_item(sc[0])
    return ""


def _youtube_row_list_suffix_title(video_detail: dict) -> str:
    """列表行标题后缀：``project_profile.video_title`` > scene 首场景 caption。"""
    if not isinstance(video_detail, dict):
        return ""
    proj = _youtube_row_project_title(video_detail)
    if proj and proj not in _GENERIC_PROJECT_VIDEO_TITLES:
        return proj
    scene_meta = _youtube_row_scene_meta_title(video_detail)
    if scene_meta:
        return scene_meta
    sc = video_detail.get("scene_content")
    return (project_manager.title_from_scene_content(sc) or "").strip()


def _youtube_row_list_display_title(
    video_detail: dict, *, max_src_chars: int | None = None
) -> str:
    """列表树展示用标题：``原视频标题 (成片名或 story title)``。

    ``max_src_chars``：有后缀时截断原标题，保证括号内项目/story 名可见。
    """
    src = _youtube_row_source_title(video_detail)
    suffix = _youtube_row_list_suffix_title(video_detail)

    def _trunc_src(s: str) -> str:
        if not max_src_chars or len(s) <= max_src_chars:
            return s
        return s[:max_src_chars].rstrip() + "…"

    if suffix and suffix != src:
        return f"{_trunc_src(src)} ({suffix})" if src else suffix
    return _trunc_src(src)


def _drop_cloned_duplicates_of_row(videos: list, keeper: dict) -> list:
    """从频道热门列表去掉同一源视频的旧克隆行，只保留 ``keeper``。"""
    if not isinstance(keeper, dict):
        return list(videos or [])
    keep_pid = project_manager.list_json_row_workflow_pid(keeper)
    keep_url = (keeper.get("url") or "").strip()
    out = []
    for v in videos or []:
        if not isinstance(v, dict):
            continue
        if project_manager.list_json_row_workflow_pid(v) == keep_pid:
            out.append(v)
            continue
        cfu = (v.get("cloned_from_url") or "").strip()
        if keep_url and cfu == keep_url:
            continue
        out.append(v)
    return out


def _apply_project_config_to_list_row(
    row: dict, selected_config: dict, *, channel_path: str = ""
) -> None:
    """将新建/更新后的项目配置写入频道热门列表中的源视频行（不克隆新行；保留外层 YouTube ``id``）。"""
    row.pop("cloned_from_id", None)
    row.pop("cloned_from_url", None)
    row.pop("youtube_source_id", None)
    row[project_manager.PROJECT_PROFILE_KEY] = project_manager.profile_for_list_storage(
        project_manager.export_profile_for_storage(copy.deepcopy(selected_config))
    )
    for k in (
        "analyzed_content",
        "scene_content",
        "topic_category",
        "topic_subtype",
        "tags",
        "language",
    ):
        if k in selected_config and selected_config.get(k) is not None:
            row[k] = copy.deepcopy(selected_config[k])
    row.pop("project_id", None)
    row.pop("project_pid", None)
    row.pop("pid", None)
    _sync_project_video_title_on_list_row(row, selected_config)
    _normalize_channel_list_item_for_storage(row, channel_path or "")


def _remove_pid_from_topic_category_lists(channel_path: str, pid: str) -> None:
    """项目 pid 变更后，从各主题分表中移除旧 pid 行。"""
    pid = (pid or "").strip()
    ch = (channel_path or "").strip()
    if not pid or not ch:
        return
    list_dir = config.channel_list_by_topic_dir_abs(ch)
    if not os.path.isdir(list_dir):
        return
    for name in os.listdir(list_dir):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(list_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(arr, list):
            continue
        new_arr = [
            it
            for it in arr
            if not (isinstance(it, dict) and _list_json_item_matches_pid(it, pid))
        ]
        if len(new_arr) == len(arr):
            continue
        try:
            config.write_channel_list_json(path, new_arr)
        except OSError:
            pass


_STORY_COPY_PROJECT_KEYS = (
    "project_profile",
    "project_id",
    "project_pid",
    "pid",
    "video_title",
    "gen_video_stem",
    "cloned_from_id",
    "cloned_from_url",
    "youtube_source_id",
    "youtube_watch_url",
    "published_watch_url",
    "publish",
    "create_date",
    "status",
)


def _fresh_story_row_id(existing: set) -> str:
    """列表行新编号，不与已有 ``id`` 重复。"""
    import uuid

    for _ in range(30):
        nid = "s" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
        if nid not in existing:
            existing.add(nid)
            return nid
    nid = "s" + uuid.uuid4().hex
    existing.add(nid)
    return nid


def _copy_story_list_row(src: dict, new_id: str) -> dict:
    """复制故事材料。新 ``id``；去掉项目信息。幻灯片 PDF 仍指向原来的文件。"""
    row = copy.deepcopy(src)
    slide = _find_gen_video_slide_for_row(src)
    for key in _STORY_COPY_PROJECT_KEYS:
        row.pop(key, None)
    row["id"] = new_id
    row["view_count"] = 0
    if slide:
        row[GEN_VIDEO_SLIDE_KEY] = slide
    stored_video = (row.get("video") or "").strip()
    gen_dir = getattr(config, "INPUT_MEDIA_GEN_VIDEO_PATH", "") or ""
    if stored_video and gen_dir and os.path.normcase(os.path.abspath(stored_video)).startswith(
        os.path.normcase(os.path.abspath(gen_dir))
    ):
        row.pop("video", None)
    _normalize_channel_list_item_for_storage(row)
    return row


def _channel_list_row_tree_key(video: dict) -> str:
    """树视图 tag / 查找键：优先外层 ``id``，否则 ``url``。"""
    if not isinstance(video, dict):
        return ""
    iid = project_manager.list_json_row_id(video)
    if iid:
        return iid
    return (video.get("url") or "").strip()


def _channel_list_row_dedupe_key(video: dict) -> str:
    """列表去重键：优先外层 ``id``（YouTube id 或独立行 id）；无 id 再按 ``url``；最后按展示标题。"""
    if not isinstance(video, dict):
        return ""
    iid = project_manager.list_json_row_id(video)
    if iid:
        return f"id:{iid}"
    u = (video.get("url") or "").strip()
    if u:
        return f"url:{u}"
    t = _youtube_row_display_title(video).strip().lower()
    if t:
        return f"title:{t}"
    return f"row:{id(video)}"


def _channel_list_row_complete_score(video: dict) -> int:
    c = config.read_transcript_text_from_video_detail(video)
    cat = (video.get("topic_category") or "").strip()
    sub = (video.get("topic_subtype") or "").strip()
    content_len = len(c)
    if cat and sub:
        return 1_000_000 + content_len
    return content_len


def dedupe_channel_video_list(videos: list) -> list:
    """仅合并去重键完全相同的行；勿按展示标题误删不同项目/不同 url 的条目。"""
    by_key = {}
    for video in videos or []:
        if not isinstance(video, dict):
            continue
        key = _channel_list_row_dedupe_key(video)
        if not key:
            continue
        if key not in by_key:
            by_key[key] = video
            continue
        cur = by_key[key]
        if _channel_list_row_complete_score(video) > _channel_list_row_complete_score(cur):
            by_key[key] = video
    return list(by_key.values())


def _is_viewing_topic_category_program_list(
    channel_path: str, list_json_path: str, topic_category: str
) -> bool:
    """当前打开的 ``channel_list_json`` 是否即为某主题分表（``list_by_topic/<topic>.json``）。"""
    list_json_path = (list_json_path or "").strip()
    topic_category = (topic_category or "").strip()
    if not list_json_path or not topic_category:
        return False
    topic_path = _topic_category_program_list_path(channel_path, topic_category)
    if not topic_path:
        return False
    return os.path.normcase(os.path.normpath(list_json_path)) == os.path.normcase(
        os.path.normpath(topic_path)
    )


def _upsert_topic_category_program_list_row(channel_path: str, topic_category: str, entry: dict) -> str:
    """按 ``pid`` 对指定主题分表做 upsert（去掉同 PID 旧行再追加），返回写入路径。"""
    path = _topic_category_program_list_path(channel_path, topic_category or "")
    pid = _video_detail_project_pid(entry)
    arr = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)
        except (json.JSONDecodeError, OSError):
            arr = []
    if not isinstance(arr, list):
        arr = []
    if pid:
        arr = [it for it in arr if isinstance(it, dict) and not _list_json_item_matches_pid(it, pid)]
    arr.append(copy.deepcopy(entry))
    config.write_channel_list_json(path, arr)
    return path




def _video_detail_source_keys(vd: dict) -> tuple[str, str]:
    """源 YouTube 行的 ``id`` / ``url``，用于匹配 ``cloned_from_*``。"""
    if not isinstance(vd, dict):
        return "", ""
    return (str(vd.get("id") or "").strip(), str(vd.get("url") or "").strip())


def _find_cloned_project_pids_for_source(vd: dict, channel_videos: list) -> list[str]:
    """同源克隆项目 pid 列表（主题分表里「新建项目」追加的行，``cloned_from_id/url`` 指向源行）。"""
    src_id, src_url = _video_detail_source_keys(vd)
    if not src_id and not src_url:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in channel_videos or []:
        if not isinstance(item, dict):
            continue
        pid = _video_detail_project_pid(item)
        if not pid or pid in seen:
            continue
        cf_id = (item.get("cloned_from_id") or "").strip()
        cf_url = (item.get("cloned_from_url") or "").strip()
        matched = (src_id and cf_id == src_id) or (src_url and cf_url and cf_url == src_url)
        if matched:
            seen.add(pid)
            out.append(pid)
    return out


def _list_row_index_for_pid(channel_videos: list, pid: str) -> int:
    pid = (pid or "").strip()
    if not pid:
        return -1
    for i, item in enumerate(channel_videos or []):
        if _list_json_item_matches_pid(item, pid):
            return i
    return -1


def _list_json_item_matches_pid(item: dict, wanted_pid: str) -> bool:
    """主题分表或列表中的一行是否与给定 ``pid`` 对应（优先 ``project_profile.pid``）。"""
    wanted_pid = (wanted_pid or "").strip()
    if not wanted_pid or not isinstance(item, dict):
        return False
    return project_manager.list_json_row_workflow_pid(item) == wanted_pid





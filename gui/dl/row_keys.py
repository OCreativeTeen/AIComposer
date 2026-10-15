"""list-row id helpers (no gui.dl deps) (moved verbatim from gui/dl/youtube_dl.py)."""
import re
import project_manager


def _video_youtube_id(v):
    """从频道视频项解析 YouTube 视频 id（11 位）。

    有 ``project_profile`` 的行：外层 ``id`` 可仍为源 YouTube id；亦从 ``url`` / ``cloned_from_url`` 解析。
    无项目行：``id`` 或 ``url`` 均可。
    """
    if not isinstance(v, dict):
        return ""
    has_proj = project_manager.list_json_row_has_project_profile(v)
    if not has_proj:
        vid = (v.get("id") or "").strip()
        if vid and len(vid) == 11:
            return vid
    for key in ("url", "cloned_from_url"):
        u_pub = (v.get(key) or "").strip()
        if u_pub:
            m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", u_pub)
            if m:
                return m.group(1)
            m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", u_pub)
            if m:
                return m.group(1)
    if has_proj:
        vid = (v.get("id") or "").strip()
        if vid and project_manager.list_row_outer_id_in_watch_url(v):
            return vid
        return ""
    vid = (v.get("id") or "").strip()
    if vid and len(vid) == 11:
        return vid
    return ""

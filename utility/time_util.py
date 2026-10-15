"""date helpers (moved verbatim from gui/downloader.py)."""
from datetime import datetime


def _should_update_upload_date(video: dict) -> bool:
    """是否允许用 YouTube API / yt-dlp 的 ``upload_date`` 写入本条（下载、频道刷新）。

    克隆项目行（``cloned_from_*``）跳过；源下载行及发布后 ``url`` 已变的行均允许更新。
    本工具发布到 YouTube 不写 ``upload_date``，改写 ``create_date``（见 ``_apply_publish_create_date``）。
    """
    if not isinstance(video, dict):
        return False
    if (video.get("cloned_from_url") or video.get("cloned_from_id") or "").strip():
        return False
    return True


def _format_publish_display_date(pub_s: str) -> str:
    """将已发布时间的多种字符串格式压成 yyyy-mm-dd（只精确到天）。"""
    s = (pub_s or "").strip()
    if not s:
        return ""
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00").split("+")[0])
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return s[:10] if len(s) >= 10 else s

"""t99u: 发布 Telegram = 从已发布(unlisted)的 YouTube 链接下载较小的 mp4,再用发布 Bot 发出。

列表行字段(由 YouTube 发布写入):
    published_youtube_url / published_youtube_video_id / published_youtube_title /
    published_youtube_description / published_youtube_at
"""

from __future__ import annotations

import os
import time

URL_KEY = "published_youtube_url"
ID_KEY = "published_youtube_video_id"
TITLE_KEY = "published_youtube_title"
DESC_KEY = "published_youtube_description"
AT_KEY = "published_youtube_at"

_RETRY_HINTS = ("processing", "unavailable", "not available", "try again", "is not yet", "premiere", "http error 403")


def published_youtube_url(row: dict | None) -> str:
    return str((row or {}).get(URL_KEY) or "").strip() if isinstance(row, dict) else ""


def _say(status, msg: str) -> None:
    print(msg)
    if callable(status):
        try:
            status(msg)
        except Exception:  # noqa: BLE001
            pass


def send_published_youtube_to_telegram(row: dict, *, status=None, retries: int = 4, wait_s: int = 30) -> list[str]:
    """下载 ``row[published_youtube_url]`` (<=720p mp4),然后 notify_youtube_publish_extras。"""
    from utility.telegram_notify import notify_youtube_publish_extras, telegram_publish_enabled
    from utility.youtube_download import download_dir, download_youtube

    url = published_youtube_url(row)
    if not url:
        raise RuntimeError("这一项还没有 YouTube 链接,请先「发布 YouTube」。")
    if not telegram_publish_enabled():
        raise RuntimeError("Telegram 未配置:需要在 D:\\AIComposer\\.env 填 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_IDS（逗号分隔）。")
    out_dir = os.path.join(download_dir(), "telegram_publish")
    res = None
    last = ""
    for attempt in range(retries + 1):
        try:
            res = download_youtube(url, resolution="telegram", out_dir=out_dir, status=status,
                                   transcript=False, local_fallback=False)
            break
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            low = last.lower()
            if attempt < retries and any(h in low for h in _RETRY_HINTS):
                _say(status, f"YouTube 可能还在处理视频,{wait_s} 秒后重试 ({attempt + 1}/{retries}) .")
                time.sleep(wait_s)
                continue
            break
    if not res or not res.get("video") or not os.path.isfile(res["video"]):
        raise RuntimeError(
            "从 YouTube 下载失败(刚上传的视频可能还在处理,请稍等几分钟再试):\n" + last[:800]
        )
    mp4 = res["video"]
    mb = os.path.getsize(mp4) / (1024 * 1024)
    _say(status, f"已下载 {os.path.basename(mp4)} ({mb:.1f} MB),发送 Telegram .")
    title = str(row.get(TITLE_KEY) or row.get("title") or res.get("title") or "").strip()
    desc = str(row.get(DESC_KEY) or row.get("summary") or "").strip()
    lines = [f"下载:{os.path.basename(mp4)} ({mb:.1f} MB)"]
    lines += notify_youtube_publish_extras(mp4_path=mp4, watch_url=url, title_line=title, summary=desc)
    return lines

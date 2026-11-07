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


def send_published_youtube_to_telegram(
    row: dict, *, status=None, retries: int = 4, wait_s: int = 30, channel_id: str | None = None,
) -> list[str]:
    """下载 ``row[published_youtube_url]`` (<=720p mp4),然后 notify_youtube_publish_extras。

    t236u: 若 YouTube 上是定时公开(private+publishAt)，先临时改为 unlisted 再下，下完恢复原状态。
    """
    from utility.telegram_notify import notify_youtube_publish_extras, telegram_publish_enabled
    from utility.youtube_download import download_dir, download_youtube

    url = published_youtube_url(row)
    if not url:
        raise RuntimeError("这一项还没有 YouTube 链接,请先「发布 YouTube」。")
    if not telegram_publish_enabled():
        raise RuntimeError(
            "Telegram 未配置:需要在 D:\\AIComposer\\.env 填 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_IDS（逗号分隔）。"
        )
    out_dir = os.path.join(download_dir(), "telegram_publish")

    # t236u: 用上传留下的 token 改隐私（没有 token / 改失败仍尝试直接下载）
    yt_client = None
    video_id = ""
    try:
        from gui.dl.youtube_dl import (
            temporary_unlisted_for_download,
            youtube_from_saved_token,
            youtube_video_id_from_url,
        )
        import project_manager as _pm

        video_id = (str(row.get(ID_KEY) or "").strip() or youtube_video_id_from_url(url))
        ch = (channel_id or "").strip() or str((_pm.PROJECT_CONFIG or {}).get("channel") or "").strip()
        if video_id and ch:
            yt_client = youtube_from_saved_token(ch)
            if yt_client is None:
                _say(status, f"没有频道 {ch} 的 YouTube token，无法临时改隐私；直接尝试下载。")
    except Exception as exc:  # noqa: BLE001
        _say(status, f"准备临时改隐私时出错（将直接下载）: {exc}")
        yt_client = None

    def _do_download():
        res_local = None
        last_local = ""
        for attempt in range(retries + 1):
            try:
                res_local = download_youtube(
                    url, resolution="telegram", out_dir=out_dir, status=status,
                    transcript=False, local_fallback=False,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_local = str(exc)
                low = last_local.lower()
                if attempt < retries and any(h in low for h in _RETRY_HINTS):
                    _say(status, f"YouTube 可能还在处理视频,{wait_s} 秒后重试 ({attempt + 1}/{retries}) .")
                    time.sleep(wait_s)
                    continue
                break
        return res_local, last_local

    if yt_client is not None and video_id:
        with temporary_unlisted_for_download(yt_client, video_id, status=status) as _snap:
            res, last = _do_download()
    else:
        res, last = _do_download()

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

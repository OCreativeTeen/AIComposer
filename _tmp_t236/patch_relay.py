# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(r"D:\AIComposer")


def patch_relay():
    path = ROOT / "utility" / "telegram_youtube_relay.py"
    text = path.read_text(encoding="utf-8")
    if "temporary_unlisted_for_download" in text:
        print("relay already patched")
        return
    start = text.index("def send_published_youtube_to_telegram(")
    # end at next top-level def or EOF — this file only has this function after helpers
    # find the mp4 = res["video"] line which stays
    keep_from = text.index('    mp4 = res["video"]', start)
    new_fn = '''def send_published_youtube_to_telegram(
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
            "Telegram 未配置:需要在 D:\\\\AIComposer\\\\.env 填 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_IDS（逗号分隔）。"
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
            "从 YouTube 下载失败(刚上传的视频可能还在处理,请稍等几分钟再试):\\n" + last[:800]
        )

'''
    # Fix: in the written file we need actual `\n` escape in the RuntimeError string
    new_fn = new_fn.replace(
        '"从 YouTube 下载失败(刚上传的视频可能还在处理,请稍等几分钟再试):\\n" + last[:800]',
        '"从 YouTube 下载失败(刚上传的视频可能还在处理,请稍等几分钟再试):\\n" + last[:800]',
    )
    # The D:\\\\ in new_fn is for producing D:\\ in output file (matching original style)
    text = text[:start] + new_fn + text[keep_from:]
    path.write_text(text, encoding="utf-8")
    print("relay patched; verify:")
    t2 = path.read_text(encoding="utf-8")
    print("has temp unlisted:", "temporary_unlisted_for_download" in t2)
    # compile-check the error string has one backslash-n
    import re
    m = re.search(r'下载失败.*?(\\\\n|\\n)', t2)
    print("newline escape sample near error:", m.group(0) if m else None)


def patch_finalize():
    path = ROOT / "gui" / "workflow" / "wf_finalize_publish.py"
    text = path.read_text(encoding="utf-8")
    if "_adjust_youtube_publish" in text:
        print("finalize already has adjust")
    else:
        old_pub = '''    def publish_video(self, send_telegram: bool = False):
        """t99u: 只发 YouTube,上传后立即 unlisted(不排期);send_telegram 已废弃,Telegram 请用 publish_telegram。"""
        if getattr(self, "_publish_upload_running", False):
'''
        helpers = Path(r"D:\AIComposer\_tmp_t236\finalize_helpers.py.txt")
        # write helpers separately with correct escapes
        pass

    # Do finalize with a dedicated Python file that constructs strings properly
    print("finalize deferred to next script")


if __name__ == "__main__":
    patch_relay()

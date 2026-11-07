# -*- coding: utf-8 -*-
"""t236u: YouTube privacy helpers + Telegram temp-unlisted + republish/adjust."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"D:\AIComposer")

HELPERS = r'''

def youtube_video_id_from_url(url: str) -> str:
    """从 watch / youtu.be / shorts URL 取出 11 位 video id。"""
    url = (url or "").strip()
    if not url:
        return ""
    m = re.search(r"(?:[?&]v=|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else ""


def get_video_status(youtube, video_id: str) -> dict:
    """读 videos.status：privacyStatus / publishAt 等。找不到则抛错。"""
    vid = (video_id or "").strip()
    if not vid:
        raise ValueError("缺少 YouTube video id")
    resp = youtube.videos().list(part="status", id=vid).execute() or {}
    items = resp.get("items") or []
    if not items:
        raise RuntimeError(f"YouTube 找不到视频 {vid}（可能已删）")
    st = dict((items[0] or {}).get("status") or {})
    return {
        "privacyStatus": (st.get("privacyStatus") or "").strip() or "private",
        "publishAt": (st.get("publishAt") or "").strip() or None,
        "selfDeclaredMadeForKids": bool(st.get("selfDeclaredMadeForKids", False)),
        "containsSyntheticMedia": st.get("containsSyntheticMedia"),
    }


def set_video_privacy(youtube, video_id: str, privacy: str, *, publish_at=None) -> dict:
    """改隐私。``publish_at`` 为 datetime 或 RFC3339 字符串时：private + publishAt（定时公开）。
    ``privacy='unlisted'|'public'|'private'`` 且 publish_at is None：清掉定时。"""
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    vid = (video_id or "").strip()
    if not vid:
        raise ValueError("缺少 YouTube video id")
    privacy = (privacy or "").strip().lower()
    if privacy not in ("public", "unlisted", "private"):
        raise ValueError(f"无效 privacy: {privacy}")

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }
    if publish_at is not None:
        if isinstance(publish_at, _dt):
            local_tz = _dt.now().astimezone().tzinfo
            dt_utc = publish_at if publish_at.tzinfo else publish_at.replace(tzinfo=local_tz)
            dt_utc = dt_utc.astimezone(_tz.utc)
            publish_at_str = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            publish_at_str = str(publish_at).strip()
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at_str
        print(f"📅 YouTube 定时公开（UTC）: {publish_at_str}  id={vid}")
    else:
        print(f"🔒 YouTube privacy → {privacy}  id={vid}")

    return youtube.videos().update(
        part="status",
        body={"id": vid, "status": status},
    ).execute()


def restore_video_status(youtube, video_id: str, snap: dict) -> dict:
    """按 get_video_status 快照恢复 privacy / publishAt。"""
    snap = dict(snap or {})
    privacy = (snap.get("privacyStatus") or "private").strip().lower()
    publish_at = snap.get("publishAt") or None
    # 定时公开：必须 private + publishAt；若快照是 unlisted/public 则不带 publishAt
    if publish_at and privacy == "private":
        return set_video_privacy(youtube, video_id, "private", publish_at=publish_at)
    return set_video_privacy(youtube, video_id, privacy, publish_at=None)


def delete_youtube_video(youtube, video_id: str) -> None:
    """删除频道上的视频（videos.delete）。"""
    vid = (video_id or "").strip()
    if not vid:
        raise ValueError("缺少 YouTube video id")
    youtube.videos().delete(id=vid).execute()
    print(f"🗑️ 已删除 YouTube 视频 {vid}")


def temporary_unlisted_for_download(youtube, video_id: str, *, status=None, settle_s: float = 3.0):
    """若当前是 private（含定时公开），临时改为 unlisted 以便 yt-dlp 下载；结束后恢复原状态。

    用法::
        with temporary_unlisted_for_download(yt, vid, status=say) as snap:
            download_youtube(...)
    """
    import contextlib
    import time as _time

    @contextlib.contextmanager
    def _cm():
        snap = get_video_status(youtube, video_id)
        priv = (snap.get("privacyStatus") or "").lower()
        changed = False

        def _say(msg: str) -> None:
            print(msg)
            if callable(status):
                try:
                    status(msg)
                except Exception:  # noqa: BLE001
                    pass

        try:
            # public / unlisted 可直接下；private（含 publishAt 定时）需要临时放开
            if priv == "private":
                _say("视频当前为私有/定时公开，临时改为「不公开列出」以便下载…")
                set_video_privacy(youtube, video_id, "unlisted")
                changed = True
                if settle_s and settle_s > 0:
                    _time.sleep(float(settle_s))
            yield snap
        finally:
            if changed:
                try:
                    _say("下载结束，恢复原来的 YouTube 发布状态…")
                    restore_video_status(youtube, video_id, snap)
                except Exception as exc:  # noqa: BLE001
                    _say(f"⚠️ 恢复原发布状态失败（请到 Studio 手动改回）: {exc}")

    return _cm()

'''


def patch_youtube_dl():
    path = ROOT / "gui" / "dl" / "youtube_dl.py"
    text = path.read_text(encoding="utf-8")
    if "def temporary_unlisted_for_download" in text:
        print("youtube_dl helpers already present")
        return
    # ensure `re` is imported at module level
    if not re.search(r"(?m)^import re\b", text) and "import re\n" not in text:
        # likely already has re via other imports
        if "import re" not in text.split("class ")[0]:
            text = "import re\n" + text
            print("added import re")
    anchor = "def youtube_from_saved_token(channel_id: str):"
    if anchor not in text:
        raise SystemExit("youtube_from_saved_token not found")
    # insert AFTER youtube_from_saved_token function — find ensure_all_topic_playlists
    mark = "def ensure_all_topic_playlists(channel_id: str, youtube=None, privacy: str = \"public\") -> dict:"
    if mark not in text:
        raise SystemExit("ensure_all_topic_playlists not found")
    text = text.replace(mark, HELPERS + "\n" + mark, 1)
    raw = text.encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    path.write_bytes(raw)
    print("youtube_dl helpers inserted")


def patch_telegram_relay():
    path = ROOT / "utility" / "telegram_youtube_relay.py"
    text = path.read_text(encoding="utf-8")
    if "temporary_unlisted_for_download" in text:
        print("telegram relay already patched")
        return

    old = '''def send_published_youtube_to_telegram(row: dict, *, status=None, retries: int = 4, wait_s: int = 30) -> list[str]:
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
            "从 YouTube 下载失败(刚上传的视频可能还在处理,请稍等几分钟再试):\\n" + last[:800]
        )
'''
    new = '''def send_published_youtube_to_telegram(
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
        raise RuntimeError("Telegram 未配置:需要在 D:\\AIComposer\\.env 填 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_IDS（逗号分隔）。")
    out_dir = os.path.join(download_dir(), "telegram_publish")

    # t236u: 用上传留下的 token 改隐私（没有 token / 改失败仍尝试直接下载）
    yt_client = None
    video_id = ""
    try:
        from gui.dl.youtube_dl import temporary_unlisted_for_download, youtube_from_saved_token, youtube_video_id_from_url
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
    if old not in text:
        # try with actual newline in error string
        old2 = old.replace("\\\\n", "\\n")
        if old2 not in text:
            raise SystemExit("send_published_youtube_to_telegram block not found")
        text = text.replace(old2, new.replace("\\\\n", "\\n"), 1)
    else:
        text = text.replace(old, new, 1)
    raw = text.encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    path.write_bytes(raw)
    print("telegram_youtube_relay patched")


def patch_finalize():
    path = ROOT / "gui" / "workflow" / "wf_finalize_publish.py"
    text = path.read_text(encoding="utf-8")
    if "_adjust_youtube_publish" in text and "t236u" in text:
        print("finalize already patched")
        return

    # Patch publish_telegram to pass channel_id
    old_tg = '''                lines = send_published_youtube_to_telegram(row, status=lambda m: ui(lambda: var.set(m)))
'''
    new_tg = '''                _ch = getattr(getattr(self, "workflow", None), "channel", None) or (
                    (project_manager.PROJECT_CONFIG or {}).get("channel") or ""
                )
                lines = send_published_youtube_to_telegram(
                    row, status=lambda m: ui(lambda: var.set(m)), channel_id=str(_ch or ""),
                )
'''
    if old_tg not in text:
        raise SystemExit("publish_telegram send call not found")
    text = text.replace(old_tg, new_tg, 1)

    # Insert helpers + modify publish_video start
    # Add methods before publish_video
    old_pub = '''    def publish_video(self, send_telegram: bool = False):
        """t99u: 只发 YouTube,上传后立即 unlisted(不排期);send_telegram 已废弃,Telegram 请用 publish_telegram。"""
        if getattr(self, "_publish_upload_running", False):
'''
    new_pub = '''    def _published_youtube_id(self) -> str:
        """当前项目已发布的 YouTube video id（配置或列表行）。"""
        pc = project_manager.PROJECT_CONFIG or {}
        vid = str(pc.get("published_youtube_video_id") or "").strip()
        if vid:
            return vid
        try:
            row = project_manager.load_video_detail_row_for_config(pc) or {}
        except Exception:  # noqa: BLE001
            row = {}
        from utility.telegram_youtube_relay import ID_KEY, URL_KEY
        from gui.dl.youtube_dl import youtube_video_id_from_url

        vid = str(row.get(ID_KEY) or "").strip()
        if vid:
            return vid
        return youtube_video_id_from_url(str(row.get(URL_KEY) or ""))

    def _youtube_client_for_channel(self):
        from gui.dl.youtube_dl import youtube_from_saved_token

        ch = getattr(getattr(self, "workflow", None), "channel", None) or (
            (project_manager.PROJECT_CONFIG or {}).get("channel") or ""
        )
        yt = youtube_from_saved_token(str(ch or ""))
        if yt is None:
            raise RuntimeError(
                f"没有频道「{ch}」的 YouTube 登录 token（token_{ch}.json）。\\n"
                "请先成功「发布 YouTube」一次以完成授权。"
            )
        return yt, str(ch or "")

    def _clear_published_youtube_fields(self, *, video_id: str = "") -> None:
        """删掉旧视频后清掉配置 / 列表里的 published_youtube_*。"""
        from utility.telegram_youtube_relay import AT_KEY, AT_KEY, DESC_KEY, ID_KEY, TITLE_KEY, URL_KEY

        pc = project_manager.PROJECT_CONFIG
        if isinstance(pc, dict):
            for k in (
                "published_youtube_video_id",
                "youtube_scheduled_publish_at",
                URL_KEY, ID_KEY, TITLE_KEY, DESC_KEY, AT_KEY,
            ):
                pc.pop(k, None)
            try:
                save_project_config()
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 清 published_youtube 配置失败：{exc}")
            blanks = {URL_KEY: "", ID_KEY: "", TITLE_KEY: "", DESC_KEY: "", AT_KEY: ""}
            try:
                project_manager.save_list_row_fields_for_config(pc, blanks)
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 清列表 published_youtube 失败：{exc}")
        if video_id:
            print(f"已清除旧视频记录：{video_id}")

    def _adjust_youtube_publish(self, video_id: str) -> None:
        """t236u: 已发布过 → 只改 unlisted ↔ 定时公开，不重新上传。"""
        from gui.dl.youtube_dl import get_video_status, set_video_privacy

        try:
            yt, _ch = self._youtube_client_for_channel()
            snap = get_video_status(yt, video_id)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("调整发布状态", str(exc), parent=self.root)
            return
        cur = snap.get("privacyStatus") or "?"
        when = snap.get("publishAt") or ""
        hint = f"当前：{cur}" + (f" · 定时 {when}" if when else "")
        choice = ask_publish_schedule_dialog(
            self.root,
            mp4_path_hint=f"已有视频 {video_id}\\n{hint}",
            dialog_title="调整 YouTube 发布状态",
        )
        if choice is None:
            return
        mode, publish_at = choice
        try:
            if mode == "scheduled" and publish_at is not None:
                set_video_privacy(yt, video_id, "private", publish_at=publish_at)
                pc = project_manager.PROJECT_CONFIG
                if isinstance(pc, dict):
                    try:
                        pc["youtube_scheduled_publish_at"] = publish_at.isoformat()
                    except Exception:
                        pc["youtube_scheduled_publish_at"] = str(publish_at)
                    save_project_config()
                messagebox.showinfo(
                    "调整发布状态",
                    f"已改为定时公开。\\n到点后由 YouTube 自动公开。\\n\\nhttps://www.youtube.com/watch?v={video_id}",
                    parent=self.root,
                )
            else:
                set_video_privacy(yt, video_id, "unlisted")
                pc = project_manager.PROJECT_CONFIG
                if isinstance(pc, dict):
                    pc.pop("youtube_scheduled_publish_at", None)
                    save_project_config()
                messagebox.showinfo(
                    "调整发布状态",
                    f"已改为不公开列出（unlisted）。\\n\\nhttps://www.youtube.com/watch?v={video_id}",
                    parent=self.root,
                )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("调整发布状态", str(exc), parent=self.root)

    def _delete_published_youtube(self, video_id: str) -> bool:
        """t236u: 删除旧 YouTube 视频并清记录。成功 True。"""
        from gui.dl.youtube_dl import delete_youtube_video

        try:
            yt, _ch = self._youtube_client_for_channel()
            delete_youtube_video(yt, video_id)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("重新发布", f"删除旧视频失败：\\n{exc}", parent=self.root)
            return False
        self._clear_published_youtube_fields(video_id=video_id)
        return True

    def publish_video(self, send_telegram: bool = False):
        """t99u: 只发 YouTube,上传后立即 unlisted(不排期);send_telegram 已废弃,Telegram 请用 publish_telegram。
        t236u: 若已发布过，可选「调整排期/隐私」或「删旧后重新上传」。"""
        if getattr(self, "_publish_upload_running", False):
'''
    if old_pub not in text:
        raise SystemExit("publish_video def not found")
    text = text.replace(old_pub, new_pub, 1)

    # After the early running-check, insert already-published branch
    # Find the next lines after running check return
    insert_after = '''            messagebox.showinfo("视频发布", "上一次上传还没结束，请等它完成或先取消。", parent=self.root)
            return
        lang = getattr(self.workflow, "language", None) or "zh"
'''
    already_branch = '''            messagebox.showinfo("视频发布", "上一次上传还没结束，请等它完成或先取消。", parent=self.root)
            return
        # t236u: 已有 YouTube 成片 → 调整排期/隐私，或删掉重传
        _existing = self._published_youtube_id()
        if _existing:
            from gui.choice_dialog import askchoice

            picked = askchoice(
                "已发布过 YouTube",
                [
                    ("adjust", "调整排期 / 切换「不公开列出」与「定时公开」"),
                    ("republish", "重新发布（删除旧视频后重新上传）"),
                ],
                parent=self.root,
            )
            if not picked:
                return
            _action = picked[1]
            if _action == "adjust":
                self._adjust_youtube_publish(_existing)
                return
            if _action == "republish":
                if not messagebox.askyesno(
                    "重新发布",
                    f"将删除 YouTube 上的旧视频：\\n{_existing}\\n\\n然后重新上传成片。确定吗？",
                    parent=self.root,
                    default=messagebox.NO,
                ):
                    return
                if not self._delete_published_youtube(_existing):
                    return
            else:
                return
        lang = getattr(self.workflow, "language", None) or "zh"
'''
    if "t236u: 已有 YouTube 成片" in text:
        print("already-published branch present")
    else:
        if insert_after not in text:
            raise SystemExit("insert point after running-check not found")
        text = text.replace(insert_after, already_branch, 1)
        print("inserted already-published branch")

    # Fix finish_video_upload to pass publish_at from flow (currently hardcoded None)
    # Looking at _done: finish_video_upload(up, publish_at=None, ...) — for first publish that's fine (unlisted).
    # Keep as-is since schedule_dialog_fn still forces unlisted for new uploads.

    raw = text.encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    # Fix double-escaped newlines in Chinese strings that we introduced as \\n in source
    # In the Python source we want real \n in strings like "a\\nb" which is a\nb
    # Our new_pub used \\\\n in the raw string which became \\n in file — correct for Python source.
    path.write_bytes(raw)
    print("wf_finalize_publish patched")


if __name__ == "__main__":
    import re
    patch_youtube_dl()
    patch_telegram_relay()
    patch_finalize()

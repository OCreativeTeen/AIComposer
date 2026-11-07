# -*- coding: utf-8 -*-
from pathlib import Path

path = Path(r"D:\AIComposer\gui\workflow\wf_finalize_publish.py")
text = path.read_text(encoding="utf-8")

old_tg = (
    '                lines = send_published_youtube_to_telegram(row, status=lambda m: ui(lambda: var.set(m)))\n'
)
new_tg = (
    '                _ch = getattr(getattr(self, "workflow", None), "channel", None) or (\n'
    '                    (project_manager.PROJECT_CONFIG or {}).get("channel") or ""\n'
    '                )\n'
    '                lines = send_published_youtube_to_telegram(\n'
    '                    row, status=lambda m: ui(lambda: var.set(m)), channel_id=str(_ch or ""),\n'
    '                )\n'
)
if "channel_id=str(_ch" not in text:
    if old_tg not in text:
        raise SystemExit("tg call not found")
    text = text.replace(old_tg, new_tg, 1)
    print("patched publish_telegram channel_id")
else:
    print("tg channel_id already patched")

helpers = '''
    def _published_youtube_id(self) -> str:
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
        from utility.telegram_youtube_relay import AT_KEY, DESC_KEY, ID_KEY, TITLE_KEY, URL_KEY

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

'''

# Convert intentional \\n in helpers to real Python escapes in the written file:
# In the triple-quoted helpers above, \\n becomes \n in the string value — which is what we want
# for Python source when writing f-strings with newlines. Good.

if "_adjust_youtube_publish" not in text:
    old = '''    def publish_video(self, send_telegram: bool = False):
        """t99u: 只发 YouTube,上传后立即 unlisted(不排期);send_telegram 已废弃,Telegram 请用 publish_telegram。"""
        if getattr(self, "_publish_upload_running", False):
'''
    new = helpers + '''    def publish_video(self, send_telegram: bool = False):
        """t99u: 只发 YouTube,上传后立即 unlisted(不排期);send_telegram 已废弃,Telegram 请用 publish_telegram。
        t236u: 若已发布过，可选「调整排期/隐私」或「删旧后重新上传」。"""
        if getattr(self, "_publish_upload_running", False):
'''
    if old not in text:
        raise SystemExit("publish_video header not found")
    text = text.replace(old, new, 1)
    print("inserted helper methods")
else:
    print("helpers already present")

insert_after = '''            messagebox.showinfo("视频发布", "上一次上传还没结束，请等它完成或先取消。", parent=self.root)
            return
        lang = getattr(self.workflow, "language", None) or "zh"
'''
already = '''            messagebox.showinfo("视频发布", "上一次上传还没结束，请等它完成或先取消。", parent=self.root)
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
if "t236u: 已有 YouTube 成片" not in text:
    if insert_after not in text:
        raise SystemExit("insert_after not found")
    text = text.replace(insert_after, already, 1)
    print("inserted already-published branch")
else:
    print("already-published branch present")

path.write_text(text, encoding="utf-8")
raw = path.read_bytes()
if raw.startswith(b"\xef\xbb\xbf"):
    path.write_bytes(raw[3:])
print("finalize written")
